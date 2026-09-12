"""
How long a set of places ACTUALLY takes — the arithmetic behind "is 3 days
enough for these six stops?".

Why this exists
---------------
The planner used to split places evenly across whatever number of days it was
given (`itinerary.split_into_days`: `day = i * days // n + 1`). That is not how
anyone plans a trip. It cheerfully puts a tiger reserve and a hill station
120 km apart on the same afternoon, and it never says "that's too much" —
because it has no notion of a place taking time, or of the road between two
places taking time.

So: every place gets a realistic visit length by category, every hop gets a
realistic road duration, and a day gets a realistic budget of hours. From those
three we can pack days the way a person would, and answer the question the
traveller actually cares about — is this trip length sensible?

All deterministic. No LLM: this runs on every plan, and it should be
explainable ("Munnar needs about 6 hours, and it's 3 hours from Kochi")
rather than merely plausible-sounding.
"""
from distance import straight_line_distance_km
from itinerary import order_stops

# Roughly how long you'd actually spend, by the categories attractions.py
# emits. These are "a normal visitor, not rushing and not lingering" figures.
# Tuned for a traveller who wants to SEE the place and move on, not one who
# lingers. The earlier figures were a relaxed pace and they inflated trip
# lengths badly — ten Kerala places came out at nine days, which is holiday
# advice nobody asked for. These are "the main sights, unhurried but
# purposeful".
VISIT_HOURS: dict[str, float] = {
    "wildlife": 4.0,      # a safari slot plus the gate formalities
    "hill station": 4.0,  # the main viewpoints, not every tea estate
    "backwater": 3.5,     # the standard half-day cruise
    "city": 3.0,          # the headline sights of a city
    "beach": 2.0,
    "heritage": 2.0,
    "fort": 2.0,
    "waterfall": 1.5,
    "temple": 1.0,
    "lake": 1.0,
    "other": 1.5,
}
DEFAULT_VISIT_HOURS = 2.0

# Roads wind ~30% longer than the crow flies, and an Indian state highway
# averages ~40 km/h once you include towns, junctions and breaks.
ROAD_DETOUR = 1.3
ROAD_SPEED_KMH = 40.0

# A day's touring budget. An early start and a proper day out — 8am to about
# 6:30pm — which is what people actually do on a trip they've travelled far for.
DAY_HOURS = 10.5
# Day one is eaten into by getting there, the last day by heading home.
FIRST_DAY_HOURS = 5.5
LAST_DAY_HOURS = 6.5
# A plan is only called impractical past this much overrun, so a day that runs
# slightly long isn't rejected for being ambitious.
OVERRUN_TOLERANCE = 1.25

# Places within this of each other belong to the same "area" and should share a
# day if they can. This is what makes a plan read like a person's: you do
# Fort Kochi and the Chinese fishing nets together, then move on — you don't
# do one of them, drive 90 km, and come back tomorrow.
CLUSTER_RADIUS_KM = 35.0
# Crossing into the next area mid-day is allowed only when this much touring
# time would still be left after the drive. Enough room and it's a sensible
# push-on; anything less and you'd be spending the afternoon in the car to tick
# off one more thing, which is the behaviour we're trying to avoid.
CROSS_AREA_MIN_REMAINING_H = 3.0


def visit_hours(stop: dict) -> float:
    cat = (stop.get("category") or "").strip().lower()
    return VISIT_HOURS.get(cat, DEFAULT_VISIT_HOURS)


def travel_hours(a: dict, b: dict) -> float:
    km = straight_line_distance_km(a["lat"], a["lon"], b["lat"], b["lon"]) * ROAD_DETOUR
    return km / ROAD_SPEED_KMH


def day_budget(day: int, total_days: int) -> float:
    """The hours available on a given day of the trip."""
    if day == 1:
        return FIRST_DAY_HOURS
    if total_days > 1 and day == total_days:
        return LAST_DAY_HOURS
    return DAY_HOURS


def day_load(stops_in_day: list[dict], from_stop: dict | None = None) -> float:
    """Hours a day's stops really cost: time at each place, the road between
    them, and — crucially — the drive from wherever the night was spent to the
    first stop of the day.

    That last term is easy to forget and it matters: you sleep near the last
    place you visited, so a day that opens with a 4-hour transfer has barely
    5 hours left in it. Leaving it out made the packing far too optimistic.
    """
    if not stops_in_day:
        return 0.0
    hours = sum(visit_hours(s) for s in stops_in_day)
    for a, b in zip(stops_in_day, stops_in_day[1:]):
        hours += travel_hours(a, b)
    if from_stop is not None:
        hours += travel_hours(from_stop, stops_in_day[0])
    return hours


