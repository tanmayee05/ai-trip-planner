"""
Step 1 of the router: given a SOURCE place, find every nearby transport hub
(train stations, bus stands, airports) that a traveller could realistically
start their journey from.

We only find the hubs here. Deciding WHICH hub to use for a given
destination (the "recommend Tirupati, else Chennai, else Gannavaram" logic)
is the next step and lives elsewhere.
"""

import hashlib
import json
import re
import threading
import time
from pathlib import Path

import requests
from distance import straight_line_distance_km
from geocoding import geocode, reverse_geocode
from train_lookup import find_station_by_name, count_trains_at_station, place_name_variants

# The public Overpass server is often busy and answers 429 / 504. We try a
# few community mirrors in turn instead of silently giving back nothing
# (that was why "--- Flights ---" came back empty on some runs).
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
HEADERS = {"User-Agent": "ai-trip-planner-learning-project"}

# For each hub type: which OSM tags mark it, and how far out to look.
# NOTE: a hub type can have SEVERAL valid tags. A big APSRTC bus stand is
# usually amenity=bus_station, but some are only mapped as
# public_transport=station + bus=yes, so we search for both.
SEARCH_CONFIG = {
    "bus": {
        "tags": ['["amenity"="bus_station"]', '["public_transport"="station"]["bus"="yes"]'],
        "radius_km": 60,
    },
    "flight": {
        "tags": ['["aeroway"="aerodrome"]'],
        "radius_km": 300,
    },
}

MIN_TRAINS_THRESHOLD = 5

# What makes a station a "major junction" (Vijayawada, Secunderabad,
# Visakhapatnam, ...)? Not a hand-typed city list — how many distinct
# trains actually stop there, straight from trains.db. This is the same
# database everything else here already uses, so "major" stays correct
# even for a source city we never thought to name explicitly.
MAJOR_HUB_MIN_TRAINS = 100

# small caches so re-runs and repeated names don't re-hit the network
_geo_cache: dict[str, dict | None] = {}

# On-disk cache of Overpass answers. OSM hub data (stations, airports, city
# points) barely changes week to week, but the public Overpass servers are
# frequently busy (429 / 504). Caching the FIRST good answer per query means
# later runs are instant and a busy server can't wipe out a whole section
# (that's why "=== TRAIN ===" came back empty — every mirror was down that run).
_OVERPASS_CACHE_DIR = Path(__file__).with_name(".overpass_cache")


def _overpass_cache_path(query: str) -> Path:
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:16]
    return _OVERPASS_CACHE_DIR / f"{digest}.json"


# --------------------------------------------------------------------------
# Overpass (OpenStreetMap) helpers
# --------------------------------------------------------------------------
# Overpass returns [] both for "nothing is there" and for "every mirror is
# down". Callers that report findings to a human need to tell those apart —
# "no airport near the destination" is a confident, wrong statement to make
# when we simply couldn't ask. This set is written by _post_overpass and read
# through the helpers below.
_LAST_OVERPASS_FAILED: set[bool] = set()

# --- circuit breaker -------------------------------------------------------
# Exhausting every mirror is EXPENSIVE: a read timeout costs 45s per mirror,
# so one dead-Overpass query burns ~105-135s before returning []. A plan makes
# several queries, and when the mirrors are unhealthy they all fail the same
# way — so without a breaker a single bad Overpass spell can add ten minutes
# to a plan and push it past the point where the client gives up waiting.
#
# After a total failure we therefore stop calling out for a cooldown and let
# the affected sections degrade immediately (they already report "couldn't
# check" honestly). One success closes the breaker again, and once the cooldown
# elapses the next query is allowed through to test the water.
_OVERPASS_COOLDOWN_S = 90
_breaker_lock = threading.Lock()
_breaker_open_until = 0.0


def _breaker_is_open() -> bool:
    with _breaker_lock:
        return time.monotonic() < _breaker_open_until


def _breaker_trip() -> None:
    global _breaker_open_until
    with _breaker_lock:
        _breaker_open_until = time.monotonic() + _OVERPASS_COOLDOWN_S


def _breaker_reset() -> None:
    global _breaker_open_until
    with _breaker_lock:
        _breaker_open_until = 0.0


