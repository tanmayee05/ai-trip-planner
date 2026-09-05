"""
The Haversine formula — a standard mathematical formula for calculating distance between two points on a sphere (Earth),
given their latitude/longitude.
here we not claculating the practical distance b/w to points instead calculating only the actual distance based on 
longitute and lattitude. the real routing distance is calculated in routing.py
"""

from math import radians, sin, cos, sqrt, atan2

EARTH_RADIUS_KM = 6371


def straight_line_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate straight-line ("as the crow flies") distance between two
    coordinates using the Haversine formula.

    This is NOT road distance — a road might wind around hills/rivers and be
    much longer. This is just a quick, free way to estimate "how far apart
    are these two places" for finding nearby hubs, before we call a real
    routing API for accurate road distance.
    """
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return EARTH_RADIUS_KM * c


if __name__ == "__main__":
    from geocoding import geocode

    guntur = geocode("Guntur")
    coorg = geocode("Coorg")

    dist = straight_line_distance_km(
        guntur["lat"], guntur["lon"],
        coorg["lat"], coorg["lon"]
    )
    print(f"Straight-line distance: {dist:.1f} km")