# AI Trip Planner — Project Overview

_Last updated: 2026-09-03_

This document explains **what is built so far**, **the tech stack and why each piece was
chosen**, and **how the whole backend fits together**.

Two companion files go deeper:

| File | Covers |
|------|--------|
| [`BACKEND_FILES.md`](./BACKEND_FILES.md) | Every backend `.py` file: its job, its logic, its functions |
| [`DATABASES.md`](./DATABASES.md) | How `trains.db`, `flights.db` and `sessions.db` are built and queried |

---

## 1. What the project does

Given a plain-English request like:

> _"5 day trip to Coorg, starting from Rebala, by public transport"_

the system will eventually produce a full travel plan. Today it does the two hardest
groundwork pieces:

1. **Conversation → structured trip details** (the "slots" the planner needs).
2. **Source + destination → which transport modes actually connect them**
   (train / bus / flight), with a recommended boarding point and a last‑mile estimate.

### Current status

| Capability | State | Entry point |
|------------|-------|-------------|
| Chat that collects trip details (destination, source, days, travel mode) | ✅ working | `main.py` (HTTP) / `chat_loop.py` (terminal) |
| Session persistence across messages | ✅ working | `database.py` → `sessions.db` |
| Place name → coordinates, and reverse | ✅ working | `geocoding.py` |
| Straight‑line + real road distance | ✅ working | `distance.py`, `routing.py` |
| Find nearby stations / bus stands / airports | ✅ working | `hubs.py` |
| Train timetable database (8,490 trains, 170,340 stops) | ✅ built | `build_train_db.py` → `trains.db` |
| Flight schedule database (per airport + date) | ✅ built, partial data | `build_flight_db.py` → `flights.db` |
| **Connectivity engine** (does mode X reach the destination on date D?) | ✅ working | `connectivity.py` |
| Full day‑by‑day itinerary generation | ⬜ not started | — |
| Frontend | ⬜ not started | — |

---

## 2. The two pipelines

### Pipeline A — Chat / slot filling

```
user message
   │
   ▼
main.py  /chat            ← FastAPI endpoint (or chat_loop.py for terminal)
   │
   ├─ load_session()      ← database.py  (past slots + last question asked)
   │
   ▼
update_slots()            ← slot_extraction.py
   │   └─ Gemini LLM with .with_structured_output(TripSlots)
   │      returns a validated TripSlots object (no JSON parsing by us)
   │
   ▼
next_question()           ← trip_slots.py  (which required field is still empty?)
   │
   ▼
save_session()            ← database.py
   │
   ▼
reply + slots + ready_to_plan
```

**Why a "slots" (pydantic) model instead of free chat:** a planner needs specific facts
(destination, source, days, mode). Modelling them as a Pydantic `TripSlots` form lets us
(a) ask only for what's missing, (b) let the LLM fill several at once from one sentence,
and (c) get schema‑validated output back instead of hand‑parsing text.

### Pipeline B — Connectivity engine

```
source (lat,lon) + destination (lat,lon) + travel_date
   │
   ▼
find_destination_hubs()             ← connectivity.py
   │   nearest stations + airports around the DESTINATION
   │   (kept as full lists, not just the single closest)
   │
   ├───────────────► check_train_connectivity()
   │                   near-source stations  (hubs.py)      ── nearest first
   │                   × destination railheads               ── nearest first
   │                   → find_connecting_trains()  (train_lookup.py + trains.db)
   │                   → keep first pair with a same-day direct train
   │                     AND a last-mile road transfer ≤ 175 km
   │
   ├───────────────► check_bus_connectivity()
   │                   no schedule data → find the district bus stand,
   │                   tell the user to check RedBus / AbhiBus
   │
   └───────────────► check_flight_connectivity()
                       near-source airports × destination airports
                       → get_destinations_from()  (flight_lookup.py + flights.db)
                       → keep first pair with a same-day flight
                         AND last-mile ≤ 175 km
```

**Core idea:** "does a train/flight reach the destination" is answered from **real
timetable data on the actual travel date**, not a guess. Buses have no reliable open
data, so instead of pretending, we point the user at the sites that do.

---

## 3. Tech stack — what and why

### Language & runtime

| Choice | Why | Advantage |
|--------|-----|-----------|
| **Python 3.10+** | Best ecosystem for LLM + data glue work; project is I/O‑bound, not CPU‑bound | Huge library set, quick to iterate, type hints (`str | None`) for clarity |
| **`venv`** | Isolate dependencies from the system Python | Reproducible installs, nothing global gets polluted |

### Web / API layer

