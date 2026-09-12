# Backend — File‑by‑File Logic

_Last updated: 2026-09-12_

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

**Job:** every endpoint the frontend talks to. `init_db()` runs on import so the
tables always exist, and CORS is opened to the Vite dev and preview ports.

| Endpoint | What it does |
|----------|--------------|
| `POST /auth/signup` · `POST /auth/login` · `GET /auth/me` | Accounts. Passwords are bcrypt-hashed, the reply carries a JWT |
| `POST /attractions` | Places for a destination, via `attractions.get_attractions()` — cached per destination, so a repeat is instant |
| `POST /plan` | Geocodes the endpoints (a bad name is a fast `422`), makes the transport target the **centroid of the picked stops**, then starts the agent on a background thread and returns `202` with a job id |
| `GET /plan/{job_id}` | Poll. Carries `state`, the finished `result`, **and while running a `partial` result plus `stages` / `stages_done`** — which is what lets the UI paint sections as they land |
| `POST /plan/feasibility` | Do these places fit these days? Assesses without planning anything, so the UI can put the choice — more days, or fewer places — to the traveller *first* |
| `POST /plan/costs` | Re-runs `agent.estimate_costs` against a plan already on screen. Party size changes the per-head arithmetic and nothing else, so it would be absurd to re-plan the trip for it |
| `POST /plan/enrich` | On-demand extras for own-vehicle trips: fuel estimate, fuel stops, food, a rest-stop hotel |
| `POST /chat` | One turn of the conversation — see below |
| `GET /chat/{session_id}` | Rehydrate a transcript, using the same readiness checklist as a live turn |
| `GET /trips` · `GET /trips/{trip_id}` · `DELETE /trips/{trip_id}` | Saved trips, for the History drawer |
| `GET /health` | Liveness |

**The plan job table.** `_PLAN_JOBS` is an in-memory dict; a worker thread writes
`partial` / `stages_done` into it as the agent streams, and the poll endpoint
reads them. Fine for a single-process dev server — a restart loses an in-flight
job and the frontend simply re-submits. A real deployment would want a queue.

**`POST /chat` is more than slot filling.** In order, a turn:

1. **Resumes a pending stay negotiation** if one is open for this session. The
   message is the *answer* to that question, so it must not go through slot
   extraction — "just day 2" would otherwise be read as a travel date.
2. **Handles a place edit** ("also include Hampi", "drop Varkala") — resolves the
   name against a known list, re-plans just the days via
   `agent.plan_itinerary_only()`, and returns an `itinerary_patch`. This runs
   *before* extraction too: "include Alleppey" was being read as a new
   destination, which then broke the lookup for that very place.
3. **Folds in what the form already knows** (`known`), so the assistant never
   re-asks for something visible on screen.
4. **Extracts new slots** — guarded, because a transient LLM/network failure must
   not take the whole conversation down with a `500`.
5. **Answers a question** if the traveller asked one, then folds the next slot
   question in as a follow-up.
6. **Offers a stay change** if the message named a price band and a plan exists —
   suggest, then *ask* which nights, via `stay_revision.propose()`.

The response therefore carries not just `reply` / `slots` / `ready_to_plan` but
optionally a `pending_action` (a question awaiting an answer), a `stays_patch`,
or an `itinerary_patch` for the UI to apply to the plan on screen.

**Why session_id + DB:** HTTP is stateless. The client holds only an opaque
`session_id`; all real state (the half-filled form, the last question, the
transcript) lives in `sessions.db`, so a conversation survives across requests
and restarts.

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

## Group 6 — The planning brain

### `agent.py` — the LangGraph trip-planning agent

The thing `/plan` actually runs. A `StateGraph` over one `TripState`, shaped that
way because planning has branches that don't depend on each other, a step that
loops, and steps that can fail independently.

