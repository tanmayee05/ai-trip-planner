"""
The trip-planning agent — a LangGraph StateGraph.

WHY LangGraph instead of just calling functions in sequence
----------------------------------------------------------
Planning a trip is a multi-step pipeline where:
  * later steps depend on earlier ones (costs need the transport result),
  * some steps branch (own vehicle vs public transport, stops vs no-stops),
  * some steps LOOP: the itinerary node asks Gemini for a day-by-day plan,
    checks it, and re-prompts if it's wrong — a bounded retry cycle.

LangGraph models that as a directed graph of **nodes** sharing one **state**
object. Each node is a tiny function `(state) -> {partial updates}`; LangGraph
merges the returned dict into the state and follows the edges. Edges can be
plain (A -> B) or **conditional** (a function inspects the state and picks the
next node) — that's how we do "valid? go on. invalid? loop back."

  .compile()  -> an object we can .invoke() (run to completion, what we do now),
                 .stream() (progress per node, Step D), or checkpoint.

STEP B (this file): the `resolve` -> `cluster_itinerary` -> `repair` loop is a
real reasoning step now. `plan_transport` / `estimate_costs` still wrap the
existing logic unchanged.
"""

import operator
import os
import re
from datetime import date, timedelta
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import START, END, StateGraph
from pydantic import BaseModel, Field

from connectivity import check_all_modes
from distance import straight_line_distance_km
from enrichments import toll_plazas_along_route, stays_and_food_for_itinerary
from itinerary import order_stops
from narrative import build_narrative
from speciality import get_specialities
from feasibility import (
    assess as assess_days, day_budget, day_load, pack_days, split_by_what_fits,
    travel_hours, visit_hours,
    OVERRUN_TOLERANCE,
)
from routing import get_driving_route, get_driving_route_with_geometry

load_dotenv()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_ITINERARY_TRIES = 3

FUEL_COST_PER_KM = 7
ROAD_DETOUR = 1.3
LONG_DRIVE_KMH = 50


# ----------------------------------------------------------------------
# Shared state
# ----------------------------------------------------------------------
class TripState(TypedDict, total=False):
    # --- inputs (set by the API layer before the graph runs) ---
    source: str
    destination: str
    travel_date: str
    travel_mode: str                 # "public_transport" | "own_vehicle"
    num_days: int | None
    num_people: int | None
    source_geo: dict                 # {lat, lon, display_name}
    dest_geo: dict                   # a real place OR the picked stops' centroid
    stops: list[dict]                # [{name, lat, lon, category, blurb, ...}] — [] = point-to-point

    # --- itinerary reasoning ---
    feasibility: dict                # is num_days sensible for these places?
    deferred: list[dict]             # places that don't fit the days available
    specialities: dict               # what the destination is famous for
    itinerary: list[dict]            # flat, ordered, day-numbered  [{day, name, lat, lon, ...}]
    itinerary_notes: list[dict]      # [{day, rationale}] — the "why this day" text
    itinerary_error: str             # last validation failure, fed back into the re-prompt
    itinerary_fatal: bool            # the LLM failure won't change on retry (quota/key)
    itinerary_tries: int
    itinerary_source: str            # "llm" | "repaired" | "fallback"

    # --- produced by later nodes ---
    itinerary_stays: list[dict]         # per overnight-stop food + hotel suggestions
    transport: dict
    drive_geometry: list                # [[lat, lon], ...] downsampled road path (own-vehicle)
    drive_hours: float
    tolls: dict                        # toll plazas on the route + car-cost estimate (own-vehicle)
    offers: list[dict]                  # optional "want food / rest stop?" prompts for the UI
    return_transport: dict              # the trip back — same shape as `transport`, plus from/to labels
    costs: dict
    result: dict
    node_log: Annotated[list[str], operator.add]


# ----------------------------------------------------------------------
# Gemini structured-output schema for the itinerary
# ----------------------------------------------------------------------
class _Day(BaseModel):
    day: int = Field(description="day number, starting at 1, no gaps")
    stops: list[str] = Field(description="names of the places to cover this day, EXACTLY as given in the input")
    rationale: str = Field(description="1-2 sentences: WHY these places, this day (grouping, pacing, travel time, time-of-day)")


class _ItineraryPlan(BaseModel):
    days: list[_Day]


_llm = ChatGoogleGenerativeAI(model=MODEL_NAME, google_api_key=os.getenv("GEMINI_API_KEY"))
_planner = _llm.with_structured_output(_ItineraryPlan)

_SYSTEM = (
    "You are an India travel planner. You lay out a practical day-by-day route "
    "through a set of places, the way an experienced local guide would.\n"
    "\n"
    "You will be told, for each place, how many hours a visit really takes and "
    "how far it is from the others in DRIVING HOURS. Plan against those numbers "
    "- a day that looks balanced on paper but needs 13 hours of driving and "
    "sightseeing is a bad plan.\n"
    "\n"
    "Rules you MUST follow:\n"
    "- use EVERY place exactly once; do not invent or drop places\n"
    "- day numbers are 1,2,3,... with no gaps, and never more than the trip length\n"
    "- KEEP EACH DAY WITHIN ITS HOUR BUDGET. Count the visit hours of its places "
    "PLUS the driving between them PLUS the drive in from where the previous "
    "night was spent (you sleep near the last place of the day)\n"
    "- do NOT spread places thinly just to fill the days. Fewer, fuller days "
    "with real rest beat every day half-used\n"
    "- group places that are close together; never zig-zag back to a region "
    "you have already left\n"
    "- the arrival day is short - most of it goes on getting there\n"
    "- a place far from the rest earns its own day for the transfer\n"
    "- wildlife parks and sunrise viewpoints are MORNING-FIRST: put them at "
    "the start of their day and say so in the rationale"
)


