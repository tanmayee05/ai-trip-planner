"""
Own-vehicle enrichments — things you only care about when you're the one
driving: petrol pumps along the route, plus food and a rest-stop hotel found
NEAR THE DRIVER'S CURRENT LOCATION within a radius they choose.

These are optional. The trip plan finishes without them; the frontend shows
"want food on the way? / want a rest stop?" offers and only calls in here
when the user says yes (or asks in chat).

Route geometry arrives as [[lat, lon], ...] (the agent already flipped ORS's
[lon, lat] order). We walk it to get cumulative distance, sample points, and
turn "N hours into the drive" into "roughly here on the map".

TECH: OpenStreetMap / Overpass for petrol pumps (hard data), Gemini +
Nominatim for food & stay (curated names, then grounded to real coordinates
— same trick as attractions.py).
"""

import os
import re
import time

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from distance import straight_line_distance_km
from geocoding import geocode, reverse_geocode
from hubs import _post_overpass        # cached, mirror-failover Overpass client

load_dotenv()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# rough pump price, ₹/litre — India state averages (we have no per-pump price)
FUEL_PRICE = {"petrol": 105, "diesel": 92, "cng": 80}

# private-brand pumps run a couple of rupees dearer than the PSU trio
_PRIVATE_BRANDS = {"shell", "reliance", "jio-bp", "jiobp", "nayara", "essar"}


def _price_for(fuel_type: str, company: str | None) -> int:
    base = FUEL_PRICE.get(fuel_type, FUEL_PRICE["petrol"])
    if company and company.strip().lower() in _PRIVATE_BRANDS:
        return base + 3
    return base


def _price_hint(company: str | None = None) -> str:
    p, d = _price_for("petrol", company), _price_for("diesel", company)
    tag = f"{company} " if company and company.lower() != "any" else ""
    return f"~Rs {p}/L petrol · ~Rs {d}/L diesel ({tag}approx)"

# nightly price bands used to describe a hotel
STAY_BANDS = {"budget": 1200, "mid": 2500, "premium": 4500}

# rough single-pass toll for a 2-axle car at an Indian NH plaza (₹) — used when
# OSM carries no explicit `charge` tag, which is the common case
TOLL_CAR_PER_PLAZA = 85

# How long the per-night food+hotel section may spend in total. Each night is
# a Gemini call plus rate-limited Nominatim lookups (~20-25s), so an
# unbounded loop on a long trip would push the whole plan past the point
# where the client stops waiting for it. 150s covers ~6 nights and still
# leaves the rest of the pipeline plenty of room inside the client's window.
STAYS_BUDGET_S = 150


# ======================================================================
# route helpers
# ======================================================================
def _cumulative(geometry: list[list[float]]) -> list[float]:
    """Running km distance at each point of the [lat,lon] path."""
    out = [0.0]
    for (a_lat, a_lon), (b_lat, b_lon) in zip(geometry, geometry[1:]):
        out.append(out[-1] + straight_line_distance_km(a_lat, a_lon, b_lat, b_lon))
    return out