| Function | Role |
|----------|------|
| `resolve()` | Marks the run started and, crucially, computes **feasibility before any planning** — so the itinerary prompt can be told the truth ("these want 5 days, you have 3"). When the places don't fit, trims the stop list to what does and records the rest in `deferred` |
| `cluster_itinerary()` | Asks Gemini for a day-by-day plan, then **validates** it: every place used exactly once, day numbers contiguous, no interior blank days, no day over its hour budget. A failure comes back as `itinerary_error` and the conditional edge loops round with it folded into the re-prompt |
| `_validate()` / `_practicality_error()` | The two halves of that check — shape, then practicality. The second is where a 13-hour day gets rejected. One-stop days are exempt, because a single 6-hour place cannot be split and the error would ask for the impossible |
| `_fill_trip_days()` | Guarantees every day the traveller booked appears. Ask for 3 days with two nearby places and the planner rightly uses 2 — day 3 then shows as a free/departure day instead of vanishing and making the itinerary look truncated |
| `fallback_itinerary()` | Deterministic packing (via `feasibility.pack_days`) when Gemini cannot produce a valid plan in three tries. Respects the same hour budgets, so even the fallback is doable |
| `_is_fatal_llm_error()` | Quota, rate-limit and bad-key errors skip the retries and go straight to the fallback. Retrying changes nothing except the wait |
| `plan_stays()` | Food and a hotel for the trip, via `enrichments` |
| `find_specialities()` | What the destination is famous for, via `speciality` |
| `plan_transport()` | `check_all_modes()` for public transport, or a drive plan for own vehicle |
| `assess_drive()` | Own-vehicle only: real road geometry, toll plazas, and the optional "want food / a rest stop?" offers |
| `plan_return_leg()` | The trip home — from the **last place visited**, not the destination. `defer=True` on this node makes it a barrier that fires once instead of once per incoming branch |
| `estimate_costs()` | Fuel, tolls, food and stay arithmetic. Pure, so `/plan/costs` can re-run it for a party-size change without re-planning the trip |
| `assemble()` | Builds the API `result`, then `narrative` last so it can draw on transport, stays and itinerary together |
| `partial_result()` | The plan so far, in the finished shape — what streaming publishes. Pure: it copies rather than mutating live state |
| `run_trip_plan()` | Runs the graph. Given an `on_progress` callback it uses `stream_mode="updates"` and accumulates state itself, so each node's output is published the moment that node returns |
| `plan_itinerary_only()` | Re-plans just the days for a changed stop list (a chat edit). Reuses the same nodes, so the rules cannot diverge from the full path |
| `plan_stages()` / `stages_done()` | The stage list the progress UI draws, and which are genuinely finished — read from state, not the node log, because a failed retry logs a line without having produced anything |

### `feasibility.py` — is this trip actually doable?

All deterministic, no LLM. It runs on every plan and has to be *explainable*
("Munnar needs about 4 hours, and it is 3 hours from Kochi") rather than merely
plausible.

| Function | Role |
|----------|------|
| `VISIT_HOURS` | How long each category really takes (wildlife 4h, hill station 4h, temple 1h...). **Every "needs N days" claim traces back to this dict**, so it is the one place to tune if your pace differs |
| `travel_hours()` | Crow-flies x 1.3 road detour / 40 km/h — a realistic Indian state-highway average |
| `day_budget()` | 10.5h on a normal day, 5.5h on arrival, 6.5h on the last |
| `day_load()` | What a day really costs: the visits, the driving between them, **and** the morning transfer from wherever the night was spent. Omitting that last term made the packing far too optimistic |
| `cluster_stops()` | Single-link grouping at 35 km — the "areas" you would naturally cover in one go |
| `order_by_cluster()` + `_improve_cluster_order()` | Walk the areas nearest-first, then 2-opt the sequence to take out the crossings. A purely greedy order ran down the Kerala coast, back inland for the hill stations, then south again: ~200 km and a whole extra day |
| `pack_days()` | Fill a day until it is full, then start the next. One area per day, unless real touring time would still remain after the drive |
| `assess()` | The verdict — `ok` / `too_short` / `too_long` — with the numbers and a sentence to put to the traveller |
| `split_by_what_fits()` | `(will_fit, wont_fit)` for the time available. The last-resort guarantee that a plan is never impossible |

