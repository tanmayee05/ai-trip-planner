# Backend — File‑by‑File Logic

_Companion to [`PROJECT_OVERVIEW.md`](./PROJECT_OVERVIEW.md). Database build details are in
[`DATABASES.md`](./DATABASES.md)._

Every file lives in `trip-planner/backend/`. Files are grouped by role.

---

## Group 1 — Chat / slot filling

### `trip_slots.py` — the "form" and the question order

**Job:** define what facts a trip needs, and decide which one to ask for next.

- `TripSlots` — a Pydantic model with optional fields: `destination`, `source`,
  `num_days`, `start_date`, `num_people`, `budget`, `travel_mode`.
  Each field has a `description=` — this text **is** the instruction the LLM sees when the
  model is handed to `.with_structured_output()`, so descriptions are short and precise.
- `REQUIRED_FIELDS` — the 4 fields we must have before planning: destination, source,
  num_days, travel_mode. `start_date`, `num_people`, `budget` are optional extras.
- `QUESTIONS` — the exact wording asked for each required field.
- `next_question(slots)` — loops `REQUIRED_FIELDS` in order, returns the question for the
  first field that is still `None`; returns `None` when all four are filled.

**Logic in one line:** the form drives the conversation — we never ask for something we
already have, and we ask in a fixed, sensible order.

---

### `slot_extraction.py` — turn a message into filled slots

**Job:** given the user's latest message (and the question we just asked), extract only
the **new** info and merge it into the existing slots.

- Builds one `llm` (`ChatGoogleGenerativeAI`) and wraps it:
  `extractor = llm.with_structured_output(TripSlots)`.
  This makes Gemini return a **validated `TripSlots` object** directly — no "respond with
  JSON" prompt, no fence stripping, no `json.loads()`.
- `EXTRACTION_PROMPT` tells the model: use the last question as context (so a bare reply
  like "guntur" to "Where are you starting from?" becomes `source="guntur"`), and **leave
  every unrelated field null** — don't guess.
- `extract_new_info(message, last_question)` — calls the extractor, then
  `result.model_dump(exclude_none=True)` so only the fields the model actually filled come
  back. This is important: a partial result must never wipe slots we already know.
- `update_slots(current_slots, message, last_question)` — merges the new info onto the
  current slots with `current_slots.model_copy(update=new_info)` and returns the updated
  form.

**Why context‑aware extraction:** short answers ("2", "own car", "next Friday") are
meaningless without knowing the question. Passing `last_question` fixes that.

---

### `chat_loop.py` — terminal version of the conversation

**Job:** a plain `while True` loop for testing the chat without HTTP.

- Starts an empty `TripSlots`, prints an opener.
- Each turn: `update_slots()` → `next_question()`. If `None`, print the slots and stop;
  otherwise print the question and remember it as `last_question`.

**Use:** fastest way to sanity‑check slot extraction changes.

---

### `main.py` — the HTTP API (FastAPI)

**Job:** the same conversation loop as `chat_loop.py`, but as a stateless `/chat`
endpoint that many clients can call.

- `init_db()` runs on import so the `sessions` table always exists.
- `ChatRequest` — `{ session_id?: str, message: str }`.
  `ChatResponse` — `{ session_id, reply, slots, ready_to_plan }`.
- `POST /chat` flow:
  1. `load_session(session_id)` — if it exists, restore `slots` + `last_question`;
     otherwise mint a new `uuid4` session with empty slots.
  2. `update_slots(slots, message, last_question)` — extract + merge.
  3. `next_question(slots)` — `None` ⇒ `reply = "Great, I have everything I need!"`,
     `ready_to_plan = True`. Otherwise the reply **is** the next question.
  4. `save_session(...)` — persist slots + the question we just asked.
  5. Return the response (`slots.model_dump()` turns the Pydantic object into a dict).
- `GET /health` — trivial liveness check.

**Why session_id + DB:** HTTP is stateless. The client holds only an opaque
`session_id`; all real state (the half‑filled form, the last question) lives in
`sessions.db`, so the conversation survives across requests and restarts.

---

### `database.py` — session persistence

**Job:** store and load one row per conversation.

- `get_connection()` — `sqlite3.connect("sessions.db", check_same_thread=False)`
  (`check_same_thread=False` because FastAPI may serve requests on different threads).
- `init_db()` — `CREATE TABLE IF NOT EXISTS sessions (session_id PK, slots_json TEXT,
  last_question TEXT)`.
- `load_session(session_id)` — returns `{"slots": TripSlots(**json), "last_question": ...}`
  or `None`.
