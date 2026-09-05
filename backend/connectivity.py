"""
Connectivity checker: given a source and destination, find which nearby
hubs (train/bus/flight) actually reach the destination, ranked by
admin-proximity tier first (same district > same state > elsewhere),
then by distance within a tier.
"""
from datetime import datetime

from hubs import get_nearby_place_candidates, list_nearby_train_stations, list_nearby_bus_or_flight
from geocoding import geocode, reverse_geocode
from distance import straight_line_distance_km
from routing import get_driving_route
from flight_lookup import get_destinations_from, find_connecting_flights
from train_lookup import find_station_by_name, find_connecting_trains

AUTO_FARE_PER_KM = 15
LOCAL_BUS_FARE_PER_KM = 2

# list_nearby_train_stations() also returns far-away regional junctions (good
# for "which hubs exist", wrong for "where can THIS traveller realistically
# board / get off"). Cap the connectivity check to stations within a sane
# drive of each end. The destination cap is looser because some places
# (Coorg) have no closer railhead than ~120 km (Mysuru).
MAX_SOURCE_STATION_KM = 150
MAX_DEST_RAILHEAD_KM = 250
MAX_DEST_AIRPORT_KM = 200
# an arrival hub is only useful if the destination is a reasonable drive
# from it. A direct train/flight to a hub 280 km from the destination is not
# really "reaching" it.
MAX_LAST_MILE_KM = 175

# roads wind ~30% longer than the straight line, and a shared taxi / bus
# on a state highway averages ~40 km/h once you include stops
ROAD_DETOUR_FACTOR = 1.3
ROAD_AVG_SPEED_KMH = 40


# --------------------------------------------------------------------------
# Administrative-proximity ranking (same district > same state > elsewhere)
# --------------------------------------------------------------------------
# reverse_geocode() is a network call limited to ~1 req/s. Memoise it for the
# run so ranking a dozen hubs doesn't cost a dozen slow round-trips.
_admin_cache: dict[tuple, dict] = {}


def get_admin_hierarchy(lat: float, lon: float) -> dict:
    key = (round(lat, 4), round(lon, 4))
    if key not in _admin_cache:
        address = reverse_geocode(lat, lon)
        _admin_cache[key] = {
            "district": address.get("district") if address else None,
            "state": address.get("state") if address else None,
        }
    return _admin_cache[key]


def _admin_tier(hub_admin: dict, dest_admin: dict) -> int:
    """1 = hub is in the destination's district, 2 = same state, 3 = elsewhere."""
    if dest_admin["district"] and hub_admin["district"] == dest_admin["district"]:
        return 1
    if dest_admin["state"] and hub_admin["state"] == dest_admin["state"]:
        return 2
    return 3


def rank_dest_hubs(hubs: list[dict], destination_lat: float, destination_lon: float) -> list[dict]:
    """
    Order destination-side arrival hubs by ADMINISTRATIVE proximity first,
    physical distance second:

      tier 1  same district as the destination
      tier 2  same state
      tier 3  another state

    So for a Kerala destination the Kerala hubs come first, and the
    physically-closer Tamil Nadu / Karnataka hubs are DROPPED entirely as
    long as at least one in-state hub exists. Only if the destination's own
    state has nothing within reach do we fall back to neighbouring states.
    """
    dest_admin = get_admin_hierarchy(destination_lat, destination_lon)
    ranked = []
    for h in hubs:
        a = get_admin_hierarchy(h["lat"], h["lon"])
        ranked.append({
            **h,
            "admin_tier": _admin_tier(a, dest_admin),
            "admin_state": a["state"],
            "admin_district": a["district"],
        })
    # In-state hubs always come first (tier 1/2), sorted by distance; an
    # out-of-state hub is kept only if it's genuinely one of the 4 nearest
    # overall (a closer railhead across a state line is still worth showing).
    nearest_by_dist = sorted(ranked, key=lambda h: h["distance_km"])
    top4_names = {h["name"] for h in nearest_by_dist[:4]}
    ranked = [h for h in ranked if h["admin_tier"] <= 2 or h["name"] in top4_names]
    ranked.sort(key=lambda h: (h["admin_tier"], h["distance_km"]))
    return ranked


