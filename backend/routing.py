import hashlib
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ORS free tier is rate-limited (40 req/min) and a route between two fixed
# points never changes materially, so cache answers on disk keyed by the
# rounded coordinates. A repeated trip plan then costs zero ORS calls.
_ROUTE_CACHE_DIR = Path(__file__).with_name(".route_cache")

"""
routing engine — a service that has the actual road network and can calculate a real path between two points.
OpenRouteService (ORS)
"""
ORS_API_KEY = os.getenv("ORS_API_KEY")
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"


def _route_cache_key(lat1, lon1, lat2, lon2) -> Path:
    raw = f"{lat1:.4f},{lon1:.4f}->{lat2:.4f},{lon2:.4f}"
    return _ROUTE_CACHE_DIR / f"{hashlib.sha1(raw.encode()).hexdigest()[:16]}.json"


def get_driving_route(lat1: float, lon1: float, lat2: float, lon2: float) -> dict | None:
    """
    Get real driving distance/duration between two coordinates.
    Returns {"distance_km": float, "duration_hr": float} or None on failure.

    Note: ORS expects coordinates as [longitude, latitude] — reversed from
    how we've been writing them (lat, lon). This trips people up constantly,
    so it's worth noting explicitly here.
    """
    cache_file = _route_cache_key(lat1, lon1, lat2, lon2)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))  # dict or null
        except ValueError:
            pass

    headers = {"Authorization": ORS_API_KEY}
    params = {"start": f"{lon1},{lat1}", "end": f"{lon2},{lat2}"}

    try:
        response = requests.get(ORS_URL, headers=headers, params=params, timeout=20)
    except requests.exceptions.RequestException as e:
        print(f"ORS request failed: {e}")
        return None

    if response.status_code != 200:
        print(f"ORS error: {response.status_code} — {response.text[:120]}")
        # a 404 "no routable point" will never succeed on retry — cache the miss
        if response.status_code == 404:
            _ROUTE_CACHE_DIR.mkdir(exist_ok=True)
            cache_file.write_text("null", encoding="utf-8")
        return None

    data = response.json()
    summary = data["features"][0]["properties"]["summary"]
    out = {
        "distance_km": round(summary["distance"] / 1000, 1),  # ORS gives meters
        "duration_hr": round(summary["duration"] / 3600, 1),  # ORS gives seconds
    }
    _ROUTE_CACHE_DIR.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(out), encoding="utf-8")
    return out

"""
It's not live traffic — ORS's free driving-car profile calculates duration based on road type, speed limits, and road geometry
(curves, etc.), essentially "how long would this take driving at typical/legal speeds with no unusual delays."
It's a solid baseline estimate, but doesn't account for real-time congestion, accidents, or time-of-day traffic patterns. 
Worth remembering — we should label this as "estimated driving time" in the UI
"""

def get_driving_route_with_geometry(lat1: float, lon1: float, lat2: float, lon2: float) -> dict | None:
    """
    Same as get_driving_route, but also returns the actual path coordinates
    — needed to place waypoints ALONG the route (fuel / food / rest stops).
    Disk-cached like get_driving_route; returns None on any failure.
    """
    cache_file = _route_cache_key(lat1, lon1, lat2, lon2)
    geom_file = cache_file.with_suffix(".geom.json")
    if geom_file.exists():
        try:
            return json.loads(geom_file.read_text(encoding="utf-8"))
        except ValueError:
            pass

    headers = {"Authorization": ORS_API_KEY}
    params = {"start": f"{lon1},{lat1}", "end": f"{lon2},{lat2}"}
    try:
        response = requests.get(ORS_URL, headers=headers, params=params, timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"ORS geometry request failed: {e}")
        return None
    if response.status_code != 200:
        print(f"ORS error: {response.status_code} — {response.text[:120]}")
        return None

    data = response.json()
    feature = data["features"][0]
    summary = feature["properties"]["summary"]
    out = {
        "distance_km": round(summary["distance"] / 1000, 1),
        "duration_hr": round(summary["duration"] / 3600, 1),
        "coordinates": feature["geometry"]["coordinates"],  # ordered [lon, lat] along the road
    }
    _ROUTE_CACHE_DIR.mkdir(exist_ok=True)
    geom_file.write_text(json.dumps(out), encoding="utf-8")
    return out


if __name__ == "__main__":
    from geocoding import geocode

    guntur = geocode("Guntur")
    coorg = geocode("Coorg")

    route = get_driving_route(
        guntur["lat"], guntur["lon"],
        coorg["lat"], coorg["lon"]
    )
    print(route)