def sample_route(geometry: list[list[float]], n: int = 8) -> list[list[float]]:
    if not geometry:
        return []
    step = max(1, len(geometry) // n)
    pts = [geometry[i] for i in range(0, len(geometry), step)]
    if pts and pts[-1] != geometry[-1]:
        pts.append(geometry[-1])
    return pts[: n + 1]


def _ensure_geometry(geometry, src, dst, n: int = 14) -> list[list[float]]:
    """Use the real road path if we have it; otherwise draw a straight line
    between the endpoints so food/stay lookups still have something to sample."""
    if geometry:
        return geometry
    if not (src and dst):
        return []
    return [
        [src["lat"] + (dst["lat"] - src["lat"]) * i / (n - 1),
         src["lon"] + (dst["lon"] - src["lon"]) * i / (n - 1)]
        for i in range(n)
    ]


def point_at_fraction(geometry: list[list[float]], frac: float) -> list[float] | None:
    if not geometry:
        return None
    i = min(len(geometry) - 1, max(0, int(frac * (len(geometry) - 1))))
    return geometry[i]


def point_at_km(geometry: list[list[float]], cum: list[float], km: float) -> list[float] | None:
    """The [lat, lon] roughly `km` cumulative distance into the path (clamped
    to the ends)."""
    if not geometry:
        return None
    if km <= 0:
        return geometry[0]
    if km >= cum[-1]:
        return geometry[-1]
    for i, c in enumerate(cum):
        if c >= km:
            return geometry[i]
    return geometry[-1]


def _town_at(lat: float, lon: float) -> str:
    """Nearest named place — prefer a real town/city (more likely to have
    hotels & known eateries) over a village."""
    a = reverse_geocode(lat, lon) or {}
    return (a.get("city") or a.get("town") or a.get("district")
            or a.get("village") or "the highway")


def _place_coords(name: str, town: str, anchor: list[float]) -> tuple[float, float, bool]:
    """Geocode a named eatery/hotel (1-2 tries, keeps Nominatim load low).
    Falls back to `anchor` (the route point we sampled) so a real, useful
    suggestion is never dropped just because Nominatim can't pin the building."""
    for q in (f"{name}, {town}, India", f"{name}, {town}"):
        g = geocode(q)
        if g:
            return g["lat"], g["lon"], False
    return anchor[0], anchor[1], True   # approx — near the town on the route


def _area_at(lat: float, lon: float, fallback: str) -> str:
    """A short 'locality, town' label so the UI can say WHERE a place is."""
    a = reverse_geocode(lat, lon) or {}
    locality = a.get("suburb") or a.get("neighbourhood") or a.get("road") or a.get("village")
    town = a.get("city") or a.get("town") or a.get("municipality") or a.get("district")
    label = ", ".join(p for p in (locality, town) if p)
    return label or fallback


# ======================================================================
# fuel
# ======================================================================
def estimate_fuel(distance_km: float, mileage_kmpl: float, fuel_type: str,
                  company: str | None = None) -> dict:
    mileage = max(1.0, mileage_kmpl)
    price = _price_for(fuel_type, company)
    litres_ow = distance_km / mileage
    return {
        "fuel_type": fuel_type,
        "company": company or "any",
        "mileage_kmpl": round(mileage, 1),
        "price_per_litre": price,
        "one_way": {"litres": round(litres_ow, 1), "cost": round(litres_ow * price)},
        "round_trip": {"litres": round(litres_ow * 2, 1), "cost": round(litres_ow * 2 * price)},
        "note": f"~{round(litres_ow, 1)} L one way at {round(mileage, 1)} km/L, Rs {price}/L",
    }


def fuel_stops_along_route(geometry: list[list[float]], radius_km: float = 8,
                           company: str | None = None) -> list[dict]:
    """Real petrol pumps (OSM amenity=fuel) near the driving line, each with
    its town, roughly how far into the drive it sits, brand and a price hint.
    If `company` is given (and not 'any'), keep only that brand's pumps."""
    if not geometry:
        return []
    cum = _cumulative(geometry)
    samples = sample_route(geometry, 8)
    want = (company or "").strip().lower()
    want = "" if want in ("", "any") else want

    out: list[dict] = []
    seen: set[str] = set()
    for si, (lat, lon) in enumerate(samples):
        gi = min(len(geometry) - 1, int(si / max(1, len(samples) - 1) * (len(geometry) - 1)))
        km_here = round(cum[gi])
        town = _town_at(lat, lon)

        query = (
            f'[out:json][timeout:40];'
            f'nwr["amenity"="fuel"](around:{int(radius_km * 1000)},{lat},{lon});'
            f'out center 25;'
        )
        for e in _post_overpass(query):
            elat = e.get("lat") or (e.get("center") or {}).get("lat")
            elon = e.get("lon") or (e.get("center") or {}).get("lon")
            if elat is None:
                continue
            key = f"{round(elat, 3)},{round(elon, 3)}"
            if key in seen:
                continue
            seen.add(key)
            tags = e.get("tags", {})
            brand = tags.get("brand") or tags.get("operator")
            label = tags.get("name") or brand or "Petrol pump"
            if want and want not in f"{brand or ''} {label}".lower():
                continue
            out.append({
                "name": label, "brand": brand, "town": town,
                "km_from_start": km_here,
                "opening_hours": tags.get("opening_hours"),
                "price_hint": _price_hint(company),
                "lat": elat, "lon": elon,
            })
    out.sort(key=lambda p: p["km_from_start"])
    return out[:40]


# ======================================================================
# toll plazas
# ======================================================================
def _parse_charge(raw) -> int | None:
    """Pull a rupee figure out of an OSM `charge` / `toll:car` string."""
    if not raw:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    return round(float(m.group(1))) if m else None


# two NH plazas are never closer than this in practice — anything tighter is
# the same plaza mapped twice (ring road, lane nodes, entry/exit pair)
_MIN_PLAZA_SPACING_KM = 12


def _nearest_on_route(plat: float, plon: float, geometry: list[list[float]],
                      cum: list[float]) -> tuple[float, float]:
    """Shortest distance (km) from a point to the route, and the cumulative km
    along the route at that closest point. Uses point-to-SEGMENT distance so a
    booth sitting between two sparse polyline vertices isn't wrongly rejected."""
    import math

    ky = 110.574  # km per degree latitude
    best_d, best_km = 1e9, 0.0
    for i in range(len(geometry) - 1):
        alat, alon = geometry[i]
        blat, blon = geometry[i + 1]
        kx = 111.320 * math.cos(math.radians(alat))  # km per degree longitude here
        ax, ay = 0.0, 0.0
        bx, by = (blon - alon) * kx, (blat - alat) * ky
        px, py = (plon - alon) * kx, (plat - alat) * ky
        seg2 = bx * bx + by * by
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / seg2))
        cx, cy = ax + t * bx, ay + t * by
        d = math.hypot(px - cx, py - cy)
        if d < best_d:
            best_d = d
            best_km = cum[i] + t * (cum[i + 1] - cum[i])
    return best_d, best_km