# errors that will never come good on a retry: exhausted quota, rate limits,
# a rejected key. Anything else (a timeout, a malformed answer) is worth a
# second go.
_FATAL_LLM_MARKERS = (
    "quota", "resource_exhausted", "rate limit", "429",
    "api key", "permission_denied", "unauthenticated", "401", "403",
)


def _is_fatal_llm_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(m in text for m in _FATAL_LLM_MARKERS)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _prompt(state: TripState) -> str:
    stops = state["stops"]
    days = state.get("num_days") or max(1, min(len(stops), 5))
    src = state["source_geo"]

    lines = []
    for s in stops:
        d_from_src = round(straight_line_distance_km(src["lat"], src["lon"], s["lat"], s["lon"]))
        # nearest others in DRIVING HOURS, which is what actually constrains a
        # day. Kilometres alone don't tell the model what fits in an afternoon.
        near = sorted(
            (
                (travel_hours(s, o), o["name"])
                for o in stops
                if o["name"] != s["name"]
            ),
        )[:3]
        near_txt = ", ".join(f"{n} {hrs:.1f}h" for hrs, n in near)
        lines.append(
            f"- {s['name']} ({s.get('category', 'place')}) - needs about "
            f"{visit_hours(s):.1f}h on site; {d_from_src} km from the start; "
            f"nearest others by road: {near_txt or 'n/a'}"
        )

    budgets = ", ".join(
        f"day {d} = {day_budget(d, days):.1f}h" for d in range(1, min(days, 8) + 1)
    )

    parts = [
        f"Trip: {state['source']} -> {state['destination']}, {days} day(s), "
        f"travelling by {'own vehicle' if state['travel_mode'] == 'own_vehicle' else 'public transport'}.",
        "",
        "Places to cover:",
        *lines,
        "",
        f"Hours available per day ({budgets}"
        + (", later days = 9.0h" if days > 8 else "")
        + "). Day 1 is short because you arrive; the last day is short because you leave.",
        "",
        f"Produce a plan of at most {days} day(s).",
    ]

    # If the day count doesn't fit the places, say so here too — otherwise the
    # model quietly crams and we only reject it on the way out.
    fit = state.get("feasibility") or {}
    if fit.get("verdict") == "too_short" and not fit.get("deferred"):
        parts += ["", (
            f"NOTE: these places really want about {fit['needed_days']} days and only "
            f"{days} are available. Don't pretend otherwise - build the most sensible "
            f"{days}-day plan you can, group aggressively, and say in the rationale "
            f"which days are heavy."
        )]
    elif fit.get("verdict") == "too_long":
        parts += ["", (
            f"NOTE: there is more time ({days} days) than these places need "
            f"(about {fit['needed_days']}). Use about {fit['needed_days']} days and "
            f"stop there - every day you do use must have at least one place in it. "
            f"Don't stretch the places thin or leave blank days to fill the trip; "
            f"say in the rationale that the remaining days are free."
        )]

    if state.get("itinerary_error"):
        parts += ["", f"Your previous attempt was rejected: {state['itinerary_error']}. Fix it."]
    return "\n".join(parts)


def _validate(plan: _ItineraryPlan, stop_names: list[str], num_days: int | None) -> str | None:
    want = {_norm(n) for n in stop_names}
    got: list[str] = []
    for d in plan.days:
        got += [_norm(s) for s in d.stops]

    if sorted(got) != sorted(want):
        missing = want - set(got)
        extra = set(got) - want
        bits = []
        if missing:
            bits.append(f"missing: {', '.join(missing)}")
        if extra:
            bits.append(f"not in the list: {', '.join(extra)}")
        if not bits:
            bits.append("some place is used more than once")
        return "every place must appear exactly once (" + "; ".join(bits) + ")"

    nums = [d.day for d in plan.days]
    if nums != list(range(1, len(nums) + 1)):
        return "day numbers must be 1, 2, 3, ... with no gaps or repeats"

    # An empty DAY 1 is honest — on a long haul the arrival really is the day's
    # work. An empty day anywhere else is padding: told not to spread places
    # thinly, the model would otherwise hand back blank days to fill the trip
    # length, which reads as a broken plan rather than a restful one.
    last_with_stops = max((d.day for d in plan.days if d.stops), default=0)
    for d in plan.days:
        if d.stops or d.day == 1:
            continue
        # A blank day AFTER the sightseeing ends is a genuine free day, and
        # gets labelled as one. A blank day in the MIDDLE is padding — the
        # model stretching two places across a week of half-used days.
        if d.day < last_with_stops:
            return (
                f"day {d.day} has no places in it but later days do - don't pad "
                f"the middle of the plan with empty days"
            )
    if num_days and len(plan.days) > num_days:
        return f"use at most {num_days} days"
    return None


