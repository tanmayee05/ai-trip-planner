"""
Own-vehicle route planning: waypoints along the actual driving route for
fuel, food, and rest stops — based on real elapsed distance/time, not
guesswork, and filtered by the user's stated fuel-brand preference.
"""
import requests
from datetime import datetime, timedelta
from geocoding import reverse_geocode
from routing import get_driving_route_with_geometry
from distance import straight_line_distance_km

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "ai-trip-planner-learning-project"}

# How far apart to consider placing a fuel stop — real cars vary, but this
# is a reasonable average range before "should refuel" makes sense
FUEL_STOP_INTERVAL_KM = 250

# Meal windows — used to decide if a waypoint's estimated arrival time
# lands during a mealtime, worth suggesting food there
MEAL_WINDOWS = {
    "breakfast": (7, 10),
    "lunch": (12, 15),
    "dinner": (19, 22),
}

# Common Indian fuel brands, for matching against OSM's `brand` tag
FUEL_BRAND_TAGS = {
    "hp": "Hindustan Petroleum",
    "bharat": "Bharat Petroleum",
    "indian oil": "Indian Oil",
    "shell": "Shell",
    "reliance": "Reliance",
}


def _point_at_fraction(coordinates: list, fraction: float) -> tuple[float, float]:
    """
    Pick the coordinate roughly `fraction` of the way through the route's
    point list (0.0 = start, 1.0 = end). Simple index-based approximation
    — good enough since ORS returns many closely-spaced points.
    """
    index = int(len(coordinates) * fraction)
    index = min(index, len(coordinates) - 1)
    lon, lat = coordinates[index]  # ORS gives [lon, lat] order
    return lat, lon


def find_fuel_stations_near(lat: float, lon: float, preferred_brands: list[str] | None, radius_km: float = 15) -> tuple[list[dict], bool]:
    """Returns (stations, brand_was_found). If preferred brands were given
    but none found nearby, brand_was_found is False so the caller can
    tell the user honestly instead of silently substituting."""
    radius_m = int(radius_km * 1000)
    query = f'[out:json][timeout:30];nwr["amenity"="fuel"](around:{radius_m},{lat},{lon});out center;'

    try:
        response = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=45)
    except requests.exceptions.RequestException:
        return [], False
    if response.status_code != 200:
        return [], False

    elements = response.json().get("elements", [])
    results = []
    for e in elements:
        tags = e.get("tags", {})
        name = tags.get("name")
        if not name:
            continue  # skip stations with no real name — nothing useful to show the user
        brand = tags.get("brand", "")
        elat = e.get("lat") or e.get("center", {}).get("lat")
        elon = e.get("lon") or e.get("center", {}).get("lon")
        if elat is None:
            continue
        dist = straight_line_distance_km(lat, lon, elat, elon)
        results.append({"name": name, "brand": brand, "lat": elat, "lon": elon, "distance_km": round(dist, 1)})

    results.sort(key=lambda r: r["distance_km"])

    if preferred_brands:
        matching = [r for r in results if any(b.lower() in r["brand"].lower() for b in preferred_brands if r["brand"])]
        if matching:
            return matching[:3], True
        return results[:3], False  # brand not found — caller must say so honestly

    return results[:3], True


def build_fuel_stops(coordinates: list, total_distance_km: float, preferred_brands: list[str] | None) -> list[dict]:
    stops = []
    num_stops = int(total_distance_km // FUEL_STOP_INTERVAL_KM)

    for i in range(1, num_stops + 1):
        fraction = (i * FUEL_STOP_INTERVAL_KM) / total_distance_km
        if fraction >= 1:
            break
        lat, lon = _point_at_fraction(coordinates, fraction)

        area = reverse_geocode(lat, lon)
        area_name = (area.get("town") or area.get("city") or area.get("district")) if area else None

        stations, brand_found = find_fuel_stations_near(lat, lon, preferred_brands)
        stops.append({
            "approx_distance_km": i * FUEL_STOP_INTERVAL_KM,
            "area_name": area_name or "this area",
            "lat": lat, "lon": lon,
            "stations": stations,
            "preferred_brand_found": brand_found,
        })
    return stops


def build_meal_stops(coordinates: list, total_distance_km: float, total_duration_hr: float, start_time: str) -> list[dict]:
    start_dt = datetime.strptime(start_time, "%H:%M")
    start_hour = start_dt.hour

    # If starting during or right after a meal window, suggest eating
    # BEFORE departure instead of stopping mid-drive shortly after leaving
    stops = []
    for meal, (start_h, end_h) in MEAL_WINDOWS.items():
        if start_h <= start_hour < end_h or (meal == "dinner" and start_hour >= 20):
            stops.append({
                "meal": meal, "estimated_time": start_time,
                "approx_distance_km": 0,
                "note": f"You're starting around {meal} time — consider eating before you leave rather than stopping soon after.",
            })
            break  # only the immediately-relevant meal, not all of them

    seen_meals = {s["meal"] for s in stops}
    steps = 20
    for i in range(1, steps + 1):
        fraction = i / steps
        elapsed_hours = total_duration_hr * fraction
        clock_time = start_dt + timedelta(hours=elapsed_hours)
        hour = clock_time.hour
        for meal, (mh_start, mh_end) in MEAL_WINDOWS.items():
            if meal in seen_meals:
                continue
            if mh_start <= hour < mh_end:
                lat, lon = _point_at_fraction(coordinates, fraction)
                stops.append({
                    "meal": meal, "estimated_time": clock_time.strftime("%H:%M"),
                    "approx_distance_km": round(total_distance_km * fraction, 1),
                    "lat": lat, "lon": lon,
                })
                seen_meals.add(meal)
    return stops


def plan_own_vehicle_route(source_lat: float, source_lon: float,
                             destination_lat: float, destination_lon: float,
                             start_time: str, preferred_fuel_brand: str | None = None) -> dict:
    """
    Main entry point: real driving distance/duration, plus fuel and meal
    stop suggestions placed along the ACTUAL route path.
    """
    route = get_driving_route_with_geometry(source_lat, source_lon, destination_lat, destination_lon)
    if not route:
        return {}

    fuel_stops = build_fuel_stops(route["coordinates"], route["distance_km"], preferred_fuel_brand)
    meal_stops = build_meal_stops(route["coordinates"], route["distance_km"], route["duration_hr"], start_time)

    return {
        "distance_km": route["distance_km"],
        "duration_hr": route["duration_hr"],
        "fuel_stops": fuel_stops,
        "meal_stops": meal_stops,
    }


if __name__ == "__main__":
    from geocoding import geocode

    source = geocode("Rebala, Andhra Pradesh")
    destination = geocode("Madikeri, Karnataka")

    plan = plan_own_vehicle_route(
        source["lat"], source["lon"],
        destination["lat"], destination["lon"],
        start_time="06:00",
        preferred_fuel_brand="hp",
    )

    if not plan:
        print("Could not plan the route right now — the routing service may be temporarily unavailable (e.g. daily quota reached). Try again later.")
    else:
        print(f"Total: {plan['distance_km']} km, {plan['duration_hr']} hr\n")

        print("--- Fuel stops ---")
        for stop in plan["fuel_stops"]:
            print(f"~{stop['approx_distance_km']}km in:")
            for s in stop["stations"]:
                print(f"    {s['name']} ({s['brand']}) — {s['distance_km']}km off route")

        print("\n--- Meal stops ---")
        for stop in plan["meal_stops"]:
            print(f"{stop['meal']} around {stop['estimated_time']} (~{stop['approx_distance_km']}km in)")