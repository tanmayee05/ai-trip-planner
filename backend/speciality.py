"""
What a place is FAMOUS for — the things you'd regret not knowing about.

Rose milk in Rajahmundry. Kanchipuram silk. Kerala's houseboats. None of this
is an "attraction" you put on a map pin, and none of it comes out of
OpenStreetMap, but it's often the reason people remember a trip.

HOW IT'S SOURCED
----------------
Tavily first, for a handful of current web results, then Gemini to turn those
into a structured list. That order matters: a model asked cold will happily
name a restaurant that shut two years ago, while a model given fresh search
snippets tends to name what people are actually talking about now. Without a
Tavily key it still works, just from the model's own knowledge — same
degradation the chat answers already make.

Cached on disk per destination, like attractions: the answer for Kanchipuram
does not change week to week, and it saves both an LLM and a search call.
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

load_dotenv()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

_CACHE_DIR = Path(__file__).with_name(".speciality_cache")

_tavily = None
if TAVILY_API_KEY:
    try:
        from tavily import TavilyClient
        _tavily = TavilyClient(api_key=TAVILY_API_KEY)
    except Exception:  # noqa: BLE001 — package missing or client init failed
        _tavily = None

KINDS = ("food", "craft", "experience", "sweet", "drink")


class _Speciality(BaseModel):
    name: str = Field(description="What it is, e.g. 'Rose milk' or 'Kanchipuram silk saree'")
    kind: Literal["food", "craft", "experience", "sweet", "drink"] = Field(
        description=(
            "food = a dish or savoury item; sweet = a dessert or mithai; "
            "drink = a beverage; craft = textiles, sarees, metalwork, handicrafts; "
            "experience = something you do, like a houseboat stay or a silk-weaving workshop"
        )
    )
    why: str = Field(description="One sentence on why this place is known for it")
    where: Optional[str] = Field(
        None,
        description=(
            "The best-known place to get it, if there is a specific one — a shop, "
            "eatery or market by name. Leave empty if it's available generally."
        ),
    )
    price_hint: Optional[str] = Field(
        None, description="Rough cost in rupees if it's a thing you buy, e.g. 'Rs 40 a glass'"
    )


class _SpecialityList(BaseModel):
    specialities: list[_Speciality]


_llm = ChatGoogleGenerativeAI(model=MODEL_NAME, google_api_key=os.getenv("GEMINI_API_KEY"))
_extractor = _llm.with_structured_output(_SpecialityList)

_SYSTEM = (
    "You know India region by region: what each place is genuinely famous for, "
    "and what a visitor would be sorry to have missed.\n"
    "\n"
    "Rules:\n"
    "- Only things the place is ACTUALLY known for. If a town has no notable "
    "craft, return none rather than inventing one.\n"
    "- Be specific. 'Rose milk' and 'Kanchipuram silk saree', not 'local sweets' "
    "or 'traditional textiles'.\n"
    "- Name the well-known shop or eatery where there is one, and only where you "
    "are confident it exists and still trades.\n"
    "- Cover a spread: at least one thing to EAT, one to BUY, and one to DO. "
    "If the place has an iconic eatery people queue for, or a signature "
    "experience they travel for - Kerala's houseboats, a silk-weaving "
    "workshop - include it; that is often what the trip is remembered for.\n"
    "- Four to seven items, but never pad to hit a count.\n"
    "- Prices in rupees, and rough is fine."
)


def _cache_path(destination: str) -> Path:
    key = hashlib.sha1(destination.strip().lower().encode()).hexdigest()[:16]
    return _CACHE_DIR / f"{key}.json"


def _search_context(destination: str) -> str | None:
    """Fresh web snippets about what the place is known for, or None."""
    if not _tavily:
        return None
    try:
        res = _tavily.search(
            f"what is {destination} famous for — speciality food, sweets, sarees, "
            f"handicrafts, iconic shops",
            search_depth="basic", max_results=6, include_answer=False,
        )
    except Exception:  # noqa: BLE001 — quota, network, bad key — degrade quietly
        return None

    lines = []
    for r in res.get("results", [])[:6]:
        title = (r.get("title") or "").strip()
        snippet = (r.get("content") or "").strip()[:300]
        if title or snippet:
            lines.append(f"- {title}: {snippet}" if title else f"- {snippet}")
    return "\n".join(lines) or None


def get_specialities(destination: str) -> dict:
    """`{"destination": str, "specialities": [...], "grounded": bool}`.

    `grounded` says whether live search backed this up, so the UI can be honest
    about where the list came from.
    """
    destination = (destination or "").strip()
    if len(destination) < 2:
        return {"destination": destination, "specialities": [], "grounded": False}

    cache_file = _cache_path(destination)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except ValueError:
            pass  # corrupt entry — fall through and re-fetch

    context = _search_context(destination)
    human = f"What is {destination}, India famous for?"
    if context:
        human = (
            f"Recent web results about {destination}:\n{context}\n\n"
            f"Using those to stay current, what is {destination}, India famous for?"
        )

    try:
        result: _SpecialityList = _extractor.invoke(
            [("system", _SYSTEM), ("human", human)]
        )
    except Exception as e:  # noqa: BLE001 — an extra is never worth failing over
        print(f"speciality lookup failed for {destination}: {type(e).__name__}: {e}")
        return {"destination": destination, "specialities": [], "grounded": False}

    items: list[dict] = []
    seen: set[str] = set()
    for sp in result.specialities:
        name = sp.name.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        items.append({
            "name": name,
            "kind": sp.kind if sp.kind in KINDS else "food",
            "why": sp.why.strip(),
            "where": (sp.where or "").strip() or None,
            "price_hint": (sp.price_hint or "").strip() or None,
        })

    out = {
        "destination": destination,
        "specialities": items,
        "grounded": context is not None,
    }
    _CACHE_DIR.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(out), encoding="utf-8")
    return out


if __name__ == "__main__":
    for place in ("Rajahmundry", "Kanchipuram", "Kerala"):
        d = get_specialities(place)
        print(f"\n=== {place}  (grounded: {d['grounded']})")
        for sp in d["specialities"]:
            where = f"  @ {sp['where']}" if sp["where"] else ""
            price = f"  [{sp['price_hint']}]" if sp["price_hint"] else ""
            print(f"  [{sp['kind']:10s}] {sp['name']}{where}{price}")
            print(f"               {sp['why']}")
