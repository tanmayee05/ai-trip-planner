# Databases — How Each One Is Built and Queried

_Last updated: 2026-09-12_

_Companion to [`PROJECT_OVERVIEW.md`](./PROJECT_OVERVIEW.md) and
[`BACKEND_FILES.md`](./BACKEND_FILES.md)._

The project has **three SQLite databases**, all single files in `trip-planner/backend/`:

| File | Holds | Built by | Queried by | Size / rows |
|------|-------|----------|------------|-------------|
| `trains.db` | Indian Railways timetable | `build_train_db.py` | `train_lookup.py`, `hubs.py` | ~15 MB · 8,490 trains · 170,340 stops |
| `flights.db` | Scheduled flight departures per airport per date | `build_flight_db.py` | `flight_lookup.py` | small · grows per `(airport, date)` fetched |
| `sessions.db` | Conversations, user accounts and saved trips (3 tables) | `database.py` (`init_db`) | `database.py` | small · 1 row per session / user / saved trip |

Alongside them sits a family of on-disk JSON caches (`.geo_cache/`,
`.overpass_cache/`, `.route_cache/`, `.attractions_cache/`, `.speciality_cache/`)
— section 4 — which are what make a repeat region fast rather than another few
minutes of rate-limited lookups.

**Why SQLite everywhere:** it is serverless (just a file), built into Python's standard
library (`import sqlite3`, nothing to install), and with an index it answers lookups over
hundreds of thousands of rows instantly. All three datasets are read‑heavy reference data
— a perfect fit.

---

## 1. `trains.db` — the train timetable

### 1a. Source data

Three JSON files in `backend/data/`, one per train class:

| File | Class | Records |
|------|-------|---------|
| `SF-TRAINS.json` | Superfast | 1,412 |
| `EXP-TRAINS.json` | Express | (bulk of the 8,490) |
| `PASS-TRAINS.json` | Passenger | remainder |

Each record looks like:

```json
{
  "trainNumber": "01209",
  "trainName": "NGP PUNE SF SPL",
  "route": "NAGPUR to PUNE JN",
  "runningDays": { "SUN": false, "MON": false, "TUE": false,
                   "WED": false, "THU": false, "FRI": false, "SAT": true },
  "trainRoute": [
    { "sno": "1", "stationName": "NAGPUR - NGP",  "arrives": "Source",
      "departs": "19:40", "distance": "0 kms",   "day": "1" },
    { "sno": "2", "stationName": "WARDHA JN - WR", "arrives": "20:50",
      "departs": "20:52", "distance": "79 kms",  "day": "1" }
  ]
}
```

Note the shape: **one train** has **many stops**. This is a classic **one‑to‑many**
relationship.

### 1b. Schema — two tables, not one

`build_train_db.py` creates:

```sql
CREATE TABLE trains (
    train_number TEXT PRIMARY KEY,
    train_name   TEXT,
    train_class  TEXT,                          -- "SF" | "EXP" | "PASS"
    runs_sun INTEGER, runs_mon INTEGER, runs_tue INTEGER,
    runs_wed INTEGER, runs_thu INTEGER, runs_fri INTEGER, runs_sat INTEGER
);

CREATE TABLE train_stops (
    train_number TEXT,
    stop_order   INTEGER,        -- "sno" — position along the route
    station_name TEXT,           -- "NELLORE - NLR"
    arrival_time TEXT,
    departure_time TEXT,
    distance_km  INTEGER,        -- parsed from "79 kms"
    day_number   INTEGER,        -- 1 = departure day, 2 = next day, ...
    FOREIGN KEY (train_number) REFERENCES trains(train_number)
);
```

**Why split into two tables?** If we kept one flat table, the train's name and its 7
running‑day flags would be copied onto **every** stop row (~170k times). That wastes space
and, worse, makes updates error‑prone (change a running day → must fix every row). Two
tables linked by `train_number` store each fact exactly once.

### 1c. Build process (`build_train_db.py`)