def cluster_stops(stops: list[dict], radius_km: float = CLUSTER_RADIUS_KM) -> list[list[dict]]:
    """Group places into areas you'd naturally do in one go.

    Single-link: two places join the same area if they're within `radius_km` of
    each other, which chains along a corridor of sights the way a real day does.
    """
    remaining = list(stops)
    clusters: list[list[dict]] = []
    while remaining:
        group = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            for cand in list(remaining):
                if any(
                    straight_line_distance_km(cand["lat"], cand["lon"], m["lat"], m["lon"])
                    <= radius_km
                    for m in group
                ):
                    group.append(cand)
                    remaining.remove(cand)
                    changed = True
        clusters.append(group)
    return clusters


def _centroid(group: list[dict]) -> tuple[float, float]:
    return (sum(g["lat"] for g in group) / len(group),
            sum(g["lon"] for g in group) / len(group))


def _cluster_route_km(order: list[list[dict]], from_lat: float, from_lon: float) -> float:
    """Total crow-flies distance of a cluster sequence, start point included."""
    pts = [(from_lat, from_lon)] + [_centroid(g) for g in order]
    return sum(
        straight_line_distance_km(a[0], a[1], b[0], b[1])
        for a, b in zip(pts, pts[1:])
    )


def _improve_cluster_order(order: list[list[dict]], from_lat: float,
                           from_lon: float) -> list[list[dict]]:
    """Take the crossings out of a greedy cluster sequence (2-opt).

    Nearest-centroid-first is myopic: on a long north-to-south region it will
    run down to the coast, jump back inland for the hill stations, then return
    south again. On a real Kerala set that backtrack cost ~200 km and a whole
    extra day. Reversing any segment that shortens the whole route removes
    those crossings, and with a handful of areas it's instant.
    """
    if len(order) < 4:
        return order
    best = list(order)
    best_km = _cluster_route_km(best, from_lat, from_lon)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 2, len(best)):
                cand = best[:i + 1] + best[i + 1:j + 1][::-1] + best[j + 1:]
                km = _cluster_route_km(cand, from_lat, from_lon)
                if km < best_km - 0.5:      # ignore noise-level gains
                    best, best_km, improved = cand, km, True
    return best


def order_by_cluster(stops: list[dict], from_lat: float, from_lon: float) -> list[dict]:
    """Visiting order that finishes one area before starting the next.

    Plain nearest-neighbour over individual places (what this used to do) can
    zig-zag out of an area and back into it, which is how you end up with two
    places 90 km apart sharing an afternoon. Here the AREAS are walked
    nearest-first, and within an area the places are walked nearest-first from
    wherever you entered it.
    """
    if not stops:
        return []
    clusters = cluster_stops(stops)

    # greedy nearest-area sequence, then straightened out
    greedy: list[list[dict]] = []
    cur_lat, cur_lon = from_lat, from_lon
    pool = list(clusters)
    while pool:
        nxt = min(pool, key=lambda g: straight_line_distance_km(cur_lat, cur_lon, *_centroid(g)))
        pool.remove(nxt)
        greedy.append(nxt)
        cur_lat, cur_lon = _centroid(nxt)
    sequence = _improve_cluster_order(greedy, from_lat, from_lon)

    ordered: list[dict] = []
    cur_lat, cur_lon = from_lat, from_lon
    area = 0
    for nxt in sequence:
        # inside the area, nearest-first from where we came in
        inner = order_stops(nxt, cur_lat, cur_lon)
        # `_area` rides along so pack_days can keep an area's places together;
        # it's stripped before anything is shown or stored
        ordered.extend({**st, "_area": area} for st in inner)
        cur_lat, cur_lon = inner[-1]["lat"], inner[-1]["lon"]
        area += 1
    return ordered


def pack_days(ordered: list[dict], max_days: int | None = None) -> list[list[dict]]:
    """Fill one day until it's full, then start the next — how a person plans.
    `max_days` caps the result, with the leftovers pushed into the final day so
    nothing is silently dropped."""
    days: list[list[dict]] = []
    current: list[dict] = []

    for stop in ordered:
        if not current:
            # a day always takes at least one place — you can't split a stop
            current = [stop]
            continue
        # while packing we don't yet know the trip length, so budget the first
        # day tightly and every later day fully
        budget = FIRST_DAY_HOURS if not days else DAY_HOURS
        base = days[-1][-1] if days else None      # last night's stop
        hop = travel_hours(current[-1], stop)
        load = day_load(current, base)
        same_area = stop.get("_area") == current[-1].get("_area")

        if not same_area:
            # An area is always finished before the next is started. Moving on
            # the SAME day is allowed only if, after the drive, there's still a
            # real block of touring time left — otherwise you spend the
            # afternoon in the car to tick off one more place, and sleep
            # somewhere with half the area unseen. With room, pushing on saves a
            # whole day; without it, tomorrow's morning transfer is better.
            remaining = budget - load - hop
            if remaining < CROSS_AREA_MIN_REMAINING_H:
                days.append(current)
                current = [stop]
            elif load + hop + visit_hours(stop) > budget:
                days.append(current)
                current = [stop]
            else:
                current.append(stop)
        elif load + hop + visit_hours(stop) > budget:
            # same area, but the day is full — it spills into tomorrow
            days.append(current)
            current = [stop]
        else:
            current.append(stop)
    if current:
        days.append(current)

    if max_days and len(days) > max_days:
        # squeeze the tail into the last allowed day — the caller is telling us
        # this is all the time there is, and `assess` will have said so
        head, tail = days[: max_days - 1], days[max_days - 1:]
        days = head + [[s for d in tail for s in d]]
    return days