### `itinerary.py` — route primitives

`order_stops()` (nearest-neighbour from a point), `region_center()` (the centroid
handed to `check_all_modes` as the transport target, so the arrival hub lands in
the middle of the trip region rather than at a vague state point), and the legacy
`split_into_days()`. That last one is the even split — `day = i * days // n + 1`
— which `feasibility.pack_days` replaced; it is what used to put a tiger reserve
and a hill station 120 km apart in the same afternoon.

### `narrative.py` — the plan in plain English

Turns the structured result into a running schedule: set off at 07:00, check in
at 11:12, first stop and how long to allow, the drive on, lunch, dinner, the
night. Deterministic, and built from the same hour figures the days were packed
with, so the prose cannot describe a different trip from the one planned. It
doubles as a feasibility check a human can read — a day ending "20:38 Auroville,
23:08 start back" is obviously wrong in a way a table of hours never is.

---

## Group 7 — Places, extras and conversation

### `attractions.py` — what is worth seeing

Gemini names the places; **Nominatim grounds them to real coordinates**, and that
grounding is then checked. A bare `<name>, India` query can match anywhere in the
country: "Skandashramam", a cave 1 km from Arunachaleswarar Temple, was being
pinned in Chennai 140 km away — and the whole itinerary was then planned around
that phantom distance. A broad-query match is now rejected unless it lands within
`SAME_TOWN_MAX_KM` of the town the model named. Results are scoped `in` /
`nearby` and cached per destination.

### `speciality.py` — what the place is famous for

Rose milk in Rajahmundry, Kanchipuram silk, Kerala's houseboats. **Tavily first**
for current web snippets, **then** Gemini to structure them — the order matters,
because a model asked cold will confidently name a restaurant that shut two years
ago. Each item is tagged `food` / `sweet` / `drink` / `craft` / `experience`,
with the well-known shop where there is one and a rough price. It returns
`grounded` so the UI can claim "Web-checked" only when search actually ran, and
returns nothing rather than inventing a speciality for a town that has none.

### `enrichments.py` — fuel, food, stays, tolls

| Function | Role |
|----------|------|
| `estimate_fuel()` / `fuel_stops_along_route()` | Litres and cost for a given mileage and fuel type; real OSM petrol pumps sampled along the driving line, optionally filtered to one brand |
| `toll_plazas_along_route()` | Toll booths on the path, with a car estimate folded into the budget |
| `enrich_food()` / `enrich_stay()` | On-demand "food on the way" and "a rest-stop hotel" for a long drive |
| `stays_and_food_for_itinerary()` | **Food for every day of the trip, a hotel for every night of it.** Deliberately not keyed off "days that have stops": an arrival day with no sightseeing is still a night in a hotel, and you eat on the last day too. A travel day anchors on where the *next* day starts, which is where you would actually want to sleep |
| `stays_for_days()` | Re-pick hotels for specific days in a specific price band — used by the chat negotiation |
| `STAYS_BUDGET_S` | A wall-clock budget for the whole section. Each night costs a Gemini call plus rate-limited geocoding (~20s), so an unbounded loop on a long trip would outlast the client and take the whole plan down with it. Nights it cannot reach come back marked `skipped` for the UI to offer on demand |

### `chat_reply.py` — answering, not just interrogating

`looks_like_question()` decides whether a message is a request for information or
an answer to the pending slot question. `answer_question()` answers it — grounded
in Tavily results when a key is present — and the caller then folds the next slot
question in as a follow-up, so the assistant does not talk over the traveller
with form fields. `wants_change()` separates "best hotels in Vizag?" (a question
asked about a Kerala trip, which must not overwrite the destination) from
"actually make it Vizag" (which must).

### `stay_prefs.py` — reading a stay preference