# --------------------------------------------------------------------------
# Last-mile estimate (hub -> actual destination, when they're not the same place)
# --------------------------------------------------------------------------
def _fare_options(distance_km: float) -> list[dict]:
    return [
        {"mode": "local_bus", "estimated_fare": round(distance_km * LOCAL_BUS_FARE_PER_KM)},
        {"mode": "auto", "estimated_fare": round(distance_km * AUTO_FARE_PER_KM)},
    ]


def estimate_last_mile(hub_lat: float, hub_lon: float, destination_lat: float, destination_lon: float) -> dict:
    route = get_driving_route(hub_lat, hub_lon, destination_lat, destination_lon)
    if route:
        return {
            "distance_km": route["distance_km"],
            "duration_hr": route["duration_hr"],
            "estimated": False,
            "options": _fare_options(route["distance_km"]),
        }

    # ORS failed (commonly: the arrival hub's map point sits on a runway or
    # a field, not a road, so it returns 404 "no routable point"). Fall back
    # to a straight-line estimate instead of returning nothing.
    crow_km = straight_line_distance_km(hub_lat, hub_lon, destination_lat, destination_lon)
    approx_km = round(crow_km * ROAD_DETOUR_FACTOR, 1)
    return {
        "distance_km": approx_km,
        "duration_hr": round(approx_km / ROAD_AVG_SPEED_KMH, 1),
        "estimated": True,  # rough — no real routing was available
        "options": _fare_options(approx_km),
    }


def _clean_district(name: str) -> str:
    """'Sri Potti Sriramulu Nellore' -> 'Nellore' : drop the honorific/admin
    prefixes AP districts carry, so the name geocodes to the actual city."""
    for prefix in ("Sri Potti Sriramulu ", "Dr. B.R. Ambedkar ", "Dr. B. R. Ambedkar ", "YSR "):
        name = name.replace(prefix, "")
    return name.replace(" District", "").strip()


# --------------------------------------------------------------------------
# "Why this option" — a plain-English rationale for the recommended plan
# --------------------------------------------------------------------------
def _weekday(travel_date: str) -> str:
    try:
        return datetime.strptime(travel_date, "%Y-%m-%d").strftime("%A")
    except ValueError:
        return travel_date


def _short(station_or_hub_name: str) -> str:
    """'MYSORE JN - MYS' -> 'MYSORE JN' ; airport names pass through unchanged."""
    return station_or_hub_name.split(" - ")[0]


def _arrival_tier_reason(tier: int, arrival_state: str | None) -> str:
    return {
        1: "it is in the same district as the destination",
        2: f"it is in {arrival_state}, the same state as the destination",
        3: f"it is in {arrival_state} (a neighbouring state) - no same-state hub had a service that day",
    }.get(tier, "it is the closest usable hub")


def _last_mile_phrase(last_mile: dict) -> str:
    if not last_mile:
        return "."
    est = " (estimated)" if last_mile.get("estimated") else ""
    return (f"; from there the destination is {last_mile['distance_km']} km / "
            f"{last_mile['duration_hr']} hr by road{est}.")