def _fill_trip_days(notes: list[dict], flat: list[dict],
                    num_days: int | None) -> list[dict]:
    """Make sure every day the traveller booked appears in the plan.

    Asked for 3 days with two nearby places, the planner will sensibly fit them
    into 2 — and then day 3 was simply ABSENT, so the itinerary stopped at day 2
    and looked truncated. A day with nothing scheduled is a real part of the
    trip (you're still there, still eating, still heading home), so it gets an
    entry that says so rather than disappearing.
    """
    if not num_days or num_days < 1:
        return notes

    have = {n["day"] for n in notes}
    with_stops = {s["day"] for s in flat}
    last_with_stops = max(with_stops) if with_stops else 0

    out = list(notes)
    for day in range(1, num_days + 1):
        if day in have:
            continue
        if day == 1:
            rationale = "Arrival day — getting there is the day's work."
        elif day > last_with_stops:
            rationale = (
                "Nothing scheduled — a free day to take slowly, or to head back early."
            )
        else:
            # a gap before the sightseeing ends shouldn't happen (validation
            # rejects interior blanks), but label it honestly if it does
            rationale = "Nothing scheduled for this day."
        out.append({"day": day, "rationale": rationale})

    out.sort(key=lambda n: n["day"])
    return out


def _practicality_error(flat: list[dict], num_days: int | None) -> str | None:
    """Reject a day nobody could actually do.

    The hour budget is the whole point of planning practically, so it has to be
    CHECKED, not just requested in the prompt — an LLM told "keep days
    realistic" will still hand back a day with 13 hours in it. Feeding the
    specific day back gives the retry something concrete to fix.

    Skipped when the trip is knowingly too short for its places: there we've
    already told the model to cram, and rejecting its best effort three times
    would only push us to the deterministic fallback.
    """
    if not flat:
        return None
    by_day: dict[int, list[dict]] = {}
    for st in flat:
        by_day.setdefault(st["day"], []).append(st)

    total_days = num_days or max(by_day)
    for day in sorted(by_day):
        # A single place can't be split, so an over-long one-stop day is not a
        # planning mistake — there is nothing to move, and the error would ask
        # for the impossible. Munnar simply takes six hours.
        if len(by_day[day]) < 2:
            continue
        base = by_day[day - 1][-1] if (day - 1) in by_day else None
        load = day_load(by_day[day], base)
        budget = day_budget(day, total_days)
        if load > budget * OVERRUN_TOLERANCE:
            names = ", ".join(x["name"] for x in by_day[day])
            return (
                f"day {day} needs about {load:.1f} hours ({names}) but only "
                f"{budget:.1f} are available - move something to a lighter day"
            )
    return None


def _flatten(plan: _ItineraryPlan, stops: list[dict]) -> tuple[list[dict], list[dict]]:
    by_norm = {_norm(s["name"]): s for s in stops}
    flat: list[dict] = []
    notes: list[dict] = []
    for d in plan.days:
        notes.append({"day": d.day, "rationale": d.rationale.strip()})
        for name in d.stops:
            base = by_norm.get(_norm(name))
            if base:
                flat.append({**base, "day": d.day})
    return flat, notes


# ----------------------------------------------------------------------
# Progress stages — what the UI shows while the plan is still being built
# ----------------------------------------------------------------------
# Each graph node maps to one user-facing stage. The node_log the graph
# already accumulates tells us exactly which of these are finished, so the
# progress animation can report real work instead of guessing from a timer.
_NODE_STAGE: dict[str, tuple[str, str]] = {
    "resolve": ("start", "Getting your trip ready"),
    "cluster_itinerary": ("itinerary", "Laying out your day-by-day route"),
    "fallback_itinerary": ("itinerary", "Laying out your day-by-day route"),
    "plan_stays": ("stays", "Finding food and places to stay"),
    "find_specialities": ("specialities", "Looking up local specialities"),
    "plan_transport": ("transport", "Checking how to get there"),
    "assess_drive": ("drive", "Mapping the drive and its stops"),
    "plan_return_leg": ("return", "Planning the way back"),
    "estimate_costs": ("costs", "Adding up the budget"),
    "assemble": ("done", "Finishing up"),
}


def plan_stages(travel_mode: str, has_stops: bool) -> list[dict]:
    """The stages this particular trip will go through, in order — so the UI
    can show a real checklist rather than a fixed list of guesses."""
    keys = ["start"]
    if has_stops:
        keys += ["itinerary", "stays"]
    keys.append("specialities")
    keys.append("transport")
    if travel_mode == "own_vehicle":
        keys.append("drive")
    keys += ["return", "costs"]
    label = {k: l for k, l in _NODE_STAGE.values()}
    return [{"key": k, "label": label[k]} for k in keys]


def stages_done(state: TripState) -> list[str]:
    """Stage keys genuinely finished, read from the state rather than from the
    node log: cluster_itinerary logs a line for every FAILED try too, so
    "it ran" and "it produced something" are not the same thing."""
    log = [e.split("(")[0].strip() for e in (state.get("node_log") or [])]
    done: list[str] = []
    if "resolve" in log:
        done.append("start")
    if state.get("itinerary"):
        done.append("itinerary")
    if "plan_stays" in log:              # may legitimately yield an empty list
        done.append("stays")
    if "find_specialities" in log:
        done.append("specialities")
    if state.get("transport"):
        done.append("transport")
    if "assess_drive" in log:
        done.append("drive")
    if "plan_return_leg" in log:
        done.append("return")
    if state.get("costs"):
        done.append("costs")
    return done