- `save_session(...)` — an **upsert**: `INSERT ... ON CONFLICT(session_id) DO UPDATE`.
  One statement handles both "new conversation" and "existing conversation".
- Slots are stored as a JSON string via `slots.model_dump_json()` and rebuilt with
  `TripSlots(**json.loads(...))`.

**Why SQLite:** zero setup, single file, and one row per session is all we need.

---

## Group 2 — Geo primitives

### `geocoding.py` — names ⇄ coordinates (Nominatim / OpenStreetMap)

**Job:** the only place that talks to Nominatim.

- `geocode(place_name)` → `{"lat", "lon", "display_name"}` or `None`.
  `GET /search?q=...&format=json&limit=1`. Sends the required `User-Agent` header.
- `reverse_geocode(lat, lon)` → `{"village", "town", "city", "district", "state"}`.
  `GET /reverse?...&addressdetails=1`. Falls back `village → hamlet`,
  `district → state_district → county`.

**Why reverse geocoding matters:** it gives the **admin hierarchy** at a point. That
powers two decisions later — "is the source a village (so look at the district bus
stand)?" and "which nearby town names should we check for a train station?".

---

### `distance.py` — straight‑line distance (Haversine)

**Job:** `straight_line_distance_km(lat1, lon1, lat2, lon2)` — great‑circle distance using
the Haversine formula. Pure math, no network.

**Why it exists:** it's the **cheap filter**. We use it to sort/shortlist dozens of
candidate hubs for free, and only spend a real routing call (ORS) on the ones that win.
It is explicitly **not** road distance.

---

### `routing.py` — real road distance/time (OpenRouteService)

**Job:** `get_driving_route(lat1, lon1, lat2, lon2)` → `{"distance_km", "duration_hr"}`
or `None`.

- `GET .../v2/directions/driving-car` with the ORS API key in the `Authorization` header.
- **Gotcha handled here:** ORS wants coordinates as `lon,lat` (reverse of everywhere else
  in the codebase). The docstring calls this out.