def split_by_what_fits(stops: list[dict], num_days: int | None,
                       from_lat: float, from_lon: float) -> tuple[list[dict], list[dict]]:
    """`(will_fit, wont_fit)` for the time available.

    When there isn't enough time, the honest answer is a shorter plan plus a
    clear list of what had to be left out — NOT every place crammed in and a
    day labelled "extremely heavy". A 15-hour departure day is not a plan, it's
    a plan-shaped object; the traveller can't act on it, and it makes every
    other number in the trip (food, hotels, budget) wrong too.
    """
    if not stops:
        return [], []
    ordered = order_by_cluster(stops, from_lat, from_lon)
    if not num_days:
        return ordered, []

    kept: list[list[dict]] = []
    current: list[dict] = []
    for stop in ordered:
        day_index = len(kept) + 1
        if day_index > num_days:
            break
        budget = day_budget(day_index, num_days)
        if not current:
            current = [stop]
            continue
        base = kept[-1][-1] if kept else None
        added = travel_hours(current[-1], stop) + visit_hours(stop)
        if day_load(current, base) + added > budget:
            kept.append(current)
            current = []
            if len(kept) >= num_days:
                break
            current = [stop]
        else:
            current.append(stop)
    if current and len(kept) < num_days:
        kept.append(current)

    fits = strip_area([s for day in kept for s in day])
    fit_names = {s["name"] for s in fits}
    return fits, strip_area([s for s in ordered if s["name"] not in fit_names])


def strip_area(stops: list[dict]) -> list[dict]:
    """Drop the internal `_area` tag before a plan is shown or stored."""
    return [{k: v for k, v in st.items() if k != "_area"} for st in stops]


def needed_days(stops: list[dict], from_lat: float, from_lon: float) -> int:
    """How many days these places actually want, at a comfortable pace."""
    if not stops:
        return 0
    return len(pack_days(order_by_cluster(stops, from_lat, from_lon)))


def assess(stops: list[dict], num_days: int | None,
           from_lat: float, from_lon: float) -> dict:
    """Is the trip length sensible for these places?

    "too_short" and "too_long" are both worth saying out loud: cramming six
    places into two days ruins them, and booking six days for two days of
    sights is a different kind of mistake.
    """
    if not stops:
        return {"verdict": "ok", "needed_days": 0, "given_days": num_days or 0,
                "places": 0, "message": None, "options": []}

    ordered = order_by_cluster(stops, from_lat, from_lon)
    need = len(pack_days(ordered))
    given = num_days or need
    n = len(stops)
    # visit time plus every hop along the route, which is the same accounting
    # pack_days uses — so the headline figure and the day split can't disagree
    hours = sum(visit_hours(s) for s in stops)
    hours += sum(travel_hours(a, b) for a, b in zip(ordered, ordered[1:]))

    out = {
        "verdict": "ok",
        "needed_days": need,
        "given_days": given,
        "places": n,
        "total_hours": round(hours, 1),
        "per_place": [
            {"name": s["name"], "hours": visit_hours(s),
             "category": (s.get("category") or "other")}
            for s in ordered
        ],
        "message": None,
        "options": [],
    }

    if given < need:
        short_by = need - given
        out.update({
            "verdict": "too_short",
            "short_by": short_by,
            "message": (
                f"{n} places is a lot for {given} day{'s' if given != 1 else ''} — at a "
                f"comfortable pace they need about {need}. As it stands you'd spend most "
                f"of the trip on the road. Want to add {short_by} more "
                f"day{'s' if short_by != 1 else ''}, or drop a few of the "
                f"furthest-out places?"
            ),
            "options": [
                f"Add {short_by} more day" + ("s" if short_by != 1 else ""),
                "Drop the furthest places",
                "Keep it as it is",
            ],
        })
    elif given >= need + 2:
        spare = given - need
        out.update({
            "verdict": "too_long",
            "spare_days": spare,
            "message": (
                f"These {n} places fit comfortably into about {need} "
                f"day{'s' if need != 1 else ''}, so {given} leaves {spare} spare. "
                f"Do you want those as slow, restful days — or would you rather head "
                f"back earlier, or add somewhere else worth seeing?"
            ),
            "options": [
                f"Keep {given} days, take it slow",
                f"Head back after {need} days",
                "Suggest more places",
            ],
        })
    return out
