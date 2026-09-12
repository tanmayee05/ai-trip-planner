"""
The plan in plain English: "catch the 06:10 train, check in, then the temple".

A list of place names per day tells you WHAT, never WHEN or in WHAT ORDER. This
turns the structured plan into the thing a traveller actually reads the night
before — a running schedule with clock times, the transport they chose, the
hotel check-in, and the drive between each stop.

Deterministic on purpose. Every time here comes from the same visit-length and
driving figures the planner packed the days with (feasibility.py), so the
schedule can't drift from the itinerary it describes. An LLM would write
smoother prose and quietly invent a 4pm train.
"""
from feasibility import travel_hours, visit_hours

DAY_START_H = 9.0          # a normal touring start
FIRST_DAY_START_H = 7.0    # travel days begin early
CHECKIN_H = 0.5            # dropping bags and checking in
MEAL_H = 1.0               # a sit-down lunch


def _clock(hours: float) -> str:
    """9.5 -> '09:30'. Wraps past midnight rather than printing '25:00'."""
    h = int(hours) % 24
    m = int(round((hours - int(hours)) * 60))
    if m == 60:
        h, m = (h + 1) % 24, 0
    return f"{h:02d}:{m:02d}"


def _mode_phrase(transport: dict, travel_mode: str) -> tuple[str, float | None]:
    """How they're getting there, and how long it takes."""
    if travel_mode == "own_vehicle":
        drive = (transport or {}).get("drive") or {}
        hrs = drive.get("duration_hr")
        km = drive.get("distance_km")
        if km:
            return (f"Set off in your own vehicle — about {km} km, "
                    f"{hrs:.1f} hours of driving" if hrs else
                    f"Set off in your own vehicle — about {km} km"), hrs
        return "Set off in your own vehicle", hrs

    # public transport: name the recommended service if we confirmed one
    for mode, verb in (("train", "train"), ("bus", "bus"), ("flight", "flight")):
        sect = (transport or {}).get(mode) or {}
        rec = sect.get("recommended")
        if not rec:
            continue
        services = rec.get("trains_available") or rec.get("flights_available") or []
        first = services[0] if services else None
        board = rec.get("name", "the station")
        arrive = rec.get("arrival_station") or rec.get("arrival_airport") or "your arrival point"
        last_mile = (rec.get("last_mile") or {}).get("duration_hr")
        if first:
            dep = (first.get("departure_time") or "").split(" ")[-1][:5]
            num = first.get("train_number") or first.get("flight_number") or ""
            label = f"{verb} {num}".strip()
            line = (f"Board the {label} at {board}"
                    + (f" (departs {dep})" if dep else "")
                    + f", arriving {arrive}")
        else:
            line = f"Take a {verb} from {board} to {arrive}"
        if last_mile:
            line += f", then about {last_mile:.1f} h by road to your first stop"
        return line, None

    return "Travel to your destination by bus or train (check timings locally)", None


def build_narrative(result: dict, *, source: str, destination: str,
                    travel_mode: str, num_days: int | None) -> list[dict]:
    """`[{day, title, steps: [{time, text}]}]` — the trip read as a schedule."""
    itinerary = result.get("itinerary") or []
    stays = {s["day"]: s for s in (result.get("itinerary_stays") or [])}
    notes = {n["day"]: n.get("rationale") for n in (result.get("itinerary_notes") or [])}

    by_day: dict[int, list[dict]] = {}
    for st in itinerary:
        by_day.setdefault(st["day"], []).append(st)
    total_days = max([num_days or 0] + list(by_day) + list(stays)) or 1

    days: list[dict] = []
    for day in range(1, total_days + 1):
        stops = by_day.get(day, [])
        stay = stays.get(day) or {}
        steps: list[dict] = []
        t = FIRST_DAY_START_H if day == 1 else DAY_START_H

        if day == 1:
            line, hrs = _mode_phrase(result, travel_mode)
            steps.append({"time": _clock(t), "text": f"{line}."})
            t += hrs if hrs else 4.0

            hotel = (stay.get("stay") or [{}])[0].get("name") if stay.get("stay") else None
            where = stay.get("town") or destination
            steps.append({
                "time": _clock(t),
                "text": (f"Reach {where} and check in"
                         + (f" at {hotel}" if hotel else " at your hotel")
                         + " — drop your bags before heading out."),
            })
            t += CHECKIN_H
        elif stay.get("stay") or stops:
            steps.append({
                "time": _clock(t),
                "text": "Breakfast and check out of your room for the day ahead."
                        if day == total_days else "Breakfast, then out for the day.",
            })
            t += 0.5

        prev = None
        for i, st in enumerate(stops):
            if prev is not None:
                hop = travel_hours(prev, st)
                if hop >= 0.25:
                    steps.append({
                        "time": _clock(t),
                        "text": f"Drive on to {st['name']} — roughly {hop:.1f} h on the road.",
                    })
                    t += hop
            visit = visit_hours(st)
            steps.append({
                "time": _clock(t),
                "text": (f"{'First stop' if i == 0 else 'Next'}: {st['name']}"
                         + (f" ({st['category']})" if st.get("category") else "")
                         + f" — allow about {visit:.1f} h."),
            })
            t += visit
            # a long day earns a sit-down meal roughly in the middle
            if i == 0 and len(stops) > 1 and t < 14.0:
                food = (stay.get("food") or [{}])[0].get("name") if stay.get("food") else None
                steps.append({
                    "time": _clock(t),
                    "text": f"Lunch — {food} is nearby." if food else "Break for lunch.",
                })
                t += MEAL_H
            prev = st

        if not stops:
            steps.append({
                "time": _clock(t),
                "text": ("Nothing scheduled — a free day to rest, or to start home early."
                         if day > 1 else "Travel day, no sightseeing planned."),
            })

        # Don't leave an unexplained hole. A day that finishes its sights at
        # 13:00 and then shows "19:00 back to the hotel" reads as a gap in the
        # plan; saying the afternoon is free is both true and useful.
        evening = 19.0 if day < total_days else 16.0
        if stops and evening - t >= 2.0:
            steps.append({
                "time": _clock(t),
                "text": ("Rest of the day free — wander, rest, or add something nearby "
                         "if you're up for it."),
            })

        if day < total_days:
            hotel = (stay.get("stay") or [{}])[0].get("name") if stay.get("stay") else None
            food = (stay.get("food") or [{}])[0].get("name") if stay.get("food") else None
            night = stay.get("town") or destination
            text = f"Back to {hotel} for the night." if hotel else f"Settle in for the night near {night}."
            if food:
                text += f" Dinner at {food}."
            steps.append({"time": _clock(max(t, evening)), "text": text})
        else:
            # nothing planned at all? then leaving in the morning is the sane
            # advice, not hanging around until the afternoon
            depart = max(t, 10.0) if not stops else max(t, evening)
            steps.append({
                "time": _clock(depart),
                "text": f"Start back to {source} — that's the trip.",
            })

        days.append({
            "day": day,
            "title": notes.get(day) or (
                f"Travel to {destination}" if day == 1 else
                f"Head home to {source}" if day == total_days else
                f"Day {day} in {destination}"
            ),
            "steps": steps,
        })
    return days
