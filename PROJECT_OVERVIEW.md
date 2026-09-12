# AI Trip Planner — Project Overview

_Last updated: 2026-09-12_

This document explains **what is built so far**, **the tech stack and why each piece was
chosen**, and **how the whole backend fits together**.

Companion files go deeper:

| File | Covers |
|------|--------|
| [`README.md`](./README.md) | The front door: what it does, quickstart, the HTTP surface |
| [`RUNNING.md`](./RUNNING.md) | How to run it, and how each behaviour actually behaves |
| [`BACKEND_FILES.md`](./BACKEND_FILES.md) | Every backend `.py` file: its job, its logic, its functions |
| [`DATABASES.md`](./DATABASES.md) | How `trains.db`, `flights.db` and `sessions.db` are built and queried |

---

## 1. What the project does

Given a plain-English request like:

> _"5 day trip to Coorg, starting from Rebala, by public transport"_

the system produces a complete travel plan: which places are worth seeing, whether
they fit the days available, which trains/buses/flights actually run on that date, a
day-by-day route you could genuinely follow, where to eat and sleep each night, what
the place is famous for, the drive home, and a ball-park budget — written out both as
sections and as an hour-by-hour schedule.

### Current status

| Capability | State | Entry point |
|------------|-------|-------------|
| Chat that collects trip details (destination, source, days, people, mode) | ✅ working | `main.py` `/chat` · `chat_loop.py` (terminal) |
| Form + chat over one shared draft, either can drive the flow | ✅ working | `TripRequestPanel.tsx` |
| Session persistence across messages | ✅ working | `database.py` → `sessions.db` |
| Accounts, login, saved trips (History) | ✅ working | `auth.py`, `database.py` |
| Place name → coordinates, and reverse | ✅ working | `geocoding.py` |
| Straight‑line + real road distance + route geometry | ✅ working | `distance.py`, `routing.py` |
| Find nearby stations / bus stands / airports | ✅ working | `hubs.py` |
| Train timetable database (8,490 trains, 170,340 stops) | ✅ built | `build_train_db.py` → `trains.db` |
| Flight schedule database (per airport + date, lazily fetched) | ✅ built | `build_flight_db.py` → `flights.db` |
| **Connectivity engine** (does mode X reach the destination on date D?) | ✅ working | `connectivity.py` |
| Attraction discovery, grounded to real coordinates | ✅ working | `attractions.py` |
| **Practical day planning** — visit lengths, drive times, hour budgets | ✅ working | `feasibility.py` |
| **Feasibility negotiation** — too many places? ask, don't decide | ✅ working | `/plan/feasibility` + `TooManyPlacesDialog.tsx` |
| **Day-by-day itinerary** (LLM-reasoned, validated, with a deterministic fallback) | ✅ working | `agent.py` |
| Food + a hotel for every day and night of the trip | ✅ working | `enrichments.py` |
| Own-vehicle extras: fuel stops, toll plazas, rest halts | ✅ working | `enrichments.py`, `own_vehicle.py` |
| The return leg, from the last place visited | ✅ working | `agent.py` → `plan_return_leg` |
| Ball-park budget, re-costed in place when party size changes | ✅ working | `agent.py`, `/plan/costs` |
| **Plain-English schedule** with clock times | ✅ working | `narrative.py` |
| **Speciality** — famous food, crafts, signature experiences | ✅ working | `speciality.py` |
| Change places or stays from the chat | ✅ working | `place_edits.py`, `stay_revision.py` |
| **Streaming plans** — sections appear as they are ready | ✅ working | `agent.py` (`stream_mode="updates"`) |
| Frontend (React + Vite + Tailwind + framer-motion) | ✅ working | `frontend/src` |

---

## 2. The pipelines

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

### Pipeline C — The planning agent (LangGraph)

Once the traveller has picked their places, `/plan` hands everything to a
`StateGraph` and returns a job id immediately. The graph is the shape it is
because planning a trip is a pipeline with **branches that don't depend on each
other** and one step that **loops**.

```
resolve                         feasibility: do these places fit these days?
   │                            (too many -> plan what fits, defer the rest)
   ├──────────── fan out, run concurrently ────────────┐
   │                         │                         │
cluster_itinerary        plan_transport         find_specialities
   │  ▲ retry                │                         │
   │  └── invalid? ──────────┤                         │
   │      (names wrong, day  │ own vehicle?            │
   │       over its hours)   ▼                         │
   │                   assess_drive                    │
   ▼                   (geometry, tolls, offers)       │
plan_stays                   │                         │
   │                         │                         │
   └─────────────────────────┴─────────────────────────┘
                             ▼
                     plan_return_leg          ← defer=True: a BARRIER, fires once
                             ▼
                      estimate_costs
                             ▼
                         assemble  →  result (+ narrative)
```

**Why the branches are parallel.** The itinerary is Gemini-bound and the
transport check is timetable/Overpass-bound; neither needs the other. Running
them together removes most of their combined wall time.

**Why the join is deferred.** With branches of unequal length, an ordinary
fan-in fires the join node once per incoming edge — the return leg would be
planned twice. `defer=True` makes it wait for everything.

**Why the itinerary node loops.** Gemini is asked for a day-by-day plan and the
answer is then *checked*: every place used exactly once, day numbers contiguous,
and **no day over its hour budget**. A failure is fed back into the re-prompt.
After three tries it falls through to `fallback_itinerary`, a deterministic
packing that respects the same budgets. A quota or key error skips straight to
the fallback, since retrying changes nothing.

**Why it streams.** The graph runs with `stream_mode="updates"`, so each node's
output is published the instant that node returns. `GET /plan/{id}` carries a
`partial` result plus `stages`/`stages_done`, and the UI paints each section as
it lands. (`stream_mode="values"` emits only at super-step boundaries, which —
measured — held a 2-second itinerary back until 270 seconds, because it shares a
super-step with the slow transport branch.)

