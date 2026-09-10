# Running Wayfarer (AI Trip Planner)

Two processes: the **FastAPI backend** (port 8000) and the **Vite frontend** (port 5173).
Run each in its own terminal.

---

## One-time setup (fresh clone)

### Backend
```bash
cd trip-planner/backend
python -m venv venv
venv\Scripts\activate            # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python build_train_db.py          # builds trains.db from data/*.json  (required)
python build_flight_db.py         # seeds flights.db from AeroDataBox   (optional)
```

Create **`trip-planner/backend/.env`**:
```
GEMINI_API_KEY=your-key
ORS_API_KEY=your-openrouteservice-key
RAPIDAPI_KEY=your-rapidapi-key          # for AeroDataBox flight data
JWT_SECRET=any-long-random-string       # signs login tokens
```

### Frontend
```bash
cd trip-planner/frontend
npm install
```
`trip-planner/frontend/.env.development` already points at the backend:
```
VITE_API_BASE_URL=http://localhost:8000
```

---

## Every time you develop

### Terminal 1 — backend
```bash
cd trip-planner/backend
venv\Scripts\activate
python -m uvicorn main:app --reload --port 8000
```
- API:            http://localhost:8000
- Interactive docs: http://localhost:8000/docs

### Terminal 2 — frontend
```bash
cd trip-planner/frontend
npm run dev
```
- App: **http://localhost:5173**

Open the app, create an account, and you're in. The token is kept in
`localStorage`, so a refresh keeps you signed in; the profile menu (top-right)
has **Log out**.

---

## Useful commands

| Command | Where | What |
|---|---|---|
| `npm run build` | frontend | strict typecheck + production build into `dist/` |
| `npm run preview` | frontend | serve the built `dist/` on :4173 |
| `python connectivity.py` | backend | run the planner once from the terminal (no server) |
| `python -m uvicorn main:app --reload` | backend | dev server with auto-reload on file save |

---

## Notes

- **The plan streams.** `/plan` runs the agent with LangGraph's
  `.stream(stream_mode="updates")`, so each node's output is published the
  moment that node returns and `GET /plan/{id}` carries a `partial` result plus
  `stages` / `stages_done`. The UI keeps its planning animation on screen and
  fills in each section underneath as it arrives; the animation fades out when
  the plan is complete. The itinerary shows ~2 s in, even on a cold region
  whose transport lookups take another four minutes.
  **Use `updates`, not `values`:** a `values` snapshot is only emitted at the
  end of a super-step, and the parallel branches share one — measured, that
  held the 2 s itinerary back until 270 s, which defeats the point. The cost of
  `updates` is that `run_trip_plan` accumulates the state itself.
- **Two branches run in parallel.** Itinerary reasoning (Gemini + Nominatim)
  and transport lookups (timetables + Overpass) need nothing from each other,
  so the graph fans out after `resolve` and rejoins at `plan_return_leg`, which
  is declared `defer=True` so it fires once rather than once per branch.
  Nominatim's 1 req/s throttle is lock-guarded because both branches geocode.
- **First plan for a new region is slow (~2–3 min)** — Nominatim (the free
  geocoder) allows only ~1 request/second and a plan needs ~30 place lookups.
  Results are cached to disk (`.geo_cache/`, `.overpass_cache/`, `.route_cache/`),
  so the same region afterwards takes ~7–45 s. The frontend runs the plan as a
  background job and polls for it, so the UI stays responsive.
- **Plan jobs are in-memory** — restarting the backend loses any in-flight job
  (the frontend just re-submits). Saved trips (History) are in `sessions.db` and
  persist.
- **A plan never fails as a whole any more.** Every stage degrades on its own:
  if a provider is rate-limited or down, that one section says so and the rest
  of the plan (itinerary, map, budget, the other transport modes) still shows.
- **Unroutable stops are handled.** ORS is called through its POST
  `/geojson` endpoint with `radiuses: [-1, -1]`. The GET form snaps each
  endpoint to a road within 350 m and returns `404 Could not find routable
  point` otherwise — which hits exactly the places people choose as stops.
  Verified: Tarkarli Beach, Om Beach and Sindhudurg Fort all 404 on GET and all
  route correctly now. Failed geometry lookups are cached so one bad endpoint
  can't re-pay the round trip on every re-plan.
- **Overpass has a circuit breaker.** Exhausting all three mirrors costs
  ~105-135 s (45 s read timeout each), and a plan makes several queries that all
  fail the same way when the mirrors are sick — enough to push a plan past the
  client's patience. After one total failure new queries short-circuit for 90 s
  and the affected sections report "couldn't check"; cached answers are still
  always served, and one success closes the breaker.
- **Flight data is the first thing to run out.** AeroDataBox's free RapidAPI
  tier has a MONTHLY unit quota; once it's spent, every flight lookup returns
  `429` until the quota resets. The Flight tab then reads *"Couldn't check
  flight schedules right now"* — that means **unknown**, not "no flights".
  Trains and buses are unaffected (they come from local `trains.db` + OSM).
  A failed lookup is deliberately **not** cached, so flights start working
  again by themselves when the quota resets.
- If the frontend shows *"Can't reach the server"*, the backend isn't running on
  :8000 (or `VITE_API_BASE_URL` is wrong).
- CORS is pre-configured for `localhost:5173` and `localhost:4173`.