1. `DROP TABLE IF EXISTS` both tables (a clean rebuild every run).
2. `CREATE TABLE` both.
3. For each of the 3 JSON files:
   - `train_class = filename.split("-")[0]` → `"SF"` / `"EXP"` / `"PASS"`.
   - For each train: `INSERT OR IGNORE INTO trains (...)`, converting the boolean
     `runningDays` into `0/1` integers.
   - For each stop in `trainRoute`: `INSERT INTO train_stops (...)`, with
     `parse_distance("79 kms") -> 79`.
4. **Create indexes** — the important performance step:
   ```sql
   CREATE INDEX idx_stop_station ON train_stops(station_name);
   CREATE INDEX idx_stop_train   ON train_stops(train_number);
   ```
   Without `idx_stop_station`, every "which trains stop at X" scans all 170k rows. With
   it, the DB jumps straight to the matching rows — like a book's index vs. reading every
   page.
5. `commit()`, `close()`, print the totals.

Run it once:

```bash
python build_train_db.py
# -> Loaded 8490 trains, 170340 stops into trains.db
```

### 1d. How it's queried (`train_lookup.py`)

- **Find a station by name** — substring match:
  ```sql
  SELECT DISTINCT station_name FROM train_stops WHERE station_name LIKE '%NELLORE%';
  ```
- **Count trains at a station** — the "importance" signal:
  ```sql
  SELECT COUNT(DISTINCT train_number) FROM train_stops WHERE station_name = 'NELLORE - NLR';
  ```
- **Find a same‑day direct train A → B** — a self‑join on `train_stops`:
  ```sql
  SELECT DISTINCT t.train_number, t.train_name, t.train_class,
         s1.departure_time, s2.arrival_time
  FROM train_stops s1
  JOIN train_stops s2 ON s1.train_number = s2.train_number
  JOIN trains       t ON t.train_number  = s1.train_number
  WHERE s1.station_name = :source
    AND s2.station_name = :destination
    AND s1.stop_order  < s2.stop_order      -- source is passed BEFORE destination
    AND t.runs_tue     = 1;                 -- column chosen from the travel date
  ```
  The `stop_order` check enforces **direction**: a train passing through both stations only
  helps if it reaches the source first. The day column comes from
  `date_to_day_column("2026-09-15") -> "runs_tue"`.

---

## 2. `flights.db` — scheduled flight departures

### 2a. Source data

**AeroDataBox**, accessed through **RapidAPI** (needs `RAPIDAPI_KEY` in `.env`).
Endpoint: `GET /flights/airports/iata/{IATA}/{fromLocal}/{toLocal}` with
`direction=Departure`.

### 2b. Schema (`build_flight_db.py` → `init_db()`)

```sql
CREATE TABLE airports (
    iata TEXT PRIMARY KEY, name TEXT, lat REAL, lon REAL
);

CREATE TABLE flights (
    flight_number TEXT,
    airline TEXT,
    origin_iata TEXT,
    destination_iata TEXT,
    destination_name TEXT,
    scheduled_departure_local TEXT,
    scheduled_arrival_local TEXT,
    checked_date TEXT,                                  -- the date we asked about
    PRIMARY KEY (flight_number, scheduled_departure_local)
);
```

```sql
-- created lazily by flight_lookup.py
CREATE TABLE IF NOT EXISTS flight_checks (
    origin_iata  TEXT,
    checked_date TEXT,
    PRIMARY KEY (origin_iata, checked_date)
);
```

The `checked_date` column is what makes per-date caching possible: a row is "airport O
flies to D, on date `checked_date`".

**Why `flight_checks` exists separately.** An airport with genuinely no departures
that day stores *zero* rows in `flights`, which is indistinguishable from "never
asked" — so without this table it would be re-fetched on every single plan. A row
in `flight_checks` means "we asked, and this is the answer, empty or not".

**And why it is only written on success.** It used to be written regardless. When
the monthly AeroDataBox quota ran out, every `429` was recorded as "checked, no
flights" — permanently, surviving the quota reset. `store_departures()` now
returns whether the call actually succeeded and the mark is skipped otherwise, so
flights start working again on their own. The distinction runs all the way to the
UI: the Flight tab says *"couldn't check flight schedules right now"* rather than
*"no flights"*.