def _explain_choice(mode: str, rec: dict, all_source_hubs: list[dict],
                    working_names: set, travel_date: str) -> str:
    """Build the 'why we picked this source hub, this arrival hub, on this
    date' paragraph for the recommended option (train or flight)."""
    board_verb = "Board at" if mode == "train" else "Fly from"
    src_label = _short(rec["name"])
    arrival_key = "arrival_station" if mode == "train" else "arrival_airport"
    services_key = "trains_available" if mode == "train" else "flights_available"
    service_word = "train" if mode == "train" else "flight"

    parts = []

    # 1. why THIS source hub — were there closer ones we had to skip?
    nearer_skipped = [
        h for h in all_source_hubs
        if h["distance_km"] < rec["distance_km"] and h["name"] not in working_names
    ]
    if nearer_skipped:
        listed = ", ".join(f"{_short(h['name'])} ({h['distance_km']} km)" for h in nearer_skipped)
        parts.append(
            f"{board_verb} {src_label} ({rec['distance_km']} km from the source). "
            f"{listed} {'is' if len(nearer_skipped) == 1 else 'are'} closer, but no direct "
            f"{service_word} runs from there to a usable arrival hub on "
            f"{travel_date} ({_weekday(travel_date)}), so {src_label} is the nearest that works."
        )
    else:
        parts.append(
            f"{board_verb} {src_label} ({rec['distance_km']} km from the source) — the nearest "
            f"hub with a direct same-day {service_word} toward the destination."
        )

    # 2. the actual service on that date
    services = rec.get(services_key) or []
    if services:
        s0 = services[0]
        more = f" (+{len(services) - 1} more that day)" if len(services) > 1 else ""
        if mode == "train":
            parts.append(
                f"On {travel_date} train #{s0['train_number']} {s0['train_name']} leaves "
                f"{src_label} at {s0['departure_time']} and reaches {_short(rec[arrival_key])} at "
                f"{s0['arrival_time']}{more}."
            )
        else:
            dep = (s0["departure_time"] or "").split(" ")[-1][:5]
            arr = (s0["arrival_time"] or "").split(" ")[-1][:5]
            parts.append(
                f"On {travel_date} flight {s0['flight_number']} ({s0['airline'] or 'airline n/a'}) "
                f"departs {rec.get('iata')} at {dep} and arrives {rec['arrival_iata']} at {arr}{more}."
            )

    # 3. why THIS arrival hub
    parts.append(
        f"{_short(rec[arrival_key])} is the arrival point because "
        f"{_arrival_tier_reason(rec.get('arrival_admin_tier'), rec.get('arrival_state'))}"
        f"{_last_mile_phrase(rec.get('last_mile') or {})}"
    )
    return " ".join(parts)


def find_destination_hubs(destination_lat: float, destination_lon: float) -> dict:
    """
    Find the stations / airports around the DESTINATION. We keep the full
    lists (not just the single nearest): the closest railhead to Coorg is a
    tiny ghat-section halt with almost no trains, so the train check needs to
    be free to arrive at a bigger station slightly further out (Mysuru).
    """
    place_candidates = get_nearby_place_candidates(destination_lat, destination_lon)
    trains = list_nearby_train_stations(destination_lat, destination_lon, place_candidates)
    flights = list_nearby_bus_or_flight(destination_lat, destination_lon, "flight")
    airports = [f for f in flights if f.get("iata")]
    return {
        "nearest_train": trains[0] if trains else None,
        "train_stations": trains,
        "nearest_flight": airports[0] if airports else None,
        "flight_airports": airports,
    }


# --------------------------------------------------------------------------
# Per-mode connectivity checks
# --------------------------------------------------------------------------

def _looks_like_real_stand(stop: dict) -> bool:
    """A proper bus stand (APSRTC/RTC bus station) vs. a roadside 'bus stop'
    pole that no long-distance bus actually originates from."""
    n = stop["name"].lower()
    return ("bus station" in n or "bus stand" in n or "rtc" in n) and "bus stop" not in n


