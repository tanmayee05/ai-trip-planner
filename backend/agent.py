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
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import START, END, StateGraph
from pydantic import BaseModel, Field

from connectivity import check_all_modes
from distance import straight_line_distance_km
from enrichments import toll_plazas_along_route
from itinerary import build_itinerary  # deterministic fallback
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
    itinerary: list[dict]            # flat, ordered, day-numbered  [{day, name, lat, lon, ...}]
    itinerary_notes: list[dict]      # [{day, rationale}] — the "why this day" text
    itinerary_error: str             # last validation failure, fed back into the re-prompt
    itinerary_tries: int
    itinerary_source: str            # "llm" | "repaired" | "fallback"

    # --- produced by later nodes ---
    transport: dict
    drive_geometry: list                # [[lat, lon], ...] downsampled road path (own-vehicle)
    drive_hours: float
    tolls: dict                        # toll plazas on the route + car-cost estimate (own-vehicle)
    offers: list[dict]                  # optional "want food / rest stop?" prompts for the UI
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
    "through a set of places. Rules you MUST follow:\n"
    "- use EVERY place exactly once; do not invent or drop places\n"
    "- day numbers are 1,2,3,... with no gaps, and never more than the trip length\n"
    "- group places that are geographically close on the same day; minimise backtracking\n"
    "- the arrival day is lighter (fewer places, closest to the entry point)\n"
    "- a place far from the rest gets its own day for the transfer + a short evening stop\n"
    "- for wildlife parks / sunrise viewpoints, note in the rationale that it is a morning-first activity"
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _prompt(state: TripState) -> str:
    stops = state["stops"]
    days = state.get("num_days") or max(1, min(len(stops), 5))
    src = state["source_geo"]

    lines = []
    for s in stops:
        d_from_src = round(straight_line_distance_km(src["lat"], src["lon"], s["lat"], s["lon"]))
        near = sorted(
            ((round(straight_line_distance_km(s["lat"], s["lon"], o["lat"], o["lon"])), o["name"])
             for o in stops if o["name"] != s["name"]),
        )[:3]
        near_txt = ", ".join(f"{n} {km}km" for km, n in near)
        lines.append(
            f"- {s['name']} ({s.get('category', 'place')}) — {d_from_src} km from the start; "
            f"nearest others: {near_txt or 'n/a'}"
        )

    parts = [
        f"Trip: {state['source']} -> {state['destination']}, {days} day(s), "
        f"travelling by {'own vehicle' if state['travel_mode'] == 'own_vehicle' else 'public transport'}.",
        "",
        "Places to cover:",
        *lines,
        "",
        f"Produce a plan of at most {days} day(s).",
    ]
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
    if num_days and len(plan.days) > num_days:
        return f"use at most {num_days} days"
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
# Nodes
# ----------------------------------------------------------------------
def resolve(state: TripState) -> dict:
    """Endpoints are already geocoded by the API layer. This node just marks
    the run started (Step C will move geocoding + fuel-stop lookup here)."""
    return {"node_log": ["resolve"], "itinerary_tries": 0}


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
        return {
            "itinerary": flat, "itinerary_notes": notes,
            "itinerary_error": "", "itinerary_tries": tries,
            "itinerary_source": "llm" if tries == 1 else "repaired",
            "node_log": [f"cluster_itinerary(ok, try {tries})"],
        }
    except Exception as e:  # noqa: BLE001 — LLM/network failure -> let the fallback handle it
        return {"itinerary_tries": tries, "itinerary_error": f"planner error: {e}",
                "node_log": [f"cluster_itinerary(try {tries}: exception)"]}


def fallback_itinerary(state: TripState) -> dict:
    """Deterministic nearest-neighbour split (from itinerary.py) when Gemini
    can't produce a valid plan within the retry budget."""
    src = state["source_geo"]
    flat = build_itinerary(state["stops"], src["lat"], src["lon"], state.get("num_days"))
    days = sorted({s["day"] for s in flat})
    notes = [{"day": d, "rationale": "Grouped by nearest-neighbour order from your start point."}
             for d in days]
    return {
        "itinerary": flat, "itinerary_notes": notes, "itinerary_source": "fallback",
        "node_log": ["fallback_itinerary"],
    }


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