### 2c. Build / fetch process

`build_flight_db.py` is both a **one‑time bulk loader** and the **fetch helper** the app
calls on demand.

- `fetch_departures(iata, from_local, to_local)` —
  - `GET` the endpoint with the RapidAPI headers, `timeout=30`;
  - non‑200 (e.g. `204` = no schedule on the free tier) ⇒ print + return `[]` (never
    crashes the caller);
  - for each departure with a real arrival IATA, collect
    `{flight_number, airline, destination_iata, destination_name, sched dep/arr}`.
- `store_departures(origin_iata, name, lat, lon, date)` —
  - `INSERT OR REPLACE INTO airports` (remember the origin's coordinates);
  - split the day into two windows (`00:00–12:00`, `12:00–23:59`) so a busy hub's list
    isn't truncated by the API's page size;
  - `fetch_departures()` each window, `INSERT OR REPLACE INTO flights` with
    `checked_date = date`, `time.sleep(2)` between calls to stay under rate limits;
  - print `Stored N departures for {iata} on {date}`.
- `__main__` bulk‑loads a starter list (currently just `TIR`) for a representative date.

### 2d. How it's queried (`flight_lookup.py`) — lazy + cached

```python
get_destinations_from(iata, name, lat, lon, travel_date) -> (destinations, data_ok):
    init_db()
    if not _is_cached(iata, travel_date):            # a row in flight_checks?
        if store_departures(iata, name, lat, lon, travel_date):
            _mark_checked(iata, travel_date)         # ONLY on a successful call
        else:
            data_ok = False                          # provider refused us
    rows = SELECT DISTINCT destination_iata, destination_name
           FROM flights WHERE origin_iata = ? AND checked_date = ?
    return rows, (data_ok or bool(rows))             # old rows are still good data
```

So each `(airport, date)` pair costs **at most one** AeroDataBox call, ever. The
connectivity engine checks `is dest_airport.iata in that list?` — and reads
`data_ok` to decide whether an empty answer means "nothing flies" or "we could
not look", which are reported to the traveller as the different facts they are.

**Data caveat:** the free AeroDataBox tier returns `204` (no content) for many smaller
Indian airports (Kadapa, Kurnool, Puttaparthi…). That's a data‑coverage limit, not a bug —
the code records "0 departures" and moves on.

---

## 3. `sessions.db` — conversations, accounts and saved trips

Despite the name, this file holds three tables. There is **no build script** —
`init_db()` creates them lazily on first import of `database.py`, and they fill
one row at a time as people use the app.

### 3a. Schema (`database.py` → `init_db()`)

```sql
-- the half-filled "form" behind a conversation, plus its transcript
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,     -- uuid4 minted by main.py
    slots_json    TEXT NOT NULL,        -- TripSlots serialised with model_dump_json()
    last_question TEXT,                 -- the question we just asked (extraction context)
    messages_json TEXT,                 -- the full [{role, text}] transcript
    updated_at    TEXT                  -- ISO timestamp
);

-- accounts
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL, -- UNIQUE is what makes a duplicate signup a 409
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,        -- bcrypt; never the password
    created_at    TEXT
);

-- finished plans, for the History drawer
CREATE TABLE IF NOT EXISTS trips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,   -- every query filters on this
    title           TEXT,               -- "nellore -> Tiruvannamalai"
    source          TEXT,
    destination     TEXT,
    travel_date     TEXT,
    source_lat      REAL,
    source_lon      REAL,
    dest_lat        REAL,
    dest_lon        REAL,
    result_json     TEXT NOT NULL,      -- the ENTIRE plan result
    created_at      TEXT,
    chat_session_id TEXT                -- links a trip back to the conversation that planned it
);
```

**Why `result_json` is one blob.** A plan result is a deep, evolving document —
itinerary, notes, per-day stays, transport per mode, drive geometry, tolls,
offers, the return leg, costs, feasibility, specialities, the narrative. Normalising
that into tables would mean a migration every time a section is added, and
nothing ever queries *inside* a saved plan: History lists trips by date and then
reopens one whole. The indexed columns beside it (`user_id`, `travel_date`,
`source`/`destination`) are exactly the ones the list view needs.

**Why `chat_session_id` is on the trip.** Reopening a saved trip restores the
conversation that produced it, rather than starting a blank one. Trips saved
before this column existed simply come back with `NULL` and a fresh chat.

### 3b. How it's used

- **`load_session(session_id)`** —
  ```sql
  SELECT slots_json, last_question, messages_json FROM sessions WHERE session_id = ?
  ```
  → rebuild `TripSlots(**json.loads(slots_json))` and return it with the last
  question and the transcript. `None` if the session is new.
- **`save_session(...)`** — an `INSERT OR REPLACE`, so a turn either creates the
  row or overwrites it. The session id is the client's only handle on the state.
- **`save_trip(user_id, meta, result)`** — called by the plan worker *only when
  someone is logged in*; planning while logged out works, it just is not kept.
- **`list_trips` / `get_trip` / `delete_trip`** — all scoped by `user_id`, so one
  account can never read or delete another's trips.

---

## 4. Non-SQLite caches — the `.*_cache/` family

Not databases, but very much part of the data layer. Each is a directory of JSON
files named by the SHA-1 of the request, and together they are why a second trip
to a region is fast instead of another few minutes of rate-limited lookups.

| Directory | Written by | Holds | Why it is safe to keep |
|-----------|-----------|-------|------------------------|
| `.geo_cache/` | `geocoding.py` | forward + reverse geocodes | Nominatim allows ~1 request/second and a cold plan needs ~30 of them. Coordinates of a town do not move |
| `.overpass_cache/` | `hubs.py` | the `elements` array per Overpass query | The public mirrors frequently answer `429` / `504`; one bad moment used to blank out a whole section. Station and airport geometry changes on the scale of months |
| `.route_cache/` | `routing.py` | ORS distance/duration, and geometry in a `.geom.json` sibling | The road between two fixed points does not materially change, and the ORS free tier is metered |
| `.attractions_cache/` | `attractions.py` | the resolved place list per destination | A Gemini call plus one grounding geocode per place — ~40s for a new region, instant afterwards |
| `.speciality_cache/` | `speciality.py` | what a destination is famous for | A Tavily search plus a Gemini call. What a town is known for does not change week to week |

Two rules hold across all of them:

- **A failure is never cached.** Only a real answer is written. Caching a
  rate-limited flight call as "checked, no flights" once turned an exhausted
  monthly quota into a permanent blank for that airport and date — the bug that
  motivated the rule.
- **To force a refresh, delete the folder** (or a single file inside it) and
  re-run. There is no invalidation logic, deliberately: everything cached here is
  either immutable or changes far slower than anyone re-plans a trip.

### In-memory state that is deliberately *not* persisted

| What | Where | What a restart costs |
|------|-------|----------------------|
| Running plan jobs | `main._PLAN_JOBS` | An in-flight plan; the frontend re-submits |
| A pending stay question | `main._PENDING_STAY_BAND` | The traveller asks again |
| The interrupted revision graph | `stay_revision` `InMemorySaver` | Same as above |

This matches the single-process dev server it runs on. A real deployment would
put the job table in a queue and the checkpointer in Redis or Postgres.

---

## 5. One‑time setup checklist

```bash
cd trip-planner/backend
pip install -r requirements.txt

# .env needs: GEMINI_API_KEY + JWT_SECRET (required),
#             ORS_API_KEY, RAPIDAPI_KEY, TAVILY_API_KEY (each unlocks a section)

python build_train_db.py     # data/*.json           -> trains.db      (required)
python build_flight_db.py    # AeroDataBox           -> flights.db     (optional bulk seed;
                             #                                          app also fetches lazily)
# sessions.db   -> created automatically on first run (sessions, users, trips)
# .*_cache/     -> created automatically as lookups succeed
```

Nothing here needs a server process: every store is either a SQLite file or a
directory of JSON. `git clone`, build `trains.db`, and the app has its whole
data layer.
