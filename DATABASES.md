# Databases — How Each One Is Built and Queried

_Companion to [`PROJECT_OVERVIEW.md`](./PROJECT_OVERVIEW.md) and
[`BACKEND_FILES.md`](./BACKEND_FILES.md)._

The project has **three SQLite databases**, all single files in `trip-planner/backend/`:

| File | Holds | Built by | Queried by | Size / rows |
|------|-------|----------|------------|-------------|
| `trains.db` | Indian Railways timetable | `build_train_db.py` | `train_lookup.py`, `hubs.py` | ~15 MB · 8,490 trains · 170,340 stops |
| `flights.db` | Scheduled flight departures per airport per date | `build_flight_db.py` | `flight_lookup.py` | small · grows per `(airport, date)` fetched |
| `sessions.db` | One row per chat conversation | `database.py` (`init_db`) | `database.py` | tiny · 1 row per session |

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

The `checked_date` column is what makes per‑date caching possible: a row is "airport O
flies to D, on date `checked_date`".

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
get_destinations_from(iata, name, lat, lon, travel_date):
    init_db()
    if not _is_cached(iata, travel_date):        # any row for (iata, date)?
        store_departures(iata, name, lat, lon, travel_date)   # fetch + store once
    return SELECT DISTINCT destination_iata, destination_name
           FROM flights WHERE origin_iata = ? AND checked_date = ?
```

So each `(airport, date)` pair costs **at most one** AeroDataBox call, ever. The
connectivity engine then just checks: `is dest_airport.iata in that list?`

**Data caveat:** the free AeroDataBox tier returns `204` (no content) for many smaller
Indian airports (Kadapa, Kurnool, Puttaparthi…). That's a data‑coverage limit, not a bug —
the code records "0 departures" and moves on.

---

## 3. `sessions.db` — chat conversation state

### 3a. Schema (`database.py` → `init_db()`)

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,     -- uuid4 minted by main.py
    slots_json    TEXT NOT NULL,        -- TripSlots serialised with model_dump_json()
    last_question TEXT                   -- the question we just asked (extraction context)
);
```

There is **no build script** — the table is created lazily on first import of `main.py`
(or `database.py`). It fills up one row at a time as people chat.

### 3b. How it's used

- **`load_session(session_id)`** —
  ```sql
  SELECT slots_json, last_question FROM sessions WHERE session_id = ?
  ```
  → rebuild `TripSlots(**json.loads(slots_json))`, return it with `last_question`.
  Returns `None` if the session is new.
- **`save_session(session_id, slots, last_question)`** — an **upsert**, so one statement
  covers both "first message" and "follow‑up message":
  ```sql
  INSERT INTO sessions (session_id, slots_json, last_question)
  VALUES (?, ?, ?)
  ON CONFLICT(session_id) DO UPDATE SET
      slots_json    = excluded.slots_json,
      last_question = excluded.last_question;
  ```
- `get_connection()` opens with `check_same_thread=False` because FastAPI may handle
  requests for the same session on different worker threads.

**Why persist at all:** HTTP is stateless. The client only ever sends back an opaque
`session_id`; the half‑filled `TripSlots` form and the "what did we just ask" context live
here, so the conversation survives across requests and server restarts.

---

## 4. Non‑SQLite cache: `.overpass_cache/`

Not a database, but part of the data layer. `hubs.py` writes one JSON file per unique
Overpass query, named by the SHA‑1 of the query string:

```
backend/.overpass_cache/<sha1[:16]>.json   →  the "elements" array from that query
```

- **Why:** the public Overpass servers frequently return `429 Too Many Requests` /
  `504 Gateway Timeout`. One bad moment used to blank out a whole section of results.
- **Safe to cache long‑term:** station/airport/town geometry in OpenStreetMap changes on
  the scale of months.
- **To force a refresh:** delete the folder (or a specific file) and re‑run.

---

## 5. One‑time setup checklist

```bash
cd trip-planner/backend
pip install -r requirements.txt

# .env needs: GEMINI_API_KEY, ORS_API_KEY, RAPIDAPI_KEY

python build_train_db.py     # data/*.json           -> trains.db      (required)
python build_flight_db.py    # AeroDataBox           -> flights.db     (optional bulk seed;
                             #                                          app also fetches lazily)
# sessions.db  -> created automatically on first run of main.py / chat
```