`detect_stay_band()` requires **both** a band word and a stay word, so "we are on
a tight budget" and "premium trains" are not read as hotel instructions.
`parse_scope()` turns the reply into `"all"`, `"none"`, or a **list** of nights
("days 1 and 2"). Matching is whole-word via `_has_phrase()`: a plain substring
test reads "looks fine", "book it" and "not sure" as consent — which would have
silently rewritten every hotel in the plan. Hedging returns `None`, so the caller
asks again rather than guessing.

### `stay_revision.py` — human-in-the-loop, properly

"Recommend premium stays" is not a question with one answer; it is the start of a
negotiation: suggest, **stop and ask**, then change only what was agreed.
LangGraph's `interrupt()` models exactly that — it suspends mid-node, the state
persists under a thread id (the chat session), and a later `Command(resume=...)`
picks up where it stopped, which is what lets the pause span two separate HTTP
requests without a hand-rolled state machine. The merge preserves each night's
food picks, and every night it was not asked to touch.

### `place_edits.py` — "also include Hampi" / "drop Varkala"

The hard part is the place *name*, not the verb. A candidate phrase is pulled out
with a regex and then **matched against a list we already know** — the trip's own
stops for a removal, the destination's attractions for an addition. Matching
against a known set is what makes it reliable, and it means an addition arrives
with real coordinates, a category and a blurb instead of a bare name. No match
asks for clarification rather than removing the wrong place.

### `own_vehicle.py` / `budget.py`

Earlier standalone helpers for drive planning and cost breakdown. The live paths
are `agent._drive_plan` / `agent.assess_drive` and `agent.estimate_costs`; these
remain as readable references for the same arithmetic.

### `auth.py` — accounts

`hash_password` / `verify_password` (bcrypt), `create_access_token` (JWT), and the
FastAPI dependencies `get_current_user_id` (required) and `get_optional_user_id`
— the latter so planning still works while logged out, it just is not saved.

---

## Group 8 — Scratch / test scripts (not part of the pipeline)

| File | Purpose |
|------|---------|
| `test_gemini.py` | One‑liner: confirm the Gemini API key + model work |
| `test_flight_response.py` | Print a raw AeroDataBox response for one airport/date (used while shaping `build_flight_db.py`) |
| `view_db.py` | Print a few sample rows from `trains.db` |

---

## Quick reference — who calls whom

```
main.py ─┬─ auth.py / database.py           (sessions.db: users, sessions, trips)
         ├─ attractions.py                  (Gemini + Nominatim grounding)
         ├─ agent.py                        (the planning graph — below)
         ├─ feasibility.py                  (/plan/feasibility)
         ├─ enrichments.py                  (/plan/enrich)
         ├─ slot_extraction.py ── LangChain ── Gemini
         ├─ chat_reply.py ── Tavily + Gemini
         ├─ place_edits.py                  (chat: add / remove a place)
         └─ stay_prefs.py + stay_revision.py  (chat: change the stays)

agent.py ─┬─ feasibility.py ── itinerary.py ── distance.py
          ├─ connectivity.py                (see below)
          ├─ enrichments.py ── hubs.py / geocoding.py / Gemini
          ├─ speciality.py ── Tavily + Gemini
          ├─ routing.py                     (ORS road geometry)
          └─ narrative.py ── feasibility.py (the same hour figures)

connectivity.py ─┬─ hubs.py ─┬─ geocoding.py        (Nominatim)
                 │           ├─ distance.py          (Haversine)
                 │           └─ train_lookup.py      (trains.db)
                 ├─ train_lookup.py                  (trains.db)
                 ├─ flight_lookup.py ── build_flight_db.py  (AeroDataBox → flights.db)
                 ├─ routing.py                       (ORS)
                 └─ geocoding.py                     (Nominatim)
```

Two properties hold throughout that call graph:

- **Each transport mode inside `check_all_modes()` is guarded independently.** A
  flight-API outage costs you the Flight tab, not the train and bus results.
- **Every node in `agent.py` degrades on its own.** One unguarded exception used
  to discard a finished itinerary, map and budget along with the thing that
  actually failed.