def check_bus_connectivity(source_lat: float, source_lon: float,
                             destination_name: str | None = None) -> dict:
    """
    We have NO reliable bus schedule data (unlike trains.db / flights.db), so
    we don't claim connectivity. Instead:
      - if the source is a village/hamlet, also look at the DISTRICT HQ, since
        that's where inter-city buses actually start from;
      - hand back the real bus stands we found + a message telling the user
        where to check live availability (RedBus / AbhiBus).
    """
    address = reverse_geocode(source_lat, source_lon) or {}
    is_village = bool(address.get("village") or address.get("hamlet")) and not (
        address.get("city") or address.get("town")
    )

    nearby = list_nearby_bus_or_flight(source_lat, source_lon, "bus")

    district = _clean_district(address.get("district") or "")
    state = address.get("state")
    district_stands: list[dict] = []
    if is_village and district:
        dgeo = geocode(f"{district}, {state}" if state else district)
        if dgeo:
            district_stands = list_nearby_bus_or_flight(dgeo["lat"], dgeo["lon"], "bus")

    # prefer a real APSRTC/RTC stand; fall back to the closest thing we have
    pool = district_stands or nearby
    real_stands = [s for s in pool if _looks_like_real_stand(s)]
    main_stand = real_stands[0] if real_stands else (pool[0] if pool else None)

    where_to_check = "RedBus (redbus.in) or AbhiBus (abhibus.com)"
    dest_txt = f" to {destination_name}" if destination_name else ""
    if main_stand and is_village:
        note = (
            f"'{address.get('village') or 'This place'}' is a village with no bus "
            f"stand of its own. Inter-city buses run from the {district} district "
            f"stand: {main_stand['name']} (~{main_stand['distance_km']} km away). "
            f"We don't have live bus timings - check buses{dest_txt} on {where_to_check}."
        )
    elif main_stand:
        note = (
            f"Nearest bus stand: {main_stand['name']} "
            f"(~{main_stand['distance_km']} km away). "
            f"We don't have live bus timings - check buses{dest_txt} on {where_to_check}."
        )
    else:
        note = (
            f"No mapped bus stand found nearby. "
            f"Check buses{dest_txt} on {where_to_check}."
        )

    return {
        "mode": "bus",
        "all_options": nearby,
        "district_stands": district_stands,
        "working_options": [],  # never "confirmed" — we have no schedule data
        "recommended": main_stand,
        "note": note,
    }


def check_train_connectivity(source_lat: float, source_lon: float,
                               destination_lat: float, destination_lon: float,
                               travel_date: str, dest_hubs: dict) -> dict:
    place_candidates = get_nearby_place_candidates(source_lat, source_lon)
    all_source_stations = list_nearby_train_stations(source_lat, source_lon, place_candidates)

    # keep only stations the traveller can actually get to / board at
    source_stations = sorted(
        (s for s in all_source_stations if s["distance_km"] <= MAX_SOURCE_STATION_KM),
        key=lambda s: s["distance_km"],
    )
    # destination railheads, ordered by admin proximity (same district >
    # same state > other state), then distance
    dest_stations = rank_dest_hubs(
        [s for s in (dest_hubs.get("train_stations") or []) if s["distance_km"] <= MAX_DEST_RAILHEAD_KM],
        destination_lat, destination_lon,
    )

    # No railhead near the destination (e.g. Kodagu/Coorg has no railway) —
    # a train can't get the traveller there, say so instead of silence.
    if not dest_stations:
        return {
            "mode": "train", "all_options": all_source_stations,
            "working_options": [], "recommended": None,
            "note": "No railway station near the destination - train is not a viable mode for this trip.",
        }

    working_options = []
    for station in source_stations:  # nearest boarding station first
        # walk destination railheads in admin-proximity order; keep the first
        # one that BOTH has a same-day direct train AND leaves a sane road
        # transfer to the actual destination
        for dstn in dest_stations:
            trains = find_connecting_trains(station["name"], dstn["name"], travel_date)
            if not trains:
                continue
            last_mile = estimate_last_mile(dstn["lat"], dstn["lon"], destination_lat, destination_lon)
            if last_mile.get("distance_km", 1e9) > MAX_LAST_MILE_KM:
                continue  # train reaches this station, but it's too far from the destination
            working_options.append({
                **station, "reaches_destination": True,
                "arrival_station": dstn["name"],
                "arrival_distance_km": dstn["distance_km"],
                "arrival_state": dstn["admin_state"],
                "arrival_admin_tier": dstn["admin_tier"],
                "trains_available": trains, "last_mile": last_mile,
            })
            break

    # rank: in-state arrival (tier 1 or 2) beats out-of-state, but WITHIN
    # that the nearest boarding hub to the source wins. We don't split hairs
    # between "same district" and "same state" — both are fine — so a closer
    # boarding station is not passed over for a marginally better arrival.
    working_options.sort(
        key=lambda o: (0 if o["arrival_admin_tier"] <= 2 else 1, o["distance_km"]),
    )
    working_names = {o["name"] for o in working_options}
    result = {
        "mode": "train",
        "all_options": source_stations,
        "dest_hubs_considered": [
            f"{s['name']} [{s['admin_state']}, tier {s['admin_tier']}, {s['distance_km']} km from dest]"
            for s in dest_stations
        ],
        "working_options": working_options,
        "recommended": working_options[0] if working_options else None,
    }
    if working_options:
        result["recommended_reason"] = _explain_choice(
            "train", working_options[0], source_stations, working_names, travel_date
        )
    else:
        arrivals = ", ".join(s["name"] for s in dest_stations[:3])
        result["note"] = (
            f"Stations near the source exist, but no direct same-day train runs from "
            f"any of them to the destination's railheads ({arrivals}) on {travel_date}. "
            f"A connecting journey (change trains) may still be possible."
        )
    return result