def toll_plazas_along_route(geometry: list[list[float]], corridor_km: float = 3.0) -> dict:
    """Real toll booths (OSM barrier=toll_booth) on the driving line, each with
    the area it sits in and an approximate car charge. Costs come from OSM when
    tagged, else a flat per-plaza estimate — India rarely tags plaza fares.

    One Overpass query over the route's bounding box, then we keep only booths
    within `corridor_km` of the actual path (drops ones on parallel highways)."""
    if not geometry:
        return {"plazas": [], "count": 0, "car_cost_one_way": 0,
                "car_cost_round_trip": 0, "note": "No route to check for tolls."}

    cum = _cumulative(geometry)
    lats = [p[0] for p in geometry]
    lons = [p[1] for p in geometry]
    pad = 0.05  # ~5 km — the bbox only pre-filters; the corridor test is exact
    query = (
        f'[out:json][timeout:90];'
        f'nwr["barrier"="toll_booth"]'
        f'({min(lats) - pad},{min(lons) - pad},{max(lats) + pad},{max(lons) + pad});'
        f'out center 1500;'
    )
    try:
        booths = _post_overpass(query)
    except Exception:  # noqa: BLE001
        booths = []

    # 1. keep booths within the corridor, tagged with their nearest route km
    #    (point-to-segment distance — robust to a sparse downsampled polyline)
    raw: list[dict] = []
    for e in booths:
        elat = e.get("lat") or (e.get("center") or {}).get("lat")
        elon = e.get("lon") or (e.get("center") or {}).get("lon")
        if elat is None:
            continue
        d, km_here = _nearest_on_route(elat, elon, geometry, cum)
        if d > corridor_km:               # not on this route
            continue
        raw.append({"lat": elat, "lon": elon, "km": round(km_here),
                    "tags": e.get("tags", {})})

    # 2. OSM maps every LANE of a plaza as its own node — collapse booths that
    #    sit within ~2 km of each other into one physical plaza
    raw.sort(key=lambda b: b["km"])
    clusters: list[list[dict]] = []
    for b in raw:
        if clusters and straight_line_distance_km(
            b["lat"], b["lon"], clusters[-1][0]["lat"], clusters[-1][0]["lon"]
        ) <= 2.0:
            clusters[-1].append(b)
        else:
            clusters.append([b])

    out: list[dict] = []
    for group in clusters:
        head = group[0]
        if out and head["km"] - out[-1]["km_from_start"] < _MIN_PLAZA_SPACING_KM:
            continue                     # same plaza as the last one, mapped again
        tags = {}
        for b in group:                  # merge tags, first non-empty wins
            for k, v in b["tags"].items():
                tags.setdefault(k, v)
        charged = None
        for b in group:
            c = _parse_charge(b["tags"].get("charge") or b["tags"].get("toll:car")
                              or b["tags"].get("fee:car"))
            if c and c >= 20:            # ignore junk like "charge=10"
                charged = c
                break
        area = _town_at(head["lat"], head["lon"])
        name = tags.get("name") or tags.get("ref") or f"Toll plaza near {area}"
        out.append({
            "name": name,
            "area": area,
            "km_from_start": head["km"],
            "car_cost": charged or TOLL_CAR_PER_PLAZA,
            "cost_estimated": charged is None,
            "lat": head["lat"], "lon": head["lon"],
        })

    one_way = sum(p["car_cost"] for p in out)
    return {
        "plazas": out,
        "count": len(out),
        "car_cost_one_way": one_way,
        "car_cost_round_trip": one_way * 2,
        "note": (f"{len(out)} toll plaza(s) — about Rs {one_way} for a car one way "
                 f"(Rs {one_way * 2} round trip). Estimates unless the plaza is priced in OSM."),
    }