---

### Pipeline D — Practical day planning

The part that decides whether a plan is any good. All deterministic, so it can
be explained rather than merely trusted (`feasibility.py`):

```
places
   │
   ▼
cluster_stops()          places within 35 km form one "area"
   │
   ▼
order_by_cluster()       walk areas nearest-first, then 2-opt to take the
   │                     crossings out (a greedy order backtracked ~200 km
   │                     across Kerala and cost a whole extra day)
   ▼
pack_days()              fill a day until it's full, then start the next
   │                       · visit hours by category (wildlife 4h, temple 1h)
   │                       · driving hours between stops
   │                       · the morning transfer from where you slept
   │                       · 10.5h a day, 5.5h on arrival, 6.5h on the last
   │                       · ONE AREA PER DAY unless real time remains
   ▼
assess()                 verdict: ok / too_short / too_long, with the numbers
```

`too_short` is not resolved silently. `/plan/feasibility` is called **before**
planning so the UI can ask: add days, or choose fewer places? — and it keeps
asking until the trip fits. The backend's "plan what fits and defer the rest"
remains only as a last-resort guarantee for paths that skip the question.

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
| **LangGraph** (`agent.py`) | Planning is a pipeline with branches that don't depend on each other, one step that loops, and one that has to stop and ask the traveller | Nodes share one state object; parallel branches, a deferred barrier join, a bounded retry cycle and `interrupt()`-based human-in-the-loop all come for free — and `.stream()` gives per-node progress to the UI |
| **Tavily** (optional) | A model asked cold will name a restaurant that shut two years ago | Live search snippets go into the prompt FIRST, so chat answers and specialities reflect what people are saying now; the UI marks results "Web-checked" only when search actually ran |
| **python‑dotenv** | Load API keys from `.env` | Secrets stay out of code and out of git (`.gitignore`) |

### Frontend

| Choice | Why | Advantage |
|--------|-----|-----------|
| **React + TypeScript** (Vite) | The plan is a lot of interdependent state — a shared draft, a polling job, streamed partials | One `types/api.ts` mirrors the API, so a backend shape change surfaces as a compile error rather than a blank screen |
| **Tailwind CSS** | The UI has a strong, consistent visual language (blob shapes, chunky shadows, a sunset palette) | Design tokens live in `tailwind.config.js`; every panel reaches for the same ones |
| **framer-motion** | Sections stream in, the progress card has to feel alive, the nav pill glides between steps | `layoutId` handles the shared-element moves; `useScroll`/`useSpring` drive the backdrop parallax; `useReducedMotion` switches it all off |
| **react-leaflet** + OSM tiles | Free map tiles, and the drive legs are real ORS geometry | Both legs draw as separate polylines — the way home leaves from the last place visited, not the destination, and is often the longer half |
| **TanStack Query** | Attractions are fetched per destination and cached | Re-opening the picker for the same place is instant |

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
| **On‑disk JSON caches** (`.geo_cache/`, `.overpass_cache/`, `.route_cache/`, `.attractions_cache/`, `.speciality_cache/`) | Every external source is rate-limited, quota-limited or frequently busy | The first good answer is kept (roads, hub geometry and what a town is famous for barely change), so a repeat region is near-instant and a busy mirror can't blank out a section. **Failures are deliberately not cached** — a rate-limited hour must not become a permanent gap |
| **In-memory job + negotiation state** (`_PLAN_JOBS`, `_PENDING_STAY_BAND`, LangGraph `InMemorySaver`) | A plan runs 30s–5min in a background thread and the UI polls it | No queue to run for a single-process dev server. The trade: a restart loses an in-flight job (the frontend re-submits) and a pending question (the traveller asks again) |

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
5. **Cache anything that's stable — never cache a failure.** OSM geometry, Overpass
   answers, routes and flight schedules per date are all cached. A failed lookup is not:
   marking a rate-limited flight call as "checked, no flights" once turned an exhausted
   quota into a permanent blank.
6. **"We couldn't check" is not "there is none".** A provider being down and a genuine
   absence are different facts, and the UI renders them differently — grey with a
   cloud-off icon for unknown, amber for a real dead end.
7. **Degrade per section, never as a whole.** Every stage guards itself, so a flight
   quota or an Overpass outage costs you that one panel and nothing else. One unguarded
   exception used to discard a finished itinerary, map and budget along with it.
8. **Never present an impossible plan.** Hour budgets are enforced in validation, not
   merely requested in a prompt — an LLM told "keep days realistic" still returns a
   15-hour day.
9. **When something has to give, the traveller chooses.** Too many places for the days
   is a question, not a silent trim.

---

## 5. How to run

Full instructions, including what to expect on a cold region, are in
[`README.md`](./README.md) and [`RUNNING.md`](./RUNNING.md). The short version —
two processes, backend on `:8000` and frontend on `:5173`:

```bash
# frontend
cd trip-planner/frontend && npm install && npm run dev
```

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

# the API (this is what the frontend talks to)
python -m uvicorn main:app --reload

# individual pieces, each with a demo in __main__
python connectivity.py          # does train/bus/flight reach a destination?
python feasibility.py           # (imported) day packing and hour budgets
python speciality.py            # what a place is famous for
python agent.py                 # a whole plan, printed
```

`.env` must contain `GEMINI_API_KEY` and `JWT_SECRET`; `ORS_API_KEY`,
`RAPIDAPI_KEY` and `TAVILY_API_KEY` each unlock a section and degrade to an
honest "couldn't check this" when absent.

`.env` must contain: `GEMINI_API_KEY`, `ORS_API_KEY`, `RAPIDAPI_KEY`.
