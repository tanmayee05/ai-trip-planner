"""
Changing the stays in a finished plan, with the traveller in the loop.

WHY THIS IS A GRAPH AND NOT AN IF-STATEMENT
-------------------------------------------
"Recommend premium stays" is not a question with one answer — it's the start of
a short negotiation. The assistant can suggest hotels straight away, but it must
NOT quietly rewrite the plan: replacing every night's hotel when the traveller
only wanted to look, or only wanted it for the last night, is worse than doing
nothing at all.

So the flow is: propose -> STOP AND ASK -> apply only what they chose.
LangGraph's `interrupt()` models exactly that. It suspends the graph mid-node,
the state is saved to the checkpointer under a thread id, and a later
`Command(resume=...)` picks up where it stopped — which is what lets the pause
span two separate HTTP requests without hand-rolling a state machine.

The thread id is the chat session id, so a negotiation belongs to the
conversation it happened in.
"""
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, END, StateGraph
from langgraph.types import Command, interrupt

from enrichments import stays_for_days
from stay_prefs import BAND_LABELS, parse_scope


class StayRevisionState(TypedDict, total=False):
    # --- inputs ---
    band: str                   # "budget" | "mid" | "premium"
    itinerary: list[dict]       # the planned stops, day-numbered
    existing_stays: list[dict]  # what the plan currently shows, food included
    nights: list[int]           # the days that actually have an overnight halt

    # --- filled in once the traveller answers ---
    answer: str                 # their reply, verbatim
    scope: str                  # "all" | "none" | "unclear" | a day number
    attempts: int               # how many times we've put the question
    changed: bool               # did the plan actually move?
    stays: list[dict]           # the merged replacement for itinerary_stays
    message: str                # what to say back in the chat


def ask_scope(state: StayRevisionState) -> dict:
    """Put the choice to the traveller and suspend here until they answer."""
    band = BAND_LABELS.get(state["band"], state["band"])
    nights = state.get("nights") or []
    attempts = state.get("attempts", 0) + 1

    options = ["The whole trip"]
    options += [f"Just day {d}" for d in nights]
    options.append("No need")

    if attempts == 1:
        question = (
            f"Want me to put {band} stays into your plan — for the whole trip, "
            f"or just one particular day?"
        )
    else:
        # a re-ask shouldn't be the same sentence again; make the answers explicit
        example = nights[0] if nights else 1
        question = (
            f"Just so I change the right nights — for the {band} stays, say "
            f"“the whole trip”, a day like “day {example}”, or "
            f"“no need”."
        )

    answer = interrupt({
        "kind": "stay_band",
        "band": state["band"],
        "band_label": band,
        "nights": nights,
        "question": question,
        "options": options,
    })
    return {"answer": answer if isinstance(answer, str) else str(answer),
            "attempts": attempts}


def apply_scope(state: StayRevisionState) -> dict:
    """Work out what they agreed to, and change only that much."""
    nights = state.get("nights") or []
    band = state["band"]
    label = BAND_LABELS.get(band, band)
    existing = state.get("existing_stays") or []
    scope = parse_scope(state.get("answer", ""), nights)

    if scope is None:
        # Deliberately not a guess — rewriting the wrong night is worse than
        # asking again. `after_apply` routes this back to the question, up to
        # a limit, so we don't interrogate someone who has moved on.
        if state.get("attempts", 1) < _MAX_ASKS:
            return {"scope": "unclear", "changed": False, "stays": existing, "message": ""}
        return {
            "scope": "gave_up", "changed": False, "stays": existing,
            "message": (
                f"I'll leave your stays as they are for now — just ask again when "
                f"you know which nights you'd like {label} places for."
            ),
        }

    if scope == "none":
        return {
            "scope": "none", "changed": False, "stays": existing,
            "message": "No problem — I've left your stays exactly as they were.",
        }

    days = nights if scope == "all" else [int(scope)]
    fresh = stays_for_days(state.get("itinerary") or [], band, days)

    # Merge over what's already there, so the food picks for those nights — and
    # every night we weren't asked to touch — survive untouched.
    by_day = {s["day"]: dict(s) for s in existing}
    replaced: list[int] = []
    for entry in fresh:
        if entry.get("skipped") or not entry.get("stay"):
            continue
        day = entry["day"]
        current = by_day.get(day, {"day": day, "food": []})
        current.update({
            "anchor": entry.get("anchor") or current.get("anchor"),
            "town": entry.get("town") or current.get("town"),
            "stay": entry["stay"],
        })
        current.pop("skipped", None)
        by_day[day] = current
        replaced.append(day)

    merged = [by_day[d] for d in sorted(by_day)]

    if not replaced:
        return {
            "scope": str(scope), "changed": False, "stays": existing,
            "message": (
                f"I couldn't find {label} places just now — the hotel lookup didn't "
                f"come back. Your existing stays are untouched; try me again shortly."
            ),
        }

    where = "every night" if scope == "all" else f"day {replaced[0]}"
    return {
        "scope": "all" if scope == "all" else str(scope),
        "changed": True,
        "stays": merged,
        "message": (
            f"Done — {label} stays are in your plan for {where}. "
            f"Have a look under \"Food & stay along the way\"."
        ),
    }


# How many times we'll put the question before letting it go.
_MAX_ASKS = 3


def after_apply(state: StayRevisionState) -> str:
    """An answer we couldn't read sends us back to the question, so the
    conversation stays open — the previous version closed the negotiation while
    still inviting an answer, and the traveller's next reply ("just day 2") fell
    through to trip-detail extraction and was lost."""
    return "ask_scope" if state.get("scope") == "unclear" else END


def _build():
    g = StateGraph(StayRevisionState)
    g.add_node("ask_scope", ask_scope)
    g.add_node("apply_scope", apply_scope)
    g.add_edge(START, "ask_scope")
    g.add_edge("ask_scope", "apply_scope")
    g.add_conditional_edges("apply_scope", after_apply, ["ask_scope", END])
    # In-memory, like the plan-job table: a pending question is lost on a
    # restart, and the traveller simply asks again.
    return g.compile(checkpointer=InMemorySaver())


_GRAPH = _build()


def _cfg(session_id: str) -> dict:
    return {"configurable": {"thread_id": f"stays:{session_id}"}}


def nights_from_itinerary(itinerary: list[dict]) -> list[int]:
    """Days with a night after them — the last day needs no hotel."""
    days = sorted({s["day"] for s in itinerary or []})
    return days[:-1] if len(days) > 1 else days


def propose(session_id: str, band: str, itinerary: list[dict],
            existing_stays: list[dict]) -> dict | None:
    """Start the negotiation. Returns the question to put to the traveller, or
    None when there is nothing to apply it to."""
    nights = nights_from_itinerary(itinerary)
    if not nights:
        return None
    out = _GRAPH.invoke(
        {"band": band, "itinerary": itinerary,
         "existing_stays": existing_stays or [], "nights": nights},
        _cfg(session_id),
    )
    pending = out.get("__interrupt__")
    return dict(pending[0].value) if pending else None


def resume(session_id: str, answer: str) -> dict:
    """Feed the traveller's answer back in and let the graph finish."""
    out = _GRAPH.invoke(Command(resume=answer), _cfg(session_id))
    if out.get("__interrupt__"):        # asked again after an unclear answer
        return {"pending": dict(out["__interrupt__"][0].value),
                "changed": False, "message": "", "stays": None}
    return {
        "pending": None,
        "changed": bool(out.get("changed")),
        "message": out.get("message") or "",
        "stays": out.get("stays") if out.get("changed") else None,
    }