# ======================================================================
# food & stay  (Gemini -> Nominatim grounding)
# ======================================================================
_llm = ChatGoogleGenerativeAI(model=MODEL_NAME, google_api_key=os.getenv("GEMINI_API_KEY"))


class _Eatery(BaseModel):
    name: str
    kind: str = Field(description="dhaba, restaurant, food court, tiffin centre, cafe or bakery")
    why: str = Field(description="one short line — cuisine or why locals rate it")


class _EateryList(BaseModel):
    places: list[_Eatery]


class _Hotel(BaseModel):
    name: str
    band: str = Field(description="one of: budget, mid, premium")
    area: str = Field(default="", description="the locality / landmark it sits near, if known")
    why: str = Field(description="one short line — why it suits a road-trip halt")


class _HotelList(BaseModel):
    hotels: list[_Hotel]


_eatery_x = _llm.with_structured_output(_EateryList)
_hotel_x = _llm.with_structured_output(_HotelList)


def _eateries_at(anchor: list[float], town: str, radius_km: float,
                 preference: str = "any", note: str | None = None) -> list[dict]:
    """The Gemini -> Nominatim grounding step, shared by every "food near X"
    caller (near the driver's start, or near an overnight itinerary stop)."""
    ask = (
        f"Near {town}, India — within about {int(radius_km)} km — name 4-5 real, "
        f"well-known places to eat that a traveller could reach quickly. "
    )
    if preference and preference != "any":
        ask += f"The traveller wants {preference}. "
    if note:
        ask += f"Also consider: {note}. "
    try:
        res: _EateryList = _eatery_x.invoke([
            ("system", "You are an India travel expert. Only real, findable places."),
            ("human", ask),
        ])
    except Exception:
        res = _EateryList(places=[])

    places = []
    for p in res.places[:5]:
        lat, lon, approx = _place_coords(p.name.strip(), town, anchor)
        where = town if approx else _area_at(lat, lon, town)
        places.append({
            "name": p.name.strip(), "kind": p.kind.strip().lower(),
            "why": p.why.strip(), "where": where,
            "lat": lat, "lon": lon, "approx": approx,
        })
    return places


def enrich_food(geometry: list[list[float]], radius_km: float = 15,
                preference: str = "any", note: str | None = None,
                src: dict | None = None, dst: dict | None = None) -> dict:
    """Real places to eat NEAR THE START (the driver's current location), within
    roughly `radius_km`. No departure-time / meal-window logic — just "where can
    I grab food around here"."""
    geometry = _ensure_geometry(geometry, src, dst)
    anchor = (geometry[0] if geometry
              else [src["lat"], src["lon"]] if src else None)
    if not anchor:
        return {"kind": "food", "town": None, "radius_km": radius_km, "places": [],
                "note": "Couldn't work out your start point."}

    town = _town_at(anchor[0], anchor[1])
    places = _eateries_at(anchor, town, radius_km, preference, note)

    return {
        "kind": "food", "town": town, "radius_km": radius_km, "places": places,
        "note": "AI suggestions near your start — check hours before you rely on them.",
    }