def overpass_failures_reset() -> None:
    """Start a fresh 'did Overpass work?' window."""
    _LAST_OVERPASS_FAILED.clear()


def overpass_failed_since_reset() -> bool:
    """True if any Overpass query since the last reset exhausted every mirror."""
    return bool(_LAST_OVERPASS_FAILED)


def _post_overpass(query: str) -> list[dict]:
    """POST one Overpass query, trying each mirror and retrying on 429/504.
    Answers are cached on disk; prints WHY it failed instead of returning []
    silently."""
    cache_file = _overpass_cache_path(query)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except ValueError:
            pass  # corrupt cache entry — fall through and re-fetch

    # a cached answer is always served (above); only NEW queries are skipped
    if _breaker_is_open():
        print("  [overpass] skipping — every mirror failed recently (cooling down)")
        _LAST_OVERPASS_FAILED.add(True)
        return []

    for url in OVERPASS_MIRRORS:
        for attempt in range(2):
            try:
                # (connect timeout, read timeout): a mirror that hasn't
                # answered in 45s is stuck — move to the next one.
                resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=(10, 45))
            except requests.exceptions.RequestException as e:
                print(f"  [overpass] {url} error: {e}")
                break
            if resp.status_code == 200:
                try:
                    elements = resp.json().get("elements", [])
                except ValueError:
                    print(f"  [overpass] {url} sent a non-JSON body")
                    break
                _OVERPASS_CACHE_DIR.mkdir(exist_ok=True)
                cache_file.write_text(json.dumps(elements), encoding="utf-8")
                _breaker_reset()          # Overpass is answering again
                return elements
            if resp.status_code in (429, 504):
                wait = 5 * (attempt + 1)
                print(f"  [overpass] {url} busy ({resp.status_code}); retry in {wait}s")
                time.sleep(wait)
                continue
            print(f"  [overpass] {url} returned HTTP {resp.status_code}")
            break
    print("  [overpass] all mirrors failed for this query")
    _LAST_OVERPASS_FAILED.add(True)
    _breaker_trip()
    return []


def _query_overpass(lat: float, lon: float, radius_km: float, tags: list[str]) -> list[dict]:
    """
    Look for ANY of the given tags around a point.

    Two details that were bugs before:

    1. We ask for `nwr`, not just `node`. In OpenStreetMap a big thing like an
       airport or a bus station is drawn as an AREA (a `way` / `relation`
       polygon), not a single point. Querying only `node` silently misses
       almost every real airport. `nwr` = node + way + relation.

    2. We ask for `out center;`. For a way/relation with no lat/lon of its
       own, Overpass then returns a `center` point (the middle of the
       polygon) that we can measure distance to.
    """
    radius_m = int(radius_km * 1000)
    clauses = "".join(f"nwr{t}(around:{radius_m},{lat},{lon});" for t in tags)
    query = f"[out:json][timeout:60];({clauses});out center;"
    return _post_overpass(query)


def _element_coords(e: dict) -> tuple[float | None, float | None]:
    """Get a point out of any Overpass element: a node has lat/lon directly,
    a way/relation only has `center`."""
    if "lat" in e and "lon" in e:
        return e["lat"], e["lon"]
    center = e.get("center")
    if center:
        return center["lat"], center["lon"]
    return None, None


def _cached_geocode(name: str) -> dict | None:
    # geocoding.geocode() now has its own disk cache + 1 req/s throttle, so
    # this in-memory layer just avoids repeat work within a single request.
    if name not in _geo_cache:
        _geo_cache[name] = geocode(name)
    return _geo_cache[name]


