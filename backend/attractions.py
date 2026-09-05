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
from pathlib import Path

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


def get_attractions(destination: str) -> list[dict]:
    """
    Places for `destination`, each as:
      {name, town, category, blurb, lat, lon, scope, distance_km, approx_hours}
    scope is "in" or "nearby". Cached on disk per destination.
    """
    cache_file = _cache_path(destination)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except ValueError:
            pass

    anchor = geocode(destination)  # centre of the destination, for distances
    result: _AttractionList = _extractor.invoke([
        ("system", _SYSTEM),
        ("human", _PROMPT.format(destination=destination)),
    ])

    places: list[dict] = []
    seen: set[str] = set()
    for p in result.places:
        name = p.name.strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)

        geo = geocode(f"{name}, {p.nearest_town}, India") or geocode(f"{name}, India")
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

    if places:
        _CACHE_DIR.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps(places), encoding="utf-8")
    return places


if __name__ == "__main__":
    for a in get_attractions("Coorg"):
        tag = a["scope"].upper().ljust(6)
        hrs = f"~{a['approx_hours']}h" if a["approx_hours"] else ""
        print(f"{tag} {a['category']:12} | {a['name']:26} ({a['town']}) {hrs}")
