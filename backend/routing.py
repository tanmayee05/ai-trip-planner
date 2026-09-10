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
# The POST /geojson form, not the GET one. The GET endpoint snaps each endpoint
# to a road within a fixed 350 m and returns HTTP 404 "Could not find routable
# point" when it can't — which is the normal case for the very places people
# pick as stops: beaches, backwaters, island forts, hill viewpoints. POST
# accepts `radiuses`, and -1 means "search as far as needed", which turns those
# 404s into real routes (verified: Tarkarli Beach, Om Beach and Sindhudurg Fort
# all 404 on GET and all route fine here).
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"


def _ors_fetch(lat1: float, lon1: float, lat2: float, lon2: float, timeout: int) -> dict | None:
    """One ORS call -> {distance_km, duration_hr, coordinates} or None.

    Shared by both public functions so they can't drift apart; each caches the
    slice of this it actually needs.
    """
    try:
        response = requests.post(
            ORS_URL,
            headers={"Authorization": ORS_API_KEY, "Content-Type": "application/json"},
            json={
                "coordinates": [[lon1, lat1], [lon2, lat2]],  # ORS wants lon,lat
                "radiuses": [-1, -1],                         # snap from any distance
            },
            timeout=timeout,
        )
    except requests.exceptions.RequestException as e:
        print(f"ORS request failed: {e}")
        return None

    if response.status_code != 200:
        # log enough of the body to see WHICH endpoint was rejected — the old
        # 120-char cut hid the coordinate, which is the one thing you need
        print(f"ORS error: {response.status_code} — {response.text[:260]}")
        return None

    try:
        feature = response.json()["features"][0]
        summary = feature["properties"]["summary"]
    except (ValueError, KeyError, IndexError) as e:
        print(f"ORS sent an unexpected body: {type(e).__name__}")
        return None

    return {
        "distance_km": round(summary["distance"] / 1000, 1),  # ORS gives meters
        "duration_hr": round(summary["duration"] / 3600, 1),  # ORS gives seconds
        "coordinates": feature["geometry"]["coordinates"],    # ordered [lon, lat]
    }


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
            cached = json.loads(cache_file.read_text(encoding="utf-8"))  # dict or null
            # A cached `null` is a miss recorded by the old GET endpoint, which
            # gave up 350 m from the road. The unlimited-radius POST can route
            # those, so don't let a stale miss mask a route we can now get.
            if cached is not None:
                return cached
        except ValueError:
            pass

    route = _ors_fetch(lat1, lon1, lat2, lon2, timeout=25)
    _ROUTE_CACHE_DIR.mkdir(exist_ok=True)
    if route is None:
        cache_file.write_text("null", encoding="utf-8")
        return None

    out = {"distance_km": route["distance_km"], "duration_hr": route["duration_hr"]}
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
            cached = json.loads(geom_file.read_text(encoding="utf-8"))
            if cached is not None:
                return cached
        except ValueError:
            pass

    route = _ors_fetch(lat1, lon1, lat2, lon2, timeout=35)
    _ROUTE_CACHE_DIR.mkdir(exist_ok=True)
    # Cache the miss too. This one never did, so an unroutable endpoint paid
    # the full ORS round-trip again on every re-plan — which is why the same
    # 404 kept reappearing in the log for one job.
    geom_file.write_text(json.dumps(route), encoding="utf-8")
    return route


if __name__ == "__main__":
    from geocoding import geocode

    guntur = geocode("Guntur")
    coorg = geocode("Coorg")

    route = get_driving_route(
        guntur["lat"], guntur["lon"],
        coorg["lat"], coorg["lon"]
    )
    print(route)