# ----------------------------------------------------------------------
# Nodes
# ----------------------------------------------------------------------
def resolve(state: TripState) -> dict:
    """Endpoints are already geocoded by the API layer.

    This is also where we work out whether the trip length is sensible for the
    places picked — before any planning, so the itinerary prompt can be told
    the truth ("these want 5 days, you have 3") and the traveller can be asked
    about it rather than silently handed a plan that doesn't work.
    """
    src = state["source_geo"]
    stops = state.get("stops") or []
    fit = assess_days(stops, state.get("num_days"), src["lat"], src["lon"])

    out: dict = {"node_log": ["resolve"], "itinerary_tries": 0, "feasibility": fit}

    # Too many places for the days available? Plan the ones that FIT and set
    # the rest aside. Cramming them all in produced a real 15-hour departure
    # day that the model itself described as "extremely heavy" — which is not
    # a plan anyone can follow, and it made the food, hotels and budget for
    # that day wrong as well. The traveller is told what was deferred and can
    # add days or drop places.
    if fit.get("verdict") == "too_short":
        fits, deferred = split_by_what_fits(
            stops, state.get("num_days"), src["lat"], src["lon"]
        )
        if fits and deferred:
            out["stops"] = fits
            out["deferred"] = deferred
            fit = dict(fit)
            fit["deferred"] = [d["name"] for d in deferred]
            fit["message"] = (
                f"{fit['places']} places don't fit into {fit['given_days']} "
                f"day{'s' if fit['given_days'] != 1 else ''} — at a comfortable pace "
                f"they need about {fit['needed_days']}. I've planned the "
                f"{len(fits)} that fit and left out "
                + ", ".join(d["name"] for d in deferred)
                + f". Add {fit['needed_days'] - fit['given_days']} more day"
                + ("s" if fit["needed_days"] - fit["given_days"] != 1 else "")
                + " to include them, or keep the shorter plan."
            )
            out["feasibility"] = fit
    return out


def cluster_itinerary(state: TripState) -> dict:
    """Ask Gemini for a reasoned day-by-day plan, then validate it. On failure
    we leave `itinerary_error` set and the conditional edge loops us back."""
    tries = state.get("itinerary_tries", 0) + 1
    stop_names = [s["name"] for s in state["stops"]]
    try:
        plan: _ItineraryPlan = _planner.invoke([
            ("system", _SYSTEM),
            ("human", _prompt(state)),
        ])
        err = _validate(plan, stop_names, state.get("num_days"))
        if err:
            return {"itinerary_tries": tries, "itinerary_error": err,
                    "node_log": [f"cluster_itinerary(try {tries}: {err[:40]})"]}
        flat, notes = _flatten(plan, state["stops"])

        # A plan that doesn't fit the hours isn't a plan. This used to be
        # skipped when the trip was "too_short", on the reasoning that we'd
        # already asked the model to cram — which is precisely how a 15-hour
        # day reached a real traveller. The stop list is now trimmed to what
        # fits (see `resolve`), so this check applies always.
        impractical = _practicality_error(flat, state.get("num_days"))
        if impractical:
            return {"itinerary_tries": tries, "itinerary_error": impractical,
                    "node_log": [f"cluster_itinerary(try {tries}: {impractical[:40]})"]}

        return {
            "itinerary": flat,
            "itinerary_notes": _fill_trip_days(notes, flat, state.get("num_days")),
            "itinerary_error": "", "itinerary_tries": tries, "itinerary_fatal": False,
            "itinerary_source": "llm" if tries == 1 else "repaired",
            "node_log": [f"cluster_itinerary(ok, try {tries})"],
        }
    except Exception as e:  # noqa: BLE001 — LLM/network failure -> let the fallback handle it
        return {
            "itinerary_tries": tries,
            "itinerary_error": f"planner error: {e}",
            # A blown quota or a bad key answers the same way every time.
            # Retrying twice more just makes the traveller wait longer for
            # the deterministic plan we were always going to fall back to.
            "itinerary_fatal": _is_fatal_llm_error(e),
            "node_log": [f"cluster_itinerary(try {tries}: exception)"],
        }


def fallback_itinerary(state: TripState) -> dict:
    """Deterministic plan for when Gemini can't produce a valid one in budget.

    This used to divide the places evenly across the days
    (`itinerary.split_into_days`), which is how you end up with a tiger reserve
    and a hill station 120 km apart sharing an afternoon. It now packs days by
    the hours they actually cost, so even the fallback is a plan a person
    could follow.
    """
    src = state["source_geo"]
    ordered = order_stops(state["stops"], src["lat"], src["lon"])
    packed = pack_days(ordered, state.get("num_days"))

    flat: list[dict] = []
    notes: list[dict] = []
    for day, group in enumerate(packed, start=1):
        base = packed[day - 2][-1] if day > 1 else None
        for st in group:
            flat.append({**st, "day": day})
        notes.append({
            "day": day,
            "rationale": (
                f"About {day_load(group, base):.1f} hours with the driving included - "
                f"grouped so the day is doable rather than evenly filled."
            ),
        })
    return {
        "itinerary": flat,
        "itinerary_notes": _fill_trip_days(notes, flat, state.get("num_days")),
        "itinerary_source": "fallback",
        "node_log": ["fallback_itinerary"],
    }