def _hotels_at(anchor: list[float], town: str, ask_text: str) -> list[dict]:
    """The Gemini -> Nominatim grounding step, shared by every "hotel near X"
    caller (a rest-stop halt, or an overnight itinerary stay)."""
    try:
        res: _HotelList = _hotel_x.invoke([
            ("system", "You are an India travel expert. Only real, findable hotels."),
            ("human", ask_text),
        ])
    except Exception:
        res = _HotelList(hotels=[])

    options = []
    for h in res.hotels:
        lat, lon, approx = _place_coords(h.name.strip(), town, anchor)
        band = h.band.strip().lower()
        where = (h.area.strip() or town) if approx else _area_at(lat, lon, town)
        options.append({
            "name": h.name.strip(),
            "band": band if band in STAY_BANDS else "mid",
            "price_hint": f"~Rs {STAY_BANDS.get(band, STAY_BANDS['mid'])}/night",
            "why": h.why.strip(), "where": where,
            "lat": lat, "lon": lon, "approx": approx,
        })
    return options


def enrich_stay(geometry: list[list[float]], radius_km: float = 150,
                note: str | None = None,
                src: dict | None = None, dst: dict | None = None) -> dict:
    """Real hotels within roughly `radius_km` of the driver's current location,
    for a rest halt on a long drive. We look at the point ~`radius_km` along the
    route (clamped to the trip length) and pull hotels around that town."""
    geometry = _ensure_geometry(geometry, src, dst)
    if not geometry:
        return {"kind": "stay", "town": None, "radius_km": radius_km, "options": []}

    cum = _cumulative(geometry)
    target_km = min(float(radius_km), cum[-1])
    pt = point_at_km(geometry, cum, target_km) or geometry[0]
    town = _town_at(pt[0], pt[1])

    ask = (
        f"In or near {town}, India — within about {int(radius_km)} km of where the "
        f"driver is now — name 3 real hotels or lodges good for an overnight "
        f"road-trip halt (safe, parking, easy highway access). "
    )
    if note:
        ask += f"Preference: {note}. "
    options = _hotels_at(pt, town, ask)

    return {
        "kind": "stay", "town": town, "radius_km": radius_km,
        "km_from_start": round(target_km),
        "options": options,
        "note": "AI suggestions with rough price bands — confirm rates before booking.",
    }


# ======================================================================
# food & stay around the ITINERARY  (any travel mode — this is about the
# destination side, not the drive there)
# ======================================================================
def stays_and_food_for_itinerary(itinerary: list[dict]) -> list[dict]:
    """One food + stay suggestion set per overnight halt — the last place
    visited each day, for every day except the final one (the trip ends
    that day, so there's no further night to plan for). Works the same
    whether the traveller drove, flew, took a train or a bus — it's about
    where they'll actually be standing at the end of each day."""
    if not itinerary:
        return []

    by_day: dict[int, list[dict]] = {}
    for s in itinerary:
        by_day.setdefault(s["day"], []).append(s)
    days = sorted(by_day)

    # Each night costs a Gemini call plus several rate-limited Nominatim
    # lookups — roughly 15-20 seconds. On a 10-day trip that alone would
    # outlast the client's patience and take the whole plan down with it, so
    # the section runs against a wall-clock budget: nights we reach are
    # filled in, the rest come back marked `skipped` for the UI to offer
    # on demand. A partial answer beats a failed plan.
    deadline = time.monotonic() + STAYS_BUDGET_S

    out: list[dict] = []
    for day in days[:-1]:                    # the last day needs no further night
        anchor_stop = by_day[day][-1]
        anchor = [anchor_stop["lat"], anchor_stop["lon"]]

        if time.monotonic() > deadline:
            out.append({
                "day": day, "anchor": anchor_stop["name"], "town": None,
                "food": [], "stay": [], "skipped": True,
            })
            continue

        try:
            town = _town_at(anchor[0], anchor[1])
            food = _eateries_at(anchor, town, 10)
            hotel_ask = (
                f"In or near {town}, India — name 3 real hotels or lodges good for "
                f"an overnight halt on a sightseeing trip (safe, well-reviewed, "
                f"reasonably close to the sights). "
            )
            stay = _hotels_at(anchor, town, hotel_ask)
        except Exception as e:  # noqa: BLE001 — one bad night, not a bad trip
            print(f"stay/food lookup failed for day {day}: {type(e).__name__}: {e}")
            out.append({
                "day": day, "anchor": anchor_stop["name"], "town": None,
                "food": [], "stay": [], "skipped": True,
            })
            continue

        out.append({
            "day": day, "anchor": anchor_stop["name"], "town": town,
            "food": food, "stay": stay,
        })
    return out
