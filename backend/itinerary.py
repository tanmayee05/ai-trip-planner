"""
Turn a bag of picked places into a day-by-day route.

- order_stops(): nearest-neighbour path, starting from whichever picked
  place is closest to the traveller's SOURCE (that's the natural entry to
  the region).
- split_into_days(): spread the ordered stops as evenly as possible across
  the trip length.
- region_center(): centroid of the picks - we hand this to check_all_modes()
  as the transport target, so the arrival hub lands in the middle of the
  trip region rather than at some vague state centroid.
"""

from distance import straight_line_distance_km


def order_stops(stops: list[dict], from_lat: float, from_lon: float) -> list[dict]:
    remaining = list(stops)
    route: list[dict] = []
    cur_lat, cur_lon = from_lat, from_lon
    while remaining:
        nxt = min(
            remaining,
            key=lambda s: straight_line_distance_km(cur_lat, cur_lon, s["lat"], s["lon"]),
        )
        route.append(nxt)
        remaining.remove(nxt)
        cur_lat, cur_lon = nxt["lat"], nxt["lon"]
    return route


def split_into_days(ordered: list[dict], num_days: int | None) -> list[dict]:
    n = len(ordered)
    if n == 0:
        return []
    days = max(1, min(num_days or n, n))  # never more days than stops
    out = []
    for i, stop in enumerate(ordered):
        day = i * days // n + 1
        out.append({**stop, "day": day})
    return out


def region_center(stops: list[dict]) -> tuple[float, float]:
    lat = sum(s["lat"] for s in stops) / len(stops)
    lon = sum(s["lon"] for s in stops) / len(stops)
    return lat, lon


def build_itinerary(stops: list[dict], from_lat: float, from_lon: float,
                    num_days: int | None) -> list[dict]:
    """stops -> [{...stop, day}]  in travel order."""
    return split_into_days(order_stops(stops, from_lat, from_lon), num_days)


if __name__ == "__main__":
    picks = [
        {"name": "Kochi", "lat": 9.9312, "lon": 76.2673},
        {"name": "Munnar", "lat": 10.0889, "lon": 77.0595},
        {"name": "Alleppey", "lat": 9.4981, "lon": 76.3388},
        {"name": "Kovalam", "lat": 8.4004, "lon": 76.9787},
        {"name": "Wayanad", "lat": 11.6854, "lon": 76.132},
    ]
    for s in build_itinerary(picks, 16.30, 80.45, 5):  # from Guntur
        print(f"  Day {s['day']}: {s['name']}")
