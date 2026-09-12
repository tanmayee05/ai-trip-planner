# Wayfarer — AI Trip Planner

Tell it where you are and where you fancy going. It works out **which trains,
buses or flights actually run on your date**, picks the places worth seeing,
lays them out into days you could genuinely do, and writes the whole thing up
hour by hour.

Built on real data wherever real data exists — a full Indian Railways timetable,
live flight schedules, the OpenStreetMap road network — and honest about it
wherever it doesn't.

```
  "5 day trip to Coorg, starting from Nellore, by own vehicle"
        │
        ├─ which places are worth your time?           attractions.py
        ├─ do they even fit 5 days?                    feasibility.py
        ├─ how do you get there on THAT date?           connectivity.py
        ├─ what does each day actually look like?       agent.py (LangGraph)
        ├─ where do you eat and sleep each night?       enrichments.py
        └─ what will it cost?                           agent.py
```

---

## What it does

**Plans a trip two ways.** Fill in a form, or just talk to it — "5 days in
Kerala from Guntur, two of us, driving". Both write to the same draft, so
whatever you say in one shows up in the other.

**Checks that trains and flights actually run.** Not "there's an airport
nearby" — it queries a local timetable of 8,490 trains and 170,340 stops for
your specific date, and real scheduled departures per airport. Where no open
data exists (intercity buses), it says so and points you at RedBus rather than
guessing.

**Plans days a person could actually do.** Every place gets a realistic visit
length by category, every hop a real driving duration, and every day an hour
budget. Nearby places share a day; when an area is done, it moves to the next
nearest one. A day that overruns its budget is rejected and re-planned.

**Refuses to hand you an impossible trip.** Ten places in three days doesn't
get quietly trimmed to three — it asks whether you'd rather add days or drop
places, and keeps asking until the trip genuinely fits.

**Streams the plan as it builds.** The itinerary is on screen about two seconds
in, while transport lookups are still running; the rest fills in underneath a
progress animation that reports real stages, not a timer.

**Writes it out in plain English.** A running schedule with clock times: set
off at 07:00, check in at 11:12, first stop, how long to allow, the drive
between, dinner nearby.

**Survives its own dependencies.** Any provider can be rate-limited or down —
flight quota, OpenStreetMap mirrors, the LLM — and the plan still arrives with
an honest note in the section that failed. *"We checked, there's nothing"* and
*"we couldn't check"* are shown as the different facts they are.

**Tells you what the place is famous for.** A Speciality section: the rose milk,
the Kanchipuram silk, the houseboat — with the shop where there is one.

**Changes what you ask it to.** Add or remove a place in chat and the days are
re-planned. Ask for premium stays and it asks which nights before touching
anything.

---

## Quickstart

Two processes: the FastAPI backend on `:8000`, the Vite frontend on `:5173`.

```bash
# ---- backend ----
cd trip-planner/backend
python -m venv venv
venv\Scripts\activate              # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python build_train_db.py           # data/*.json -> trains.db   (required, one-off)
python -m uvicorn main:app --reload

# ---- frontend (second terminal) ----
cd trip-planner/frontend
npm install
npm run dev                        # http://localhost:5173
```

`backend/.env`:

```
GEMINI_API_KEY=...        # itinerary reasoning, slot extraction, place lookups
GEMINI_MODEL=...          # e.g. gemini-3.5-flash-lite
ORS_API_KEY=...           # OpenRouteService — real road distances
RAPIDAPI_KEY=...          # AeroDataBox — flight schedules
JWT_SECRET=...            # any long random string; signs login tokens
TAVILY_API_KEY=...        # optional — grounds chat answers and specialities in live search
```

Only `GEMINI_API_KEY` and `JWT_SECRET` are strictly required to boot. Every
other key degrades to an honest "couldn't check this" in its own section rather
than breaking the app.

Full detail, including what to expect on a cold region: **[RUNNING.md](./RUNNING.md)**.

---

## How it fits together

```
React (Vite + Tailwind + framer-motion)
  │  POST /plan           -> 202 with a job id
  │  GET  /plan/{id}      -> polled; carries `partial`, `stages`, `stages_done`
  ▼
FastAPI  (main.py)
  │  spawns a worker thread
  ▼
LangGraph agent  (agent.py)
  resolve
    ├── cluster_itinerary ──(retry/fallback)── plan_stays ──┐   itinerary branch
    ├── plan_transport ──(own vehicle?)── assess_drive ─────┤   transport branch
    └── find_specialities ──────────────────────────────────┤   speciality branch
                                                            ▼
                                              plan_return_leg   (defer=True barrier)
                                                            │
                                              estimate_costs ─> assemble -> END
```

The three branches run **concurrently** — itinerary reasoning is LLM-bound,
transport is timetable- and Overpass-bound, and they need nothing from each
other. They rejoin at a deferred barrier node, which fires once rather than
once per branch.

Streaming uses `stream_mode="updates"`, so each node's output is published the
moment that node returns rather than at the end of a super-step. That detail is
the difference between the itinerary appearing at 2 seconds and at 270.

### The HTTP surface

| Endpoint | Purpose |
|---|---|
| `POST /auth/signup` · `POST /auth/login` · `GET /auth/me` | accounts, JWT |
| `POST /attractions` | places for a destination, grounded to real coordinates |
| `POST /plan` → `GET /plan/{job_id}` | start a plan; poll it, partial result included |
| `POST /plan/feasibility` | do these places fit these days? (asked before planning) |
| `POST /plan/costs` | re-cost a plan when only the party size changed |
| `POST /plan/enrich` | on-demand fuel stops / food / rest-stop hotels |
| `POST /chat` → `GET /chat/{session_id}` | the conversation, and its transcript |
| `GET /trips` · `GET /trips/{trip_id}` · `DELETE /trips/{trip_id}` | saved trips (History) |
| `GET /health` | liveness |