def plan_transport(state: TripState) -> dict:
    src, dst = state["source_geo"], state["dest_geo"]
    if state["travel_mode"] == "own_vehicle":
        transport = _drive_plan(src, dst)
    else:
        transport = check_all_modes(
            src["lat"], src["lon"], dst["lat"], dst["lon"],
            travel_date=state["travel_date"], destination_name=state["destination"],
        )
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
    geo = get_driving_route_with_geometry(src["lat"], src["lon"], dst["lat"], dst["lon"])

    drive = state["transport"].get("drive") or {}
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


def estimate_costs(state: TripState) -> dict:
    is_drive = state["travel_mode"] == "own_vehicle"
    drive_km = (state["transport"].get("drive") or {}).get("distance_km") if is_drive else None

    days = max(1, state.get("num_days") or 2)
    people = max(1, state.get("num_people") or 2)
    nights = max(0, days - 1)

    items: list[dict] = []
    if is_drive and drive_km:
        round_trip = round(drive_km * 2)
        items.append({"label": "Fuel (round trip)", "amount": round(round_trip * FUEL_COST_PER_KM),
                      "note": f"~Rs {FUEL_COST_PER_KM}/km x {round_trip} km"})
    tolls = state.get("tolls") or {}
    if is_drive and tolls.get("count"):
        items.append({"label": "Tolls (round trip)", "amount": tolls["car_cost_round_trip"],
                      "note": f"{tolls['count']} plaza(s), car, both ways"})
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
    result = dict(state["transport"])
    if state.get("itinerary"):
        result["itinerary"] = state["itinerary"]
        result["itinerary_notes"] = state.get("itinerary_notes", [])
    if result.get("mode") == "drive":
        result["drive"]["geometry"] = state.get("drive_geometry", [])
        result["drive_hours"] = state.get("drive_hours")
        result["tolls"] = state.get("tolls") or {"plazas": [], "count": 0}
        result["offers"] = state.get("offers", [])
    result["costs"] = state["costs"]
    return {"result": result, "node_log": ["assemble"]}


# ----------------------------------------------------------------------
# Conditional edges (the routing logic)
# ----------------------------------------------------------------------
def after_resolve(state: TripState) -> Literal["cluster_itinerary", "plan_transport"]:
    return "cluster_itinerary" if state.get("stops") else "plan_transport"


def after_cluster(state: TripState) -> Literal["cluster_itinerary", "fallback_itinerary", "plan_transport"]:
    if not state.get("itinerary_error"):
        return "plan_transport"               # valid plan
    if state.get("itinerary_tries", 0) < MAX_ITINERARY_TRIES:
        return "cluster_itinerary"            # retry with the error fed back
    return "fallback_itinerary"               # give up on the LLM, use the deterministic split


def after_transport(state: TripState) -> Literal["assess_drive", "estimate_costs"]:
    # only own-vehicle drives need the road geometry + food/rest-stop offers
    return "assess_drive" if state["travel_mode"] == "own_vehicle" else "estimate_costs"


# ----------------------------------------------------------------------
# Build + compile
# ----------------------------------------------------------------------
def _build_graph():
    g = StateGraph(TripState)
    g.add_node("resolve", resolve)
    g.add_node("cluster_itinerary", cluster_itinerary)
    g.add_node("fallback_itinerary", fallback_itinerary)
    g.add_node("plan_transport", plan_transport)
    g.add_node("assess_drive", assess_drive)
    g.add_node("estimate_costs", estimate_costs)
    g.add_node("assemble", assemble)

    g.add_edge(START, "resolve")
    g.add_conditional_edges("resolve", after_resolve)
    g.add_conditional_edges("cluster_itinerary", after_cluster)
    g.add_edge("fallback_itinerary", "plan_transport")
    g.add_conditional_edges("plan_transport", after_transport)
    g.add_edge("assess_drive", "estimate_costs")
    g.add_edge("estimate_costs", "assemble")
    g.add_edge("assemble", END)
    return g.compile()


_GRAPH = _build_graph()


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
) -> dict:
    """Run the agent to completion; return the API `result` dict."""
    final = _GRAPH.invoke({
        "source": source, "destination": destination, "travel_date": travel_date,
        "travel_mode": travel_mode, "num_days": num_days, "num_people": num_people,
        "source_geo": source_geo, "dest_geo": dest_geo, "stops": stops or [],
        "node_log": [],
    })
    return final["result"]


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