def find_specialities(state: TripState) -> dict:
    """What the destination is famous for: the food, the craft, the one thing
    people travel for. Depends on nothing but the destination name, so it runs
    on the fan-out alongside the itinerary and transport branches, and it's
    cached per destination — usually free on the second trip to a region."""
    try:
        data = get_specialities(state.get("destination") or "")
    except Exception as e:  # noqa: BLE001 — an extra is never worth failing over
        print(f"speciality lookup failed: {type(e).__name__}: {e}")
        data = {}
    return {"specialities": data, "node_log": ["find_specialities"]}


def plan_stays(state: TripState) -> dict:
    """Food + a hotel near where the traveller actually ends up each night —
    independent of how they got there, so it runs for both travel modes."""
    try:
        stays = stays_and_food_for_itinerary(
            state.get("itinerary") or [], state.get("num_days")
        )
    except Exception:  # noqa: BLE001 — Gemini/Nominatim hiccup shouldn't sink the plan
        stays = []
    return {"itinerary_stays": stays, "node_log": ["plan_stays"]}


def _drive_plan(src: dict, dst: dict) -> dict:
    route = get_driving_route(src["lat"], src["lon"], dst["lat"], dst["lon"])
    if route:
        return {"mode": "drive", "drive": {**route, "estimated": False}}
    crow = straight_line_distance_km(src["lat"], src["lon"], dst["lat"], dst["lon"])
    approx_km = round(crow * ROAD_DETOUR, 1)
    return {"mode": "drive", "drive": {
        "distance_km": approx_km, "duration_hr": round(approx_km / LONG_DRIVE_KMH, 1),
        "estimated": True,
    }}


def _transport_unavailable(travel_mode: str, exc: Exception) -> dict:
    """A transport section that couldn't be built, in the shape the UI already
    knows how to render — so the plan still shows, with an honest gap in it."""
    note = (f"Couldn't work out the transport for this trip right now "
            f"({type(exc).__name__}). Everything else below is still good — "
            f"try re-planning in a few minutes.")
    if travel_mode == "own_vehicle":
        return {"mode": "drive", "drive": {}, "unavailable": True, "note": note}
    empty = {"all_options": [], "working_options": [], "recommended": None,
             "data_unavailable": True, "note": note}
    return {"train": {**empty, "mode": "train"},
            "bus": {**empty, "mode": "bus"},
            "flight": {**empty, "mode": "flight"}}


def plan_transport(state: TripState) -> dict:
    """Transport for the outbound leg.

    Everything here is best-effort. A traveller who picked their places and
    waited for a plan should still get the itinerary, the map and the budget
    even if every transport lookup is having a bad day — losing the whole
    plan because one provider is rate-limited is the worst possible trade.
    """
    src, dst = state["source_geo"], state["dest_geo"]
    try:
        if state["travel_mode"] == "own_vehicle":
            transport = _drive_plan(src, dst)
        else:
            # check_all_modes already isolates train/bus/flight from each
            # other; this catches anything that escapes all three.
            transport = check_all_modes(
                src["lat"], src["lon"], dst["lat"], dst["lon"],
                travel_date=state["travel_date"], destination_name=state["destination"],
            )
    except Exception as e:  # noqa: BLE001
        return {
            "transport": _transport_unavailable(state["travel_mode"], e),
            "node_log": [f"plan_transport(failed: {type(e).__name__})"],
        }
    return {"transport": transport, "node_log": ["plan_transport"]}


