"""
Famous / most-visited places for a destination - whether that's a whole
state ("Kerala") or a single town ("Coorg", "Tiruvannamalai").

Strategy:
  * Gemini gives the curated LIST OF PLACE NAMES: the ones IN the destination
    PLUS well-known places within a day-trip of it (so a Coorg trip can also
    offer Mysore Palace, a Tiruvannamalai trip can offer Pondicherry).
  * Nominatim grounds each name to real coordinates. Anything that won't
    geocode, or lands more than ~250 km away, is dropped.
  * We tag each place `in` (<= 60 km from the destination) or `nearby`, and
    attach a rough road distance / hours so the UI can show a second column.

The frontend shows the whole list and lets the user pick - we don't
pre-select.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from collections import Counter
from difflib import SequenceMatcher

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from distance import straight_line_distance_km
from geocoding import geocode

load_dotenv()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

_CACHE_DIR = Path(__file__).with_name(".attractions_cache")

CATEGORIES = [
    "hill station", "backwater", "beach", "wildlife", "heritage",
    "city", "temple", "fort", "waterfall", "lake", "other",
]

NEARBY_MAX_KM = 250      # farther than this is not a realistic add-on
IN_DESTINATION_KM = 60   # within this counts as "in" the destination
# How far a geocoded place may sit from the TOWN the model said it was in.
# This is a grounding check, not a taste filter: the model names real places
# correctly but Nominatim will happily match a bare name to a same-named
# street in another city. Skandashramam - a cave on Arunachala hill in
# Tiruvannamalai - was being grounded in Chennai, 140 km away, and the whole
# itinerary was then planned around that phantom distance.
SAME_TOWN_MAX_KM = 45
ROAD_DETOUR = 1.3
ROAD_KMH = 45


class _Attraction(BaseModel):
    name: str = Field(description="the place / attraction name, e.g. 'Munnar'")
    nearest_town: str = Field(description="the town or city it is in or nearest to")
    category: str = Field(description=f"one of: {', '.join(CATEGORIES)}")
    blurb: str = Field(description="one short sentence on why people visit")


class _AttractionList(BaseModel):
    places: list[_Attraction]


_llm = ChatGoogleGenerativeAI(model=MODEL_NAME, google_api_key=os.getenv("GEMINI_API_KEY"))
_extractor = _llm.with_structured_output(_AttractionList)

_SYSTEM = (
    "You are an India travel expert. Only list real, well-known places that a "
    "map service can find. Prefer specific place names over vague regions."
)
_PROMPT = (
    "For a trip to {destination}, India, list well-known tourist places to "
    "choose from:\n"
    "1) the most-visited places IN {destination} itself, and\n"
    "2) famous places WITHIN A DAY-TRIP (roughly 3-5 hours by road) that a "
    "visitor might reasonably add on.\n"
    "Give 12 to 22 places total, most-popular first, spread across categories "
    "(hill stations, backwaters, beaches, wildlife, heritage, cities, temples, "
    "forts, waterfalls)."
)


def _cache_path(destination: str) -> Path:
    key = destination.strip().lower()
    return _CACHE_DIR / f"{hashlib.sha1(key.encode()).hexdigest()[:16]}.json"


def _similar(a: str, b: str) -> float:
    """Fuzzy match on letters only, so 'thiruvunnnamalai' scores high against
    'Tiruvannamalai' but 'zzqqxx nowhere' scores near zero against 'Jaipur'."""
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


# below this, the town Gemini named is unrelated to what the user typed —
# it fell back to somewhere famous, and we must not pass that off as a match
_SPELLING_MATCH = 0.55


def _resolve_anchor(destination: str, result: _AttractionList) -> tuple[dict | None, str]:
    """Centre point + display label for the destination.

    A misspelling like "thiruvunnnamalai" won't geocode at all, but Gemini
    still understands it — so we fall back to the town its results keep
    naming. That both rescues the distance maths and hands us the correct
    spelling to show the user.
    """
    hit = geocode(destination)
    if hit:
        return hit, destination

    towns = Counter(p.nearest_town.strip() for p in result.places if p.nearest_town.strip())
    for town, _ in towns.most_common(3):
        if _similar(destination, town) < _SPELLING_MATCH:
            continue
        hit = geocode(f"{town}, India")
        if hit:
            return hit, town
    return None, destination


def get_attractions(destination: str) -> dict:
    """
    Places for `destination` as {"destination": <resolved name>, "places": [...]},
    each place being:
      {name, town, category, blurb, lat, lon, scope, distance_km, approx_hours}
    scope is "in" or "nearby". Cached on disk per destination.
    """
    cache_file = _cache_path(destination)
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            # older caches stored a bare list
            if isinstance(cached, list):
                return {"destination": destination, "places": cached}
            return cached
        except ValueError:
            pass

    try:
        result: _AttractionList = _extractor.invoke([
            ("system", _SYSTEM),
            ("human", _PROMPT.format(destination=destination)),
        ])
    except Exception:  # noqa: BLE001 — LLM/network failure: report "none found"
        return {"destination": destination, "places": []}

    # anchor AFTER the LLM call, so a misspelling can be recovered from it
    anchor, label = _resolve_anchor(destination, result)
    if anchor is None:
        # nothing we can ground the destination to — better an honest "not
        # found" than a confident list of places from somewhere else entirely
        return {"destination": destination, "places": []}

    places: list[dict] = []
    seen: set[str] = set()
    for p in result.places:
        name = p.name.strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)

        town = p.nearest_town.strip()
        geo = geocode(f"{name}, {town}, India") if town else None
        if geo is None:
            # The specific query failed, so fall back to a broad one - but a
            # bare "<name>, India" can land anywhere in the country, so only
            # trust it if it turns up somewhere near the town the model named.
            loose = geocode(f"{name}, India")
            if loose and town:
                town_geo = geocode(f"{town}, India")   # cached after the first place
                if town_geo:
                    off_by = straight_line_distance_km(
                        town_geo["lat"], town_geo["lon"], loose["lat"], loose["lon"]
                    )
                    if off_by > SAME_TOWN_MAX_KM:
                        print(f"  [attractions] dropped '{name}': grounded {off_by:.0f} km "
                              f"from {town}, so that is a different place")
                        continue
                    geo = loose
                else:
                    geo = loose      # can't check the town; take it as given
            else:
                geo = loose
        if not geo:
            continue

        dist_km = None
        approx_hours = None
        scope = "in"
        if anchor:
            dist_km = round(
                straight_line_distance_km(anchor["lat"], anchor["lon"], geo["lat"], geo["lon"]),
                1,
            )
            if dist_km > NEARBY_MAX_KM:
                continue  # too far to be a sensible add-on
            road_km = dist_km * ROAD_DETOUR
            approx_hours = round(road_km / ROAD_KMH, 1)
            scope = "in" if dist_km <= IN_DESTINATION_KM else "nearby"

        cat = p.category.strip().lower()
        places.append({
            "name": name,
            "town": p.nearest_town.strip(),
            "category": cat if cat in CATEGORIES else "other",
            "blurb": p.blurb.strip(),
            "lat": geo["lat"],
            "lon": geo["lon"],
            "scope": scope,
            "distance_km": dist_km,
            "approx_hours": approx_hours,
        })

    # in-destination first, then nearby by distance
    places.sort(key=lambda x: (x["scope"] != "in", x["distance_km"] or 0))

    out = {"destination": label, "places": places}
    if places:
        _CACHE_DIR.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps(out), encoding="utf-8")
    return out


if __name__ == "__main__":
    for a in get_attractions("Coorg")["places"]:
        tag = a["scope"].upper().ljust(6)
        hrs = f"~{a['approx_hours']}h" if a["approx_hours"] else ""
        print(f"{tag} {a['category']:12} | {a['name']:26} ({a['town']}) {hrs}")