---

## Where the data comes from

| Source | Used for | Cost |
|---|---|---|
| **Indian Railways JSON** → `trains.db` | 8,490 trains, 170,340 stops, running days | free, offline |
| **AeroDataBox** (RapidAPI) → `flights.db` | real scheduled departures per airport/date | free tier, monthly quota |
| **Nominatim** (OpenStreetMap) | place name ⇄ coordinates | free, 1 req/sec |
| **Overpass** (OpenStreetMap) | nearby stations, bus stands, airports, fuel, tolls | free, mirrors often busy |
| **OpenRouteService** | real road distance, duration and geometry | free tier |
| **Google Gemini** | itinerary reasoning, slot extraction, place and speciality lookups | free tier |
| **Tavily** | live search grounding for chat answers and specialities | optional |

Everything stable is cached on disk — `.geo_cache/`, `.overpass_cache/`,
`.route_cache/`, `.attractions_cache/`, `.speciality_cache/` — so the second
trip to a region is fast and quota-friendly. Failed lookups are deliberately
**not** cached, so a rate-limited hour doesn't become a permanent gap.

---

## Design principles

1. **Real data over guesses.** Connectivity is checked against the actual
   timetable for the actual date. Where there's no data, we say so and hand off.
2. **"Unknown" is not "none".** A provider being down and a genuine absence are
   different facts, and the UI shows them differently.
3. **Never ship an impossible plan.** Hour budgets are enforced, not requested;
   a day that can't be done is re-planned or the places are deferred.
4. **The traveller decides what to sacrifice.** When something has to give, it
   asks rather than choosing for them.
5. **Cheap check first.** Haversine shortlists hubs for free; ORS is only
   called on the survivors.
6. **Degrade, don't fail.** Every stage of the plan can fail on its own without
   taking the rest with it.
7. **Cache what's stable, never cache a failure.**

---

## The docs

| File | What's in it |
|---|---|
| **[RUNNING.md](./RUNNING.md)** | How to run it, and how every behaviour actually behaves |
| **[PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md)** | What's built, the pipelines, the tech stack and why each piece |
| **[BACKEND_FILES.md](./BACKEND_FILES.md)** | Every backend module: its job, its logic, its functions |
| **[DATABASES.md](./DATABASES.md)** | How `trains.db`, `flights.db` and `sessions.db` are built and queried |
| **[tech.md](./tech.md)** | Working notes on the external APIs |

---

## Project layout

```
trip-planner/
├── backend/
│   ├── main.py               FastAPI app — every endpoint
│   ├── agent.py              the LangGraph planning agent
│   ├── feasibility.py        visit lengths, drive times, day packing
│   ├── connectivity.py       does train/bus/flight reach the destination?
│   ├── itinerary.py          route ordering + region centroid
│   ├── narrative.py          the plan as an hour-by-hour schedule
│   ├── attractions.py        places for a destination (Gemini + grounding)
│   ├── speciality.py         what the place is famous for (Tavily + Gemini)
│   ├── enrichments.py        fuel, food, stays, toll plazas
│   ├── stay_prefs.py         reading "premium stays for days 1 and 2"
│   ├── stay_revision.py      human-in-the-loop stay changes (interrupt)
│   ├── place_edits.py        "also include Hampi" / "drop Varkala"
│   ├── chat_reply.py         answering questions, with live search
│   ├── slot_extraction.py    message -> filled trip slots
│   ├── trip_slots.py         the slot schema and question order
│   ├── hubs.py               nearby stations / stands / airports (Overpass)
│   ├── train_lookup.py       trains.db queries
│   ├── flight_lookup.py      flights.db queries + lazy fetch
│   ├── geocoding.py          Nominatim, throttled and cached
│   ├── routing.py            OpenRouteService road distance + geometry
│   ├── distance.py           Haversine
│   ├── database.py           sessions, users, saved trips
│   └── auth.py               password hashing + JWT
└── frontend/
    └── src/
        ├── pages/            DashboardPage, WelcomePage
        ├── components/
        │   ├── dashboard/    the plan: form, chat, picker, panels, map
        │   └── decor/        the ambient backdrop
        ├── hooks/            usePlanJob — start, poll, patch
        ├── api/              typed clients per endpoint
        └── types/api.ts      one shared shape for the whole API
```

---

## Notes and limits

- **Plan jobs live in memory.** A backend restart loses any in-flight job; the
  frontend just re-submits. Saved trips persist in `sessions.db`.
- **A first plan for a new region takes a couple of minutes.** Nominatim allows
  ~1 request/second and a cold plan needs around 30 lookups. Afterwards the
  same region is seconds. The UI streams and explains the wait rather than
  hiding it.
- **Bus timetables are not open data.** Buses get the right bus stand and a
  hand-off to RedBus / AbhiBus, deliberately rather than a fabricated schedule.
- **Visit-length estimates are judgement calls.** `VISIT_HOURS` in
  `feasibility.py` drives every "needs N days" claim; it's one dict at the top
  of the file if your pace differs.
- Single-process dev server: the job table, the pending-question state and the
  LangGraph checkpointer are all in memory. A real deployment would want a
  queue and a shared store.