def _downsample(coords: list[list[float]], keep: int = 120) -> list[list[float]]:
    """ORS [lon,lat] path -> a lighter [lat,lon] path for the map + enrich calls."""
    if not coords:
        return []
    step = max(1, len(coords) // keep)
    out = [[coords[i][1], coords[i][0]] for i in range(0, len(coords), step)]
    if out and out[-1] != [coords[-1][1], coords[-1][0]]:
        out.append([coords[-1][1], coords[-1][0]])
    return out


def assess_drive(state: TripState) -> dict:
    """
    Own-vehicle only. Pull the real road GEOMETRY (so later 'food/fuel/stay on
    the way' lookups have a path to sample), and decide which optional offers
    to surface: food is offered for any real drive; a rest-stop is only
    offered when the drive is genuinely long.
    """
    src, dst = state["source_geo"], state["dest_geo"]
    try:
        geo = get_driving_route_with_geometry(src["lat"], src["lon"], dst["lat"], dst["lon"])
    except Exception:  # noqa: BLE001 — no road geometry just means no route line
        geo = None

    drive = (state.get("transport") or {}).get("drive") or {}
    hours = drive.get("duration_hr") or (geo["duration_hr"] if geo else 0.0)
    polyline = _downsample(geo["coordinates"]) if geo else []

    # toll plazas on the way — shown automatically for own-vehicle, cost folded
    # into the budget (assumes a car; two-wheelers are usually exempt)
    try:
        tolls = toll_plazas_along_route(polyline)
    except Exception:  # noqa: BLE001 — Overpass hiccup shouldn't sink the plan
        tolls = {"plazas": [], "count": 0, "car_cost_one_way": 0, "car_cost_round_trip": 0}

    offers: list[dict] = []
    if hours >= 1.5:
        offers.append({
            "id": "food", "kind": "food", "status": "pending",
            "question": "Want me to find food stops along the way?",
        })
    if hours >= 6:
        offers.append({
            "id": "stay", "kind": "stay", "status": "pending",
            "reason": f"~{round(hours)} hr of driving",
            "question": f"That's ~{round(hours)} hr of driving — want a rest-stop hotel suggested on the way?",
        })

    return {
        "drive_geometry": polyline,
        "drive_hours": round(hours, 1),
        "tolls": tolls,
        "offers": offers,
        "node_log": ["assess_drive"],
    }


def _return_departure_date(state: TripState) -> str:
    """Best-guess date for the trip back — the outbound date plus however many
    days the trip runs, so train/flight schedule lookups check the right
    weekday instead of reusing the outbound one."""
    try:
        out = date.fromisoformat(state["travel_date"])
        return (out + timedelta(days=max(1, state.get("num_days") or 1))).isoformat()
    except (ValueError, KeyError):
        return state.get("travel_date", "")


def plan_return_leg(state: TripState) -> dict:
    try:
        return _plan_return_leg(state)
    except Exception as e:  # noqa: BLE001 — the way back is a bonus section
        print(f"return leg failed: {type(e).__name__}: {e}")
        return {"return_transport": {}, "node_log": [f"plan_return_leg(failed: {type(e).__name__})"]}


def _plan_return_leg(state: TripState) -> dict:
    """The trip back. It starts from wherever the traveller actually ends up —
    the last itinerary stop if any were picked, otherwise the destination —
    and ends at the original source. Own-vehicle gets the same drive-plan +
    toll treatment as the outbound leg; public transport gets a fresh
    train/bus/flight check in the reverse direction."""
    itinerary = state.get("itinerary") or []
    if itinerary:
        last = itinerary[-1]
        return_src = {"lat": last["lat"], "lon": last["lon"], "display_name": last["name"]}
        from_label = last["name"]
    else:
        return_src = state["dest_geo"]
        from_label = state["destination"]
    return_dst = state["source_geo"]
    to_label = state["source"]

    if state["travel_mode"] == "own_vehicle":
        transport = _drive_plan(return_src, return_dst)
        geo = get_driving_route_with_geometry(
            return_src["lat"], return_src["lon"], return_dst["lat"], return_dst["lon"]
        )
        drive = transport.get("drive") or {}
        hours = drive.get("duration_hr") or (geo["duration_hr"] if geo else 0.0)
        polyline = _downsample(geo["coordinates"]) if geo else []
        try:
            tolls = toll_plazas_along_route(polyline)
        except Exception:  # noqa: BLE001
            tolls = {"plazas": [], "count": 0, "car_cost_one_way": 0, "car_cost_round_trip": 0}
        transport["drive"]["geometry"] = polyline
        transport["drive_hours"] = round(hours, 1)
        transport["tolls"] = tolls
    else:
        transport = check_all_modes(
            return_src["lat"], return_src["lon"], return_dst["lat"], return_dst["lon"],
            travel_date=_return_departure_date(state), destination_name=to_label,
        )

    transport["from_label"] = from_label
    transport["to_label"] = to_label
    return {"return_transport": transport, "node_log": ["plan_return_leg"]}


def estimate_costs(state: TripState) -> dict:
    is_drive = state["travel_mode"] == "own_vehicle"
    drive_km = ((state.get("transport") or {}).get("drive") or {}).get("distance_km") if is_drive else None
    ret = state.get("return_transport") or {}
    return_km = (ret.get("drive") or {}).get("distance_km") if is_drive else None

    days = max(1, state.get("num_days") or 2)
    people = max(1, state.get("num_people") or 2)
    nights = max(0, days - 1)

    items: list[dict] = []
    if is_drive and drive_km:
        total_km = round(drive_km + (return_km if return_km is not None else drive_km))
        items.append({"label": "Fuel (round trip)", "amount": round(total_km * FUEL_COST_PER_KM),
                      "note": f"~Rs {FUEL_COST_PER_KM}/km x {total_km} km (there + back)"})
    tolls = state.get("tolls") or {}
    return_tolls = ret.get("tolls") or {} if is_drive else {}
    toll_total = (tolls.get("car_cost_one_way") or 0) + (return_tolls.get("car_cost_one_way") or 0)
    toll_count = (tolls.get("count") or 0) + (return_tolls.get("count") or 0)
    if is_drive and toll_count:
        items.append({"label": "Tolls (round trip)", "amount": toll_total,
                      "note": f"{toll_count} plaza(s), car, both ways"})
    items.append({"label": "Food", "amount": 400 * people * days,
                  "note": f"~Rs 400 x {people} people x {days} days"})
    items.append({"label": "Stay", "amount": 1500 * nights,
                  "note": f"~Rs 1500/night x {nights} night" + ("s" if nights != 1 else "")})

    return {"costs": {
        "items": items, "total": sum(i["amount"] for i in items),
        "assumptions": {"people": people, "days": days},
        "note": "Ball-park only. Excludes train/flight/bus tickets and activities.",
    }, "node_log": ["estimate_costs"]}


def assemble(state: TripState) -> dict:
    result = dict(state.get("transport") or {})
    if state.get("feasibility", {}).get("places"):
        result["feasibility"] = state["feasibility"]
    if state.get("deferred"):
        result["deferred"] = state["deferred"]
    if (state.get("specialities") or {}).get("specialities"):
        result["specialities"] = state["specialities"]
    if state.get("itinerary"):
        result["itinerary"] = state["itinerary"]
        result["itinerary_notes"] = state.get("itinerary_notes", [])
        result["itinerary_stays"] = state.get("itinerary_stays", [])
    if result.get("mode") == "drive":
        # copy rather than mutate: `assemble` is now also called on every
        # progress snapshot, and writing through to the state's own drive dict
        # from a reporting path is asking for trouble while the other branch
        # is still running
        drive = dict(result.get("drive") or {})
        drive["geometry"] = state.get("drive_geometry", [])
        result["drive"] = drive
        result["drive_hours"] = state.get("drive_hours")
        result["tolls"] = state.get("tolls") or {"plazas": [], "count": 0}
        result["offers"] = state.get("offers", [])
    # Only emit these once they hold something. An empty dict is TRUTHY in
    # JavaScript, so shipping `"costs": {}` in a progress snapshot made the UI
    # render its budget panel against no data — which crashed the whole page.
    # Absent means "not ready yet"; present means "safe to render".
    if state.get("return_transport"):
        result["return"] = state["return_transport"]
    if state.get("costs"):
        result["costs"] = state["costs"]

    # The plan as a reader wants it: a running schedule with clock times. Built
    # LAST so it can draw on the transport, the stays and the itinerary
    # together, and from the same hour figures the days were packed with — so
    # the prose can't contradict the plan it describes.
    try:
        result["narrative"] = build_narrative(
            result,
            source=state.get("source") or "",
            destination=state.get("destination") or "",
            travel_mode=state.get("travel_mode") or "public_transport",
            num_days=state.get("num_days"),
        )
    except Exception as e:  # noqa: BLE001 — prose is a bonus, never a blocker
        print(f"narrative build failed: {type(e).__name__}: {e}")
        result["narrative"] = []
    return {"result": result, "node_log": ["assemble"]}


# ----------------------------------------------------------------------
# Conditional edges (the routing logic)
# ----------------------------------------------------------------------
def after_resolve(state: TripState) -> list[str]:
    """Fan out: the itinerary reasoning and the transport lookups need nothing
    from each other, so they run as two concurrent branches. The itinerary
    branch is Gemini + Nominatim bound and the transport branch is timetable +
    Overpass bound, so overlapping them cuts most of their combined wall time.
    They rejoin at plan_return_leg, which needs both."""
    branches = ["plan_transport", "find_specialities"]
    if state.get("stops"):
        branches.insert(0, "cluster_itinerary")
    return branches


def after_cluster(state: TripState) -> Literal["cluster_itinerary", "fallback_itinerary", "plan_stays"]:  # noqa: E501
    if not state.get("itinerary_error"):
        return "plan_stays"                   # valid plan
    if state.get("itinerary_fatal"):
        return "fallback_itinerary"           # quota/key — retrying changes nothing
    if state.get("itinerary_tries", 0) < MAX_ITINERARY_TRIES:
        return "cluster_itinerary"            # retry with the error fed back
    return "fallback_itinerary"               # give up on the LLM, use the deterministic split


def after_transport(state: TripState) -> Literal["assess_drive", "plan_return_leg"]:
    # only own-vehicle drives need the road geometry + food/rest-stop offers
    return "assess_drive" if state["travel_mode"] == "own_vehicle" else "plan_return_leg"


def _ordered_nodes(has_stops: bool) -> list[str]:
    """Unused at runtime — kept as the readable statement of branch order."""
    itinerary = ["cluster_itinerary", "fallback_itinerary", "plan_stays"] if has_stops else []
    return ["resolve", *itinerary, "plan_transport", "assess_drive",
            "plan_return_leg", "estimate_costs", "assemble"]


# ----------------------------------------------------------------------
# Build + compile
# ----------------------------------------------------------------------
def _build_graph():
    g = StateGraph(TripState)
    g.add_node("resolve", resolve)
    g.add_node("cluster_itinerary", cluster_itinerary)
    g.add_node("fallback_itinerary", fallback_itinerary)
    g.add_node("plan_stays", plan_stays)
    g.add_node("find_specialities", find_specialities)
    g.add_node("plan_transport", plan_transport)
    g.add_node("assess_drive", assess_drive)
    # defer=True makes this a BARRIER: it waits until both branches above are
    # finished instead of firing once per incoming edge. Without it the two
    # branches, which are different lengths, would each trigger it and the
    # return leg would be planned twice — verified, it really does run twice.
    g.add_node("plan_return_leg", plan_return_leg, defer=True)
    g.add_node("estimate_costs", estimate_costs)
    g.add_node("assemble", assemble)

    g.add_edge(START, "resolve")
    # resolve fans out into the itinerary branch and the transport branch
    g.add_conditional_edges("resolve", after_resolve,
                            ["cluster_itinerary", "plan_transport", "find_specialities"])
    # branch A — itinerary, then the food/stay picks that depend on it
    g.add_conditional_edges("cluster_itinerary", after_cluster)
    g.add_edge("fallback_itinerary", "plan_stays")
    g.add_edge("plan_stays", "plan_return_leg")
    # branch B — transport, plus the drive assessment for own-vehicle trips
    g.add_conditional_edges("plan_transport", after_transport)
    g.add_edge("assess_drive", "plan_return_leg")
    # rejoins at the same barrier as the other branches
    g.add_edge("find_specialities", "plan_return_leg")
    g.add_edge("plan_return_leg", "estimate_costs")
    g.add_edge("estimate_costs", "assemble")
    g.add_edge("assemble", END)
    return g.compile()


_GRAPH = _build_graph()


def plan_itinerary_only(
    *,
    source: str,
    destination: str,
    travel_mode: str,
    num_days: int | None,
    source_geo: dict,
    stops: list[dict],
) -> dict:
    """Re-plan just the day-by-day route for a changed set of stops.

    Used when the traveller edits their places in chat ("also include Hampi",
    "drop Varkala"). Only the itinerary needs redoing — the route to the region,
    its timetables and the budget are all still valid — and rebuilding those
    would cost minutes for a change that takes seconds.

    It calls the SAME nodes the full graph uses (resolve -> cluster -> retry ->
    fallback), so the planning rules and the hour budgets can't quietly diverge
    between the two paths.
    """
    state: TripState = {
        "source": source, "destination": destination, "travel_mode": travel_mode,
        "num_days": num_days, "source_geo": source_geo, "stops": stops,
        "travel_date": "", "node_log": [],
    }
    state.update(resolve(state))

    for _ in range(MAX_ITINERARY_TRIES):
        state.update(cluster_itinerary(state))
        if not state.get("itinerary_error"):
            break
        if state.get("itinerary_fatal"):
            break
    if not state.get("itinerary"):
        state.update(fallback_itinerary(state))

    return {
        "itinerary": state.get("itinerary") or [],
        "itinerary_notes": state.get("itinerary_notes") or [],
        "feasibility": state.get("feasibility") or {},
        "source": state.get("itinerary_source") or "fallback",
    }


def partial_result(state: TripState) -> dict:
    """Whatever of the plan is usable RIGHT NOW, in the same shape as the
    finished result. `assemble` is already tolerant of missing pieces, so the
    half-built plan renders with exactly the components the UI uses at the
    end — the itinerary shows as soon as it exists, the map fills in when
    transport lands, and nothing has to be re-done when the rest arrives."""
    try:
        return assemble(state)["result"]
    except Exception:  # noqa: BLE001 — a progress snapshot must never break the run
        return {}


def run_trip_plan(
    *,
    source: str,
    destination: str,
    travel_date: str,
    travel_mode: str,
    num_days: int | None,
    num_people: int | None,
    source_geo: dict,
    dest_geo: dict,
    stops: list[dict] | None,
    on_progress=None,
) -> dict:
    """Run the agent to completion; return the API `result` dict.

    `on_progress(partial, done_stages)` is called after each super-step of the
    graph with the plan as it stands, so the caller can publish it while the
    rest is still being worked out. Streaming in `values` mode hands us the
    whole accumulated state each time, which is all a snapshot needs.
    """
    payload = {
        "source": source, "destination": destination, "travel_date": travel_date,
        "travel_mode": travel_mode, "num_days": num_days, "num_people": num_people,
        "source_geo": source_geo, "dest_geo": dest_geo, "stops": stops or [],
        "node_log": [],
    }

    if on_progress is None:
        return _GRAPH.invoke(payload)["result"]

    # `updates` rather than `values`, deliberately. A `values` snapshot is only
    # emitted at the end of a SUPER-STEP, and the two branches share one — so
    # the itinerary (≈2s) would sit unpublished until the transport lookups
    # (minutes, on a cold region) finished with it, which defeats the whole
    # point of streaming. `updates` fires as each node returns. The trade is
    # that it hands us only that node's own slice of state, so we accumulate
    # the state ourselves; `node_log` is the one reducer-backed key, appended
    # exactly as the graph's own operator.add would.
    merged: TripState = dict(payload)
    for chunk in _GRAPH.stream(payload, stream_mode="updates"):
        for update in (chunk or {}).values():
            if not isinstance(update, dict):
                continue
            for key, value in update.items():
                if key == "node_log":
                    merged["node_log"] = list(merged.get("node_log") or []) + list(value)
                else:
                    merged[key] = value
        try:
            on_progress(partial_result(merged), stages_done(merged))
        except Exception as e:  # noqa: BLE001 — never let reporting kill planning
            print(f"progress callback failed: {type(e).__name__}: {e}")

    # `assemble` is the last node, so its update carried the finished result
    return merged.get("result") or partial_result(merged)


if __name__ == "__main__":
    from geocoding import geocode

    s = geocode("Guntur, Andhra Pradesh")
    picks = [
        {"name": "Munnar", "lat": 10.0889, "lon": 77.0595, "category": "hill station",
         "blurb": "tea hills"},
        {"name": "Fort Kochi", "lat": 9.9658, "lon": 76.2422, "category": "fort",
         "blurb": "colonial waterfront"},
        {"name": "Alleppey Backwaters", "lat": 9.4981, "lon": 76.3388, "category": "backwater",
         "blurb": "houseboats"},
        {"name": "Periyar National Park", "lat": 9.4621, "lon": 77.2378, "category": "wildlife",
         "blurb": "tiger reserve"},
    ]
    clat = sum(p["lat"] for p in picks) / len(picks)
    clon = sum(p["lon"] for p in picks) / len(picks)
    out = run_trip_plan(
        source="Guntur", destination="Kerala", travel_date="2026-09-22",
        travel_mode="own_vehicle", num_days=4, num_people=2,
        source_geo=s, dest_geo={"lat": clat, "lon": clon, "display_name": "Kerala"},
        stops=picks,
    )
    for d in out.get("itinerary_notes", []):
        stops_that_day = [x["name"] for x in out["itinerary"] if x["day"] == d["day"]]
        print(f"Day {d['day']}: {', '.join(stops_that_day)}")
        print(f"   why: {d['rationale']}")
    print("costs total:", out["costs"]["total"])