def check_flight_connectivity(source_lat: float, source_lon: float,
                                destination_lat: float, destination_lon: float,
                                travel_date: str, dest_hubs: dict) -> dict:
    nearby_airports = [a for a in list_nearby_bus_or_flight(source_lat, source_lon, "flight") if a.get("iata")]

    # airports near the DESTINATION, ordered by admin proximity (same
    # district > same state > other state), then distance. This is why
    # Madikeri prefers Mysuru/Mangaluru (Karnataka) over the closer Kannur
    # (Kerala), and only falls through to Kannur if nothing flies to the
    # Karnataka airports that day.
    dest_airports = rank_dest_hubs(
        [a for a in (dest_hubs.get("flight_airports") or []) if a["distance_km"] <= MAX_DEST_AIRPORT_KM],
        destination_lat, destination_lon,
    )
    if not dest_airports:
        return {
            "mode": "flight", "all_options": nearby_airports, "working_options": [], "recommended": None,
            "note": "No airport with a known code found near the destination.",
        }

    working_options = []
    for airport in nearby_airports:  # nearest source airport first
        for dstn in dest_airports:  # admin-proximity order
            destinations = get_destinations_from(
                airport["iata"], airport["name"], airport["lat"], airport["lon"], travel_date
            )
            if not any(d["iata"] == dstn["iata"] for d in destinations):
                continue
            last_mile = estimate_last_mile(dstn["lat"], dstn["lon"], destination_lat, destination_lon)
            if last_mile.get("distance_km", 1e9) > MAX_LAST_MILE_KM:
                continue
            working_options.append({
                **airport, "reaches_destination": True,
                "arrival_airport": dstn["name"], "arrival_iata": dstn["iata"],
                "arrival_distance_km": dstn["distance_km"],
                "arrival_state": dstn["admin_state"],
                "arrival_admin_tier": dstn["admin_tier"],
                "flights_available": find_connecting_flights(airport["iata"], dstn["iata"], travel_date),
                "last_mile": last_mile,
            })
            break

    # in-state arrival beats out-of-state; within that, nearest source airport wins
    working_options.sort(
        key=lambda o: (0 if o["arrival_admin_tier"] <= 2 else 1, o["distance_km"]),
    )
    working_names = {o["name"] for o in working_options}
    result = {
        "mode": "flight", "all_options": nearby_airports,
        "dest_hubs_considered": [
            f"{a['name']} ({a['iata']}) [{a['admin_state']}, tier {a['admin_tier']}, {a['distance_km']} km from dest]"
            for a in dest_airports
        ],
        "working_options": working_options,
        "recommended": working_options[0] if working_options else None,
    }
    if working_options:
        result["recommended_reason"] = _explain_choice(
            "flight", working_options[0], nearby_airports, working_names, travel_date
        )
    else:
        checked = ", ".join(a["name"] for a in dest_airports[:4])
        result["note"] = (
            f"No source airport has a same-day flight to any airport near the "
            f"destination ({checked}) on {travel_date}."
        )
    return result