# --------------------------------------------------------------------------
# Bus stands & airports
# --------------------------------------------------------------------------
def list_nearby_bus_or_flight(lat: float, lon: float, transport_type: str, max_results: int = 6) -> list[dict]:
    """Return several nearby options (not just one), sorted closest first."""
    config = SEARCH_CONFIG[transport_type]
    elements = _query_overpass(lat, lon, config["radius_km"], config["tags"])

    results = []
    seen_names = set()
    for e in elements:
        elat, elon = _element_coords(e)
        if elat is None:
            continue

        tags = e.get("tags", {})
        name = tags.get("name")
        if not name:
            continue  # unnamed aprons / bus bays / airstrips are noise
        if name in seen_names:
            continue  # same hub mapped as both a node and an area
        seen_names.add(name)

        dist = straight_line_distance_km(lat, lon, elat, elon)
        row = {
            "name": name,
            "lat": elat, "lon": elon,
            "type": transport_type, "distance_km": round(dist, 1),
        }
        if transport_type == "flight":
            # an IATA code is a strong hint the airport has scheduled
            # passenger flights (Tirupati/Chennai/Kadapa have one;
            # airstrips, heliports and naval bases do not)
            row["iata"] = tags.get("iata")
        results.append(row)

    if transport_type == "flight":
        # real airports first, then by distance; airstrips sink to the bottom
        results.sort(key=lambda r: (r["iata"] is None, r["distance_km"]))
    else:
        results.sort(key=lambda r: r["distance_km"])
    return results[:max_results]


# --------------------------------------------------------------------------
# Nearby place names (for the train-station search)
# --------------------------------------------------------------------------
def get_nearby_towns(lat: float, lon: float, radius_km: float = 70) -> list[str]:
    """
    Ask OSM for real town / city points around the source.

    Why: reverse-geocoding a village only tells us its own name and its
    district ("Rebala", "Nellore"). It never tells us about the OTHER towns
    nearby (Kavali, Gudur, Sullurpeta...) where the usable stations are.
    Returned closest-first.
    """
    radius_m = int(radius_km * 1000)
    query = (
        f'[out:json][timeout:60];'
        f'node["place"~"^(city|town)$"](around:{radius_m},{lat},{lon});'
        f'out body;'
    )
    elements = _post_overpass(query)

    towns = []
    for e in elements:
        tags = e.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        if not name:
            continue
        dist = straight_line_distance_km(lat, lon, e["lat"], e["lon"])
        towns.append((round(dist, 1), name))

    towns.sort()
    return [name for _, name in towns]


def get_regional_cities(lat: float, lon: float, radius_km: float = 550) -> list[str]:
    """
    Bigger-radius version of get_nearby_towns(), `place=city` only (not
    town/village — that keeps a 550km-radius result set manageable).

    This is how we reach the region's major junctions (Vijayawada,
    Secunderabad, Visakhapatnam, ...) WITHOUT hand-typing their names: we
    just ask OSM which real cities are within a long-distance-express's
    reach of the source, then let MAJOR_HUB_MIN_TRAINS decide which of
    their stations actually count as major. 550km safely covers
    Visakhapatnam (~505km from south Nellore district).
    """
    radius_m = int(radius_km * 1000)
    query = f'[out:json][timeout:90];node["place"="city"](around:{radius_m},{lat},{lon});out body;'
    elements = _post_overpass(query)

    cities = []
    for e in elements:
        tags = e.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        if not name:
            continue
        dist = straight_line_distance_km(lat, lon, e["lat"], e["lon"])
        cities.append((round(dist, 1), name))

    cities.sort()
    return [name for _, name in cities]


def get_nearby_place_candidates(lat: float, lon: float) -> list[str]:
    """
    Place names worth checking for train stations, local -> regional:
      source village + district (reverse geocoding)
      + real nearby towns / cities (OSM `place` points)
    """
    address = reverse_geocode(lat, lon)
    candidates = []
    if address:
        for key in ["village", "town", "city", "district"]:
            val = address.get(key)
            if val:
                candidates.append(val.replace("Sri Potti Sriramulu ", ""))

    for town in get_nearby_towns(lat, lon):
        if town not in candidates:
            candidates.append(town)

    return candidates


# --------------------------------------------------------------------------
# Train stations
# --------------------------------------------------------------------------
def _clean_place(name: str) -> str:
    """'Atmakuru ( N )' -> 'Atmakuru' : drop bracketed suffixes / extra spaces."""
    return re.split(r"[(\[]", name)[0].strip()


def _station_search_name(station_name: str) -> str:
    """
    Turn a DB station name into something Nominatim can actually geocode.
    'VIJAYAWADA JN - BZA' -> 'Vijayawada, India'
    Without stripping the ' JN' / ' H' suffix, Vijayawada and Guntur
    junctions failed to geocode and dropped out of the list entirely.
    """
    base = station_name.split(" - ")[0]
    base = re.sub(r"\s+(JN|JN\.|HALT|H|CABIN)\.?$", "", base, flags=re.IGNORECASE).strip()
    return f"{base.title()}, India"


