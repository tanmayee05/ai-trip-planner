"""
New tool: Nominatim (OpenStreetMap's free geocoding service)
What it is: A free, keyless API that turns a place name into coordinates. No signup, no API key
just one rule: you must send a User-Agent header identifying your app (their usage policy, to prevent abuse).
uses:1.Turning a place name ("Guntur") into coordinates (latitude/longitude) — this is called geocoding
     2.Getting the road distance/duration between two coordinates

Results are cached on disk (.geo_cache/). Nominatim asks callers to stay under
1 request/second, so a fresh trip plan that needs ~30 place lookups would take
~30s of pure waiting. Caching the first answer makes every later plan that
touches the same region almost instant, and the cache survives restarts.
"""

# requests is a Python library for making HTTP calls to other web services (this is a new dependency).
# requests is the general-purpose tool for calling any web API.
import hashlib
import json
import time
from pathlib import Path

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_URL_REVERSE = "https://nominatim.openstreetmap.org/reverse"

# Nominatim requires a User-Agent identifying the app — this is their
# usage policy, not optional. Using a browser-like or blank one can get
# you blocked.
HEADERS = {"User-Agent": "ai-trip-planner-learning-project"}

_GEO_CACHE_DIR = Path(__file__).with_name(".geo_cache")

# Nominatim's usage policy: max ~1 request/second. We enforce it here, and
# ONLY around real network calls (cache hits are free), so a warm cache runs
# at full speed.
_MIN_REQUEST_GAP_S = 1.1
_last_request_at = 0.0


def _throttle() -> None:
    global _last_request_at
    wait = _MIN_REQUEST_GAP_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _get_json(url: str, params: dict):
    """GET with the throttle + one retry. Returns parsed JSON, or None on any
    network failure (Nominatim occasionally times out / rate-limits under a
    burst of lookups; a single failed lookup must not kill a whole trip plan)."""
    for attempt in range(2):
        _throttle()
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException:
            if attempt == 0:
                time.sleep(2)
                continue
            return None


def _cache_get(key: str):
    f = _GEO_CACHE_DIR / f"{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))  # may be a dict or null
        except ValueError:
            return "MISS"
    return "MISS"


def _cache_put(key: str, value) -> None:
    _GEO_CACHE_DIR.mkdir(exist_ok=True)
    f = _GEO_CACHE_DIR / f"{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}.json"
    f.write_text(json.dumps(value), encoding="utf-8")


def geocode(place_name: str) -> dict | None:
    """
    Turn a place name into coordinates.
    Returns {"lat": float, "lon": float, "display_name": str} or None if not found.
    """
    key = f"search:{place_name.strip().lower()}"
    cached = _cache_get(key)
    if cached != "MISS":
        return cached

    results = _get_json(NOMINATIM_URL, {"q": place_name, "format": "json", "limit": 1})
    if results is None:
        return None  # transient failure — don't cache, let a later call retry

    if not results:
        _cache_put(key, None)  # genuinely no such place — safe to remember
        return None

    best = results[0]
    out = {
        "lat": float(best["lat"]),
        "lon": float(best["lon"]),
        "display_name": best["display_name"],
    }
    _cache_put(key, out)
    return out


def reverse_geocode(lat: float, lon: float) -> dict | None:
    """
    Given coordinates, return the address hierarchy (village, town, district, state).
    Used to find candidate nearby place names when the exact source has no
    real transport hub of its own.
    """
    key = f"reverse:{round(lat, 5)},{round(lon, 5)}"
    cached = _cache_get(key)
    if cached != "MISS":
        return cached

    data = _get_json(NOMINATIM_URL_REVERSE,
                     {"lat": lat, "lon": lon, "format": "json", "addressdetails": 1})
    if data is None:
        return None  # transient failure — caller treats a missing hierarchy gracefully

    address = data.get("address", {})
    out = {
        "village": address.get("village") or address.get("hamlet"),
        "town": address.get("town"),
        "city": address.get("city"),
        "district": address.get("state_district") or address.get("county"),
        "state": address.get("state"),
    }
    _cache_put(key, out)
    return out


if __name__ == "__main__":
    result = geocode("Guntur")
    print(result)

    result = geocode("Coorg")
    print(result)