def check_all_modes(source_lat: float, source_lon: float,
                     destination_lat: float, destination_lon: float, travel_date: str,
                     destination_name: str | None = None) -> dict:
    # Compute destination hubs ONCE, share across train and flight checks —
    # this halves the Overpass load compared to before.
    dest_hubs = find_destination_hubs(destination_lat, destination_lon)

    return {
        "train": check_train_connectivity(source_lat, source_lon, destination_lat, destination_lon, travel_date, dest_hubs),
        "bus": check_bus_connectivity(source_lat, source_lon, destination_name),
        "flight": check_flight_connectivity(source_lat, source_lon, destination_lat, destination_lon, travel_date, dest_hubs),
    }

if __name__ == "__main__":
    from geocoding import geocode

    source = geocode("Rebala, Andhra Pradesh")
    destination = geocode("coorg, Karnataka")  # Coorg's actual main town, not the district centroid

    print("Source:", source)
    print("Destination:", destination)

    result = check_all_modes(
        source["lat"], source["lon"],
        destination["lat"], destination["lon"],
        travel_date="2026-09-15",
        destination_name="Madikeri",
    )

    for mode, data in result.items():
        print(f"\n=== {mode.upper()} ===")

        if data["working_options"]:
            print("Confirmed working (nearest boarding point first):")
            for o in data["working_options"]:
                lm = o.get("last_mile") or {}
                lm_txt = ""
                if lm:
                    tag = " est." if lm.get("estimated") else ""
                    lm_txt = f"  ->  then {lm['distance_km']} km / {lm['duration_hr']} hr road{tag} to destination"
                tier_txt = {1: "same district", 2: "same state", 3: "other state"}.get(o.get("arrival_admin_tier"), "")

                def _hhmm(t: str) -> str:
                    # "2026-09-15 06:30+05:30" -> "06:30" ; "14:25" -> "14:25"
                    return t.split(" ")[1][:5] if t and " " in t else (t or "?")

                if mode == "train":
                    src_short = o["name"].split(" - ")[0]
                    dst_short = o["arrival_station"].split(" - ")[0]
                    print(f"  board {o['name']} ({o['distance_km']} km away) "
                          f"-> arrive {o['arrival_station']} [{o.get('arrival_state')}, {tier_txt}]{lm_txt}")
                    for t in o.get("trains_available", []):
                        print(f"      #{t['train_number']}  {t['train_name']} ({t['train_class']})  |  "
                              f"dep {src_short} {t['departure_time']}  ->  arr {dst_short} {t['arrival_time']}")
                elif mode == "flight":
                    print(f"  fly from {o['name']} ({o.get('iata')}) "
                          f"-> arrive {o['arrival_airport']} [{o.get('arrival_state')}, {tier_txt}]{lm_txt}")
                    for f in o.get("flights_available", []):
                        print(f"      {f['flight_number']}  {f['airline'] or 'airline n/a'}  |  "
                              f"dep {o.get('iata')} {_hhmm(f['departure_time'])}  ->  "
                              f"arr {o['arrival_iata']} {_hhmm(f['arrival_time'])}")
        else:
            print("Confirmed working: none")

        # show the near-source hubs that were checked but don't connect, so
        # it's clear they weren't just missed (e.g. Nellore has no direct
        # train onward to a railhead near Coorg)
        if mode in ("train", "flight"):
            if data.get("dest_hubs_considered"):
                print("Destination-side arrival hubs considered:", ", ".join(data["dest_hubs_considered"]))
            working_names = {o["name"] for o in data["working_options"]}
            not_connecting = [o for o in data.get("all_options", []) if o["name"] not in working_names]
            if not_connecting:
                print("Near the source but no direct same-day service to the destination:")
                for o in not_connecting:
                    print(f"  {o['name']} ({o['distance_km']} km away)")

        rec = data["recommended"]
        print("Recommended:", rec["name"] if rec else "none confirmed")
        if data.get("recommended_reason"):
            print("Why:", data["recommended_reason"])
        if "note" in data:
            print("Note:", data["note"])