def _place_is_whole_word(place: str, station_name: str) -> bool:
    """
    True only if `place` appears as a WHOLE WORD inside the station name.

    find_station_by_name() uses SQL `LIKE %place%`, so the place "Allur"
    wrongly matched the station "TIRUVALLUR - TRL" (…tiruv-ALLUR…). A word
    boundary check kills that false positive while still letting "Nellore"
    match "NELLORE SOUTH - NLS".
    """
    place = _clean_place(place)
    if len(place) < 4:
        return False  # 2-3 letter fragments match everything
    return re.search(rf"\b{re.escape(place.upper())}\b", station_name.upper()) is not None


def _collect_stations(lat: float, lon: float, names: list[str], min_trains: int = MIN_TRAINS_THRESHOLD) -> list[dict]:
    """Check each candidate place name against trains.db. `min_trains` lets
    the caller ask for only the busiest stations (see list_nearby_train_stations
    below) without geocoding every small halt along the way."""
    results = []
    seen_stations = set()

    for place_name in names:
        # try the name AND any old/new railway spelling of it (Mysuru/Mysore)
        variants = [_clean_place(v) for v in place_name_variants(_clean_place(place_name))]
        matched_stations = {
            s
            for term in variants
            for s in find_station_by_name(term)
            if any(_place_is_whole_word(v, s) for v in variants)
        }

        for station_name in matched_stations:
            if station_name in seen_stations:
                continue
            seen_stations.add(station_name)

            count = count_trains_at_station(station_name)
            if count < min_trains:
                continue

            geo = _cached_geocode(_station_search_name(station_name))
            if not geo:
                continue

            dist = straight_line_distance_km(lat, lon, geo["lat"], geo["lon"])
            results.append({
                "name": station_name, "lat": geo["lat"], "lon": geo["lon"],
                "type": "train", "train_count": count,
                "distance_km": round(dist, 1), "major_hub": count >= MAJOR_HUB_MIN_TRAINS,
            })
    return results


def list_nearby_train_stations(lat: float, lon: float, search_names: list[str], max_results: int = 5) -> list[dict]:
    """
    Return:
      - the closest real stations to the source (up to max_results), PLUS
      - every genuinely major junction (train_count >= MAJOR_HUB_MIN_TRAINS)
        among the region's cities, even if it's far away — long-distance
        expresses stop there and a traveller from this region can board a
        through train at the junction.

    Nothing here is a hardcoded place name: "nearby" comes from OSM
    (get_nearby_place_candidates), "major" comes from trains.db train counts,
    and "region" comes from OSM again (get_regional_cities).
    """
    nearby = _collect_stations(lat, lon, search_names)

    regional_cities = get_regional_cities(lat, lon)
    # only the busiest stations matter here, so we skip geocoding (network
    # calls) for every minor station that happens to share a city's name
    majors = _collect_stations(lat, lon, regional_cities, min_trains=MAJOR_HUB_MIN_TRAINS)

    merged = {s["name"]: s for s in nearby}
    for s in majors:
        merged.setdefault(s["name"], s)
    stations = sorted(merged.values(), key=lambda r: r["distance_km"])

    kept = stations[:max_results]
    kept_names = {s["name"] for s in kept}
    for s in stations[max_results:]:
        if s["major_hub"] and s["name"] not in kept_names:
            kept.append(s)
    return kept


if __name__ == "__main__":
    place = geocode("Repudi, Andhra Pradesh")
    print("Source coordinates:", place)

    place_candidates = get_nearby_place_candidates(place["lat"], place["lon"])
    print("Place candidates to check:", place_candidates)

    print("\n--- Trains (near + major junctions) ---")
    for t in list_nearby_train_stations(place["lat"], place["lon"], place_candidates):
        tag = "  [major junction]" if t["major_hub"] else ""
        print(t, tag)

    print("\n--- Buses ---")
    for b in list_nearby_bus_or_flight(place["lat"], place["lon"], "bus"):
        print(b)

    print("\n--- Flights ---")
    for f in list_nearby_bus_or_flight(place["lat"], place["lon"], "flight"):
        print(f)