| Choice | Why | Advantage |
|--------|-----|-----------|
| **FastAPI** (`main.py`) | Modern async web framework with built‑in request/response validation | Pydantic models validate input automatically; auto‑generated `/docs` (Swagger); minimal boilerplate |
| **Uvicorn** | ASGI server FastAPI runs on | Fast, standard, one‑command launch (`uvicorn main:app --reload`) |
| **Pydantic** | Declare data shapes once (`TripSlots`, `ChatRequest`) | Validation + JSON (de)serialisation + it doubles as the **schema the LLM sees** |

### LLM layer

| Choice | Why | Advantage |
|--------|-----|-----------|
| **Google Gemini** (`gemini-3.6-flash`) | Fast, cheap, strong enough for structured extraction | Low latency for a chat loop; generous free tier |
| **LangChain** (`langchain-google-genai`) | `.with_structured_output(TripSlots)` wires the Pydantic model straight into Gemini's JSON/function‑calling mode | We never write "reply in JSON" prompts or strip ```` ```json ```` fences — the model returns a validated object |
| **python‑dotenv** | Load API keys from `.env` | Secrets stay out of code and out of git (`.gitignore`) |

### Geo / maps layer (all free, keyless except ORS)

| Choice | Used in | Why | Advantage |
|--------|---------|-----|-----------|
| **Nominatim** (OpenStreetMap geocoder) | `geocoding.py` | Turn "Rebala, Andhra Pradesh" → lat/lon, and lat/lon → address hierarchy (village/district/state) | Free, no key; one rule: send a `User-Agent`. Reverse geocoding gives us the admin hierarchy for "is this a village?" logic |
| **Overpass API** (OpenStreetMap query engine) | `hubs.py` | Ask "every bus station / airport / town within N km of this point" | Free, no key; queries raw OSM nodes/ways/relations. This is how we find hubs without a hardcoded list |
| **OpenRouteService (ORS)** | `routing.py` | Real **road** distance & duration between two points (last‑mile from arrival hub → destination) | Free tier with a key; built on OSM road network; gives realistic drive times, not straight‑line |
| **Haversine formula** (pure math) | `distance.py` | Straight‑line "crow‑flies" km between two lat/lon | Zero network cost — used to rank/shortlist hubs *before* spending an ORS call on the winner |

### Transport data

| Choice | Used in | Why | Advantage |
|--------|---------|-----|-----------|
| **Static Indian Railways JSON** (`data/*.json`) → **`trains.db`** | `build_train_db.py`, `train_lookup.py` | Full timetable (routes, stops, running days) as 3 JSON dumps we load once into SQLite | Offline, instant queries, no per‑request API cost or rate limit; running‑days columns let us answer "runs on *this* date" |
| **AeroDataBox** (via RapidAPI) → **`flights.db`** | `build_flight_db.py`, `flight_lookup.py` | Real scheduled departures per airport per date | Actual flight schedules; we cache each `(airport, date)` so we never re‑hit the paid API for the same query |

### Storage

| Choice | Why | Advantage |
|--------|-----|-----------|
| **SQLite** (`trains.db`, `flights.db`, `sessions.db`) | Serverless — a single file, built into Python's stdlib | Nothing to install or run; indexes make 170k‑row lookups instant; perfect for read‑heavy reference data |
| **On‑disk JSON cache** (`.overpass_cache/`) | Overpass public servers are frequently busy (HTTP 429/504) | First good answer is saved forever (OSM hub data barely changes); repeat runs are instant and a busy server can't blank out a whole section |

---

## 4. Design principles used throughout

1. **Real data over guesses.** Train/flight connectivity is checked against the actual
   timetable for the actual date. Where we have no data (buses), we say so and hand off.
2. **Cheap check first, expensive check second.** Haversine (free) shortlists hubs;
   ORS (paid/limited) is only called on candidates that survive.
3. **No hardcoded place lists.** "Nearby towns" and "major junctions" are discovered from
   OpenStreetMap + the train DB's own stop counts, so the logic works for any source.
4. **Fail loud, not silent.** A busy Overpass mirror prints why; a missing destination
   railhead produces an explicit note, not an empty section.
5. **Cache anything that's stable.** OSM geometry, Overpass answers, and flight schedules
   per date are all cached so re‑runs are fast and quota‑friendly.

---

## 5. How to run

```bash
cd trip-planner/backend
python -m venv venv
venv\Scripts\activate           # Windows
pip install -r requirements.txt

# one-time database builds
python build_train_db.py        # data/*.json  -> trains.db
python build_flight_db.py       # AeroDataBox  -> flights.db  (needs RAPIDAPI_KEY)

# chat (terminal)
python chat_loop.py

# chat (HTTP API)
uvicorn main:app --reload       # POST http://127.0.0.1:8000/chat

# connectivity engine (demo in __main__)
python connectivity.py
```

`.env` must contain: `GEMINI_API_KEY`, `ORS_API_KEY`, `RAPIDAPI_KEY`.
