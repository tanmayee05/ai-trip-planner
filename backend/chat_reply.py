"""
Answering, as opposed to interrogating.

The planner chat was a pure slot-filling loop: whatever you said, it replied
with the next unanswered question. So "can you give best hotel rooms in Vizag
with a beach view" got "Where are you starting your journey from?" — the
question was simply dropped on the floor.

This module spots when a message is actually ASKING something and produces a
real answer, then folds the pending slot question in as a follow-up so the
conversation still moves toward a plan.

We gate the extra LLM call behind a cheap heuristic — short replies like
"guntur" or "5 days" are slot answers and skip it entirely, so the common
path stays as fast as before.
"""

import os
import re

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from trip_slots import TripSlots

load_dotenv()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

_llm = ChatGoogleGenerativeAI(model=MODEL_NAME, google_api_key=os.getenv("GEMINI_API_KEY"))

_tavily = None
if TAVILY_API_KEY:
    try:
        from tavily import TavilyClient
        _tavily = TavilyClient(api_key=TAVILY_API_KEY)
    except Exception:  # noqa: BLE001 — package missing or client init failed; degrade gracefully
        _tavily = None

# leading words that make a sentence a request for information
_LEAD = re.compile(
    r"^\s*(can|could|would|will|what|which|where|when|how|why|who|is|are|do|does|"
    r"any|some|suggest|recommend|tell|give|show|find|list|best|good|top|"
    r"i want to know|help)\b",
    re.I,
)

# a casual opener ("hey give me...", "so what's...") sits in front of the
# actual request and would otherwise defeat _LEAD's anchored match — strip it
# first so "hey give all the mid-range stays" is still recognised as a request
_OPENER = re.compile(
    r"^\s*(hey|hi|hello|yo|hola|please|pls|so|well|ok|okay|also|btw|"
    r"umm?|hmm?|thanks|thank you)[,!.\s]+",
    re.I,
)


def looks_like_question(message: str) -> bool:
    """Is the user asking us something, rather than answering a slot question?

    A literal '?' always counts. Otherwise we need a reasonably long sentence
    that opens like a request — that keeps "guntur", "5 days" and "own vehicle"
    on the fast path.
    """
    m = (message or "").strip()
    if not m:
        return False
    if "?" in m:
        return True
    stripped = _OPENER.sub("", m, count=1)
    if len(stripped.split()) < 4:
        return False
    return bool(_LEAD.match(stripped))


# phrasing that signals the traveller wants to CHANGE the trip, not just ask
# about somewhere — lets "can we go to Goa instead?" through the guard that
# stops "best hotels in Vizag?" from rewriting the destination
_CHANGE = re.compile(
    r"\b(instead|change|switch|swap|rather|make it|actually|update|"
    r"let's go to|lets go to|move it to)\b",
    re.I,
)


def wants_change(message: str) -> bool:
    """Does this message explicitly ask to alter the trip details?"""
    return bool(_CHANGE.search(message or ""))


_SYSTEM = (
    "You are Wayfarer, a warm and practical India travel assistant built into a "
    "trip-planning app. Answer the traveller's question directly and concretely — "
    "name real places, hotels, neighbourhoods, dishes or routes where that helps. "
    "Keep it tight: 2-4 short sentences, or a bullet list sized to what they asked "
    "for (e.g. 'give me 5' means 5 bullets, one line each). "
    "Give prices only as rough ranges and say they are approximate. "
    "If you are not confident something exists, say so rather than inventing it. "
    "Ask at most ONE follow-up question, and only the one you are given."
)

_SYSTEM_GROUNDED = _SYSTEM + (
    " You are also given some live search results below — prefer them over your "
    "own memory for names, prices, ratings and anything that changes over time. "
    "Only state a star rating or review count if the search results actually give "
    "one; otherwise describe reputation qualitatively (e.g. 'well-reviewed') "
    "instead of inventing a number. Don't mention 'search results' to the "
    "traveller — just answer naturally, as if you already knew this."
)


def _search_context(message: str, slots: TripSlots) -> str | None:
    """A few live web results to ground the answer in — real, current names
    and prices instead of whatever the model last saw in training. Returns
    None (not an empty string) whenever search isn't available or useful, so
    the caller can fall back to the plain, ungrounded prompt."""
    if not _tavily:
        return None
    place = slots.destination or slots.source
    query = f"{message} {place}" if place else message
    try:
        res = _tavily.search(
            query, search_depth="basic", max_results=5, include_answer=False,
        )
    except Exception:  # noqa: BLE001 — quota, network, bad key — degrade quietly
        return None

    lines = []
    for r in res.get("results", [])[:5]:
        title = (r.get("title") or "").strip()
        snippet = (r.get("content") or "").strip()
        if not (title or snippet):
            continue
        snippet = snippet[:280]
        lines.append(f"- {title}: {snippet}" if title else f"- {snippet}")
    return "\n".join(lines) or None


def _text_of(response) -> str:
    """LangChain content is usually a str, occasionally a list of parts."""
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in content
        ]
        return "\n".join(x for x in parts if x).strip()
    return str(content).strip()


def answer_question(message: str, slots: TripSlots, pending_question: str | None) -> str | None:
    """A real answer to `message`, with `pending_question` woven in as the
    follow-up. Returns None if the model is unavailable — the caller then
    falls back to plain slot-filling.

    When TAVILY_API_KEY is configured, this first pulls a few live search
    results for the question (grounded to the trip's destination) so names,
    prices and ratings come from the actual web instead of only the model's
    training data — falls straight through to the plain answer if search
    isn't configured or comes back empty."""
    known = ", ".join(
        f"{k}={v}" for k, v in slots.model_dump(exclude_none=True).items()
    ) or "nothing yet"

    context = _search_context(message, slots)

    human = f'The traveller said: "{message}"\n\nTrip details so far: {known}.\n\n'
    if context:
        human += f"Live search results:\n{context}\n\n"
    if pending_question:
        human += (
            "After you answer, ask this one follow-up in your own words so we can "
            f'keep building their plan: "{pending_question}"'
        )
    else:
        human += "We already have every trip detail we need, so do not ask a follow-up."

    system = _SYSTEM_GROUNDED if context else _SYSTEM
    try:
        return _text_of(_llm.invoke([("system", system), ("human", human)])) or None
    except Exception:  # noqa: BLE001 — fall back to the plain question
        return None