- Reads `summary.distance` (metres → km) and `summary.duration` (seconds → hours).
- Returns `None` and prints the status on any non‑200 (commonly `404 "no routable point"`
  when a hub's map pin sits on a runway or a field, not a road).

**Why ORS:** the last‑mile leg (arrival station/airport → the actual destination town)
needs a realistic drive estimate, and ORS is built on the OSM road graph.

---

## Group 3 — Hub discovery

### `hubs.py` — find nearby stations, bus stands, airports

**Job:** given a point, return real transport hubs around it. No hardcoded place lists.

**Overpass access (shared):**
- `OVERPASS_MIRRORS` — three public servers, tried in order.
- `_post_overpass(query)` —
  1. Check the **on‑disk cache** (`.overpass_cache/<sha1>.json`). Hit ⇒ return instantly.
  2. Miss ⇒ try each mirror, retry once on `429/504`, `(10s connect, 45s read)` timeout.
  3. First 200 response is saved to the cache and returned.
  4. All mirrors fail ⇒ print why, return `[]`.
- `_query_overpass(lat, lon, radius_km, tags)` — builds
  `(nwr[tagA](around); nwr[tagB](around); ); out center;`.
  - `nwr` = node **+ way + relation**. Airports and big bus stands are drawn as *areas*
    (ways/relations), not points — querying only `node` misses almost all of them.
  - `out center;` makes Overpass return a `center` point for those areas so we can measure
    distance to them.
- `_element_coords(e)` — pulls lat/lon from a node, or `center` from a way/relation.

**Bus stands & airports:**
- `SEARCH_CONFIG` — bus: `amenity=bus_station` **or** `public_transport=station`+`bus=yes`,
  radius 60 km. flight: `aeroway=aerodrome`, radius 300 km.
- `list_nearby_bus_or_flight(lat, lon, type)` — runs the query, drops unnamed noise
  (aprons/bays), de‑dupes by name, sorts closest‑first. For flights it also reads the
  `iata` tag and sorts **IATA‑coded airports first** (real airports before airstrips /
  heliports / naval bases).

**Place names for the train search:**
- `get_nearby_towns(lat, lon, 70km)` — Overpass `place~"^(city|town)$"`. This is how we
  learn the *neighbouring* town names (Kavali, Gudur, …) that reverse geocoding never
  tells us.
- `get_regional_cities(lat, lon, 550km)` — `place="city"` only, wide radius. Feeds the
  "major junction" search (Vijayawada, Secunderabad, …) — again, discovered, not typed.
- `get_nearby_place_candidates(lat, lon)` — combines reverse‑geocode (village + district)
  with `get_nearby_towns()` into the list of names to check against `trains.db`.

**Train stations:**
- `_clean_place("Atmakuru ( N )")` → `"Atmakuru"` (strip bracketed suffixes).
- `_station_search_name("VIJAYAWADA JN - BZA")` → `"Vijayawada, India"` (strip ` JN`/` H`
  so Nominatim can geocode it).
- `_place_is_whole_word(place, station_name)` — the DB search uses SQL `LIKE '%place%'`,
  which made `"Allur"` match `"TIRUVALLUR - TRL"`. This re‑checks with a `\bword\b`
  boundary so only genuine matches survive; names < 4 chars are rejected outright.
- `_collect_stations(lat, lon, names, min_trains)` — for each candidate name:
  - expand it with `place_name_variants()` (see `train_lookup.py`) so **Mysuru** also
    tries **Mysore**;
  - `find_station_by_name()` for every variant, keep matches that pass the whole‑word test;
  - drop stations with fewer than `min_trains` trains;
  - geocode the station (cached, 1 req/s) and attach straight‑line distance;
  - flag `major_hub = train_count >= MAJOR_HUB_MIN_TRAINS` (100).
- `list_nearby_train_stations(lat, lon, search_names)` — merges **near stations** with
  **regional major junctions**, sorts closest‑first, keeps the nearest `max_results`, then
  re‑adds any major junction that got cut. (Great for "which hubs exist"; the connectivity
  engine applies its own tighter distance caps on top.)

**Caches:** `_geo_cache` (in‑memory geocode results) + `.overpass_cache/` (on disk).

---

## Group 4 — Timetable lookups

### `train_lookup.py` — query `trains.db`

**Job:** all SQL against the train database.

- `CITY_RENAMES` + `place_name_variants(name)` — Indian Railways still labels some
  stations by their old name (`MYSORE`, `BANGALORE`, `MANGALORE`, `CALICUT`, `GULBARGA`,
  …) while OSM uses the new one (`Mysuru`, `Bengaluru`, …). `place_name_variants("Mysuru")`
  → `["Mysuru", "Mysore"]`, matched **both ways**. Without this, Coorg's real railhead
  (Mysore Jn) was invisible.
- `find_station_by_name(place_name)` — `SELECT DISTINCT station_name FROM train_stops
  WHERE station_name LIKE '%NAME%'`. Returns every station whose name contains the term.
- `count_trains_at_station(station_name)` — `COUNT(DISTINCT train_number)` at that exact
  station. This is the "does this station actually matter" signal used for `major_hub`.
- `date_to_day_column("2026-09-15")` → `"runs_tue"` — maps a real date to the DB's
  running‑day column.
- `find_connecting_trains(source_station, dest_station, travel_date)` — the key query.
  Self‑joins `train_stops` to itself on `train_number`:
  - one row for the **source** stop, one for the **destination** stop;
  - `s1.stop_order < s2.stop_order` (the train must pass source *before* destination —
    direction matters);
  - `trains.<day_column> = 1` (it actually runs on that weekday).
  Returns train number, name, class, departure and arrival times.

**Example of it working correctly:** `NELLORE → MYSORE JN` returns 0 rows because the only
Gudur→Mysore train that day (Bagmati Express 12577) has stop order `… ONGOLE → GUDUR JN →
PERAMBUR …` — it never stops at Nellore.

---

### `flight_lookup.py` — query `flights.db` (with lazy fetch)

**Job:** "what does airport X fly to on date D?", fetching from the API only if we haven't
already.

- `_is_cached(iata, date)` — is there any row for this `(origin_iata, checked_date)`?
- `get_destinations_from(iata, name, lat, lon, travel_date)`:
  1. `init_db()` (ensure tables exist);
  2. if not cached, `store_departures(...)` (calls AeroDataBox, writes rows) — see
     `DATABASES.md`;
  3. `SELECT DISTINCT destination_iata, destination_name FROM flights WHERE origin_iata=?
     AND checked_date=?`.
  Returns `[{"iata", "name"}, ...]`.

**Why lazy + cached:** AeroDataBox is a paid RapidAPI service. Each `(airport, date)` is
fetched at most once, ever.

---

## Group 5 — The connectivity engine

### `connectivity.py` — does train / bus / flight actually connect source → destination?

**Job:** the brain that ties hubs + timetables + routing together.

**Tunables (top of file):**
`MAX_SOURCE_STATION_KM = 150`, `MAX_DEST_RAILHEAD_KM = 250`,
`MAX_DEST_AIRPORT_KM = 200`, `MAX_LAST_MILE_KM = 175`,
`ROAD_DETOUR_FACTOR = 1.3`, `ROAD_AVG_SPEED_KMH = 40`,
`AUTO_FARE_PER_KM = 15`, `LOCAL_BUS_FARE_PER_KM = 2`.

**Helpers:**
- `_clean_district("Sri Potti Sriramulu Nellore")` → `"Nellore"` (strip honorific/admin
  prefixes so the name geocodes to the real city).
- `_fare_options(km)` — rough local‑bus / auto fare estimates.
- `estimate_last_mile(hub_lat, hub_lon, dest_lat, dest_lon)`:
  - try ORS (`get_driving_route`) → real km/hr, `"estimated": False`;
  - if ORS fails (the `404 "no routable point"` case), fall back to
    `haversine × 1.3` km and `÷ 40 km/h`, `"estimated": True`. Never returns `{}`.
- `find_destination_hubs(dest_lat, dest_lon)` — nearest stations **and** nearest airports
  around the destination, kept as **full lists** (`train_stations`, `flight_airports`), not
  just the single closest. (The closest railhead to Coorg is a tiny ghat halt with no
  useful trains — the check needs freedom to arrive at Mysore instead.)

**`check_train_connectivity(...)`:**
1. `source_stations` = `list_nearby_train_stations(source)` filtered to
   `distance_km ≤ 150`, sorted nearest‑first.
2. `dest_stations` = `dest_hubs["train_stations"]` filtered to `distance_km ≤ 250`,
   nearest‑first. Empty ⇒ return a note "no railway station near the destination".
3. For each source station (nearest first), try each destination railhead (nearest
   first): `find_connecting_trains(...)`. Keep the **first** pair that has a same‑day
   direct train **and** `estimate_last_mile(...) ≤ 175 km`. `break` to the next source
   station.
4. `recommended` = the nearest working boarding station.
5. If nothing works, attach a note listing the railheads that were tried.
6. Result also carries `dest_hubs_considered` for transparency in the output.

**`check_bus_connectivity(...)`:** we have **no** reliable bus schedule data, so we never
claim a working option.
1. `reverse_geocode(source)` → is it a village/hamlet with no city/town? (`is_village`).
2. `list_nearby_bus_or_flight(source, "bus")` for the local stands.
3. If it's a village, also geocode the **district HQ** and list the bus stands there.
4. `_looks_like_real_stand()` prefers an APSRTC/RTC "bus station" over a roadside "bus
   stop" pole.
5. Return `recommended` = that main stand + a `note` telling the user it's a village,
   which district stand serves it, and to **check RedBus (redbus.in) / AbhiBus
   (abhibus.com)** for live availability to the destination.

**`check_flight_connectivity(...)`:** mirrors the train logic.
1. `nearby_airports` = source airports with an `iata` code, nearest‑first.
2. `dest_airports` = `dest_hubs["flight_airports"]` filtered to `distance_km ≤ 200`,
   nearest‑first.
3. For each source airport × destination airport: `get_destinations_from(...)`; keep the
   first pair with a same‑day flight **and** last‑mile `≤ 175 km`.
4. `recommended` = nearest working source airport; note lists airports checked if nothing
   connects.

**`check_all_modes(...)`:** calls `find_destination_hubs()` **once** (halves the Overpass
load) and runs all three checks. The `__main__` block demos Rebala → Madikeri on
2026‑09‑15 and prints, per mode: the working options, the destination‑side hubs
considered, and the near‑source hubs that were checked but don't connect.

---

## Group 6 — Scratch / test scripts (not part of the pipeline)

| File | Purpose |
|------|---------|
| `test_gemini.py` | One‑liner: confirm the Gemini API key + model work |
| `test_flight_response.py` | Print a raw AeroDataBox response for one airport/date (used while shaping `build_flight_db.py`) |
| `view_db.py` | Print a few sample rows from `trains.db` |

---

## Quick reference — who calls whom

```
main.py ─┬─ database.py            (sessions.db)
         ├─ slot_extraction.py ── LangChain ── Gemini
         └─ trip_slots.py

connectivity.py ─┬─ hubs.py ─┬─ geocoding.py        (Nominatim)
                 │           ├─ distance.py          (Haversine)
                 │           └─ train_lookup.py      (trains.db)
                 ├─ train_lookup.py                  (trains.db)
                 ├─ flight_lookup.py ── build_flight_db.py  (AeroDataBox → flights.db)
                 ├─ routing.py                       (ORS)
                 └─ geocoding.py                     (Nominatim)
```
