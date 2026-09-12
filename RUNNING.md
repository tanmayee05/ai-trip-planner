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
- **Nearby places share a day; areas are finished before the next is started.**
  `cluster_stops` groups places within 35 km into areas (single-link, so it
  chains along a corridor of sights), the areas are sequenced nearest-first and
  then straightened with a 2-opt pass, and packing keeps an area together.
  Crossing into the next area mid-day is allowed only when a real block of
  touring time would still be left after the drive. The 2-opt matters more than
  it looks: on a Kerala set it barely changed total distance but cut the trip
  from 9 days to 6, because it put nearby places ADJACENT in the sequence so
  days could pack.
- **Visit lengths are tuned for seeing a place, not lingering in it.** The
  original figures (hill station 6 h, backwater 5 h) were relaxed-pace and
  inflated trips badly. They're now "the main sights, unhurried but
  purposeful", against a 10.5 h touring day.
- **Days are planned practically, not divided evenly.** `feasibility.py` gives
  every place a realistic visit length by category (a wildlife park 5 h, a
  temple 1.5 h) and every hop a real driving duration, then packs days against
  an hour budget (9 h; 4.5 h on arrival day, 6 h on the last) — including the
  morning transfer from wherever the night was spent. Those figures go into the
  itinerary prompt, and a day that overruns its budget is REJECTED and
  re-planned, so practicality is enforced rather than merely requested. The
  deterministic fallback packs by hours too; it used to be `day = i * days // n`.
- **The trip length is questioned when it doesn't fit.** Too few days for the
  places picked and the plan says so ("6 places is a lot for 2 days — they need
  about 6") and offers to add days or drop the furthest stops. Too many, and it
  asks whether you want restful days or would rather head back earlier. An
  empty arrival day is allowed (on a long haul, getting there IS the day); an
  empty day anywhere else is rejected as padding.
- **The map draws both legs of an own-vehicle trip.** The way home is its own
  road path, not the outbound one reversed: it leaves from the LAST place
  visited rather than the destination, and it is routinely a different
  distance (a real Nellore→Auroville trip was 272 km out and 338 km back). It
  renders dashed in the return-panel colour, with a legend, and counts towards
  the map bounds so it can't fall off-screen.
- **Too many places for the days? The traveller is ASKED, before planning.**
  `POST /plan/feasibility` checks the selection against the day count without
  building anything, and "Plan my trip" puts the choice up: make the trip
  longer (with a day stepper that says whether that number fits everything), or
  go back and choose fewer places. Deciding which places to sacrifice is not
  ours to make — the planner silently kept 3 of 10 and presented it as the
  plan, which is the wrong answer even when the 3 are sensible.
  The backend trim below remains the last-resort guarantee for any path that
  skips the question (chat, direct API), never the first response.
- **A plan is never impossible.** If the places don't fit the days, the planner
  now plans the ones that DO and names what it set aside — it used to cram them
  all in and label the result "extremely heavy" (a real Nellore→Tiruvannamalai
  plan asked for 15 hours on a 6-hour departure day). The hour-budget check
  also used to be SKIPPED when time was short, i.e. exactly when it mattered;
  it always runs now.
- **Places are grounded before they are trusted.** Gemini names real places
  correctly but Nominatim will match a bare name anywhere in India —
  "Skandashramam", a cave 1 km from Arunachaleswarar Temple, was being pinned
  in Chennai 140 km away, and the whole itinerary was then planned around that
  phantom distance. A broad-query match is now rejected unless it lands within
  `SAME_TOWN_MAX_KM` of the town the model named.
- **"Speciality" — what the place is famous for.** `speciality.py` finds the
  food, sweets, crafts and signature experiences a destination is known for
  (rose milk, Kanchipuram silk, Kerala's houseboats), each with the well-known
  shop where there is one and a rough price. Tavily first for current web
  snippets, THEN Gemini to structure them — that order matters, because a model
  asked cold happily names a restaurant that shut two years ago. Without a
  Tavily key it still works from the model's own knowledge, and the panel says
  "Web-checked" only when search actually backed it up. Cached per destination
  and computed on the graph's fan-out, so it costs nothing on the second trip
  to a region.
- **The plan is also written out in plain English.** `narrative.py` turns the
  structured plan into a running schedule with clock times — the transport
  they chose, hotel check-in, each stop with how long to allow, the drive
  between, lunch and dinner. Deterministic, from the same hour figures the days
  were packed with, so the prose can't describe a different trip than the one
  planned. It doubles as a feasibility check a human can read at a glance.
- **Every booked day appears in the plan.** Ask for 3 days with two nearby
  places and the planner will rightly fit them into 2 — but day 3 is still part
  of your trip, so it shows as a free/departure day rather than vanishing and
  making the itinerary look truncated (`_fill_trip_days`). A blank day is only
  rejected as padding when LATER days still have sightseeing in them; a blank
  day 1 is arrival, and a blank day at the end is genuinely free. Food is still
  suggested for those days, and a bed for every night but the last.
- **Places can be changed from the chat.** "also include Hampi" / "drop
  Varkala" re-plans the DAYS only — the route to the region, its timetables and
  the budget are all still valid, so rebuilding them would cost minutes for a
  seconds-long change. `plan_itinerary_only()` reuses the same graph nodes, so
  the rules can't diverge. Names are resolved by fuzzy-matching a known list
  (your stops for a removal, the destination's attractions for an addition)
  rather than by parsing free text, and an unmatched name asks rather than
  guesses. This intercepts BEFORE slot extraction — otherwise "include
  Alleppey" is read as a new destination.
- **Stay changes can cover several nights at once.** The per-night options are
  tick-boxes, not one-of buttons, and the parser reads "days 1 and 2",
  "day 2 and day 4", "1, 3" — single-select made the traveller repeat
  themselves for every night they cared about.
- **Stay changes are negotiated, not assumed.** Ask in chat for budget /
  mid-range / premium stays once a plan exists and the assistant answers as
  usual, then asks whether to apply it to the whole trip, one day, or not at
  all — and changes nothing until you say. That pause is a real LangGraph
  `interrupt()` in `stay_revision.py`, checkpointed under the chat session id,
  so it survives the gap between two HTTP requests. An answer it can't read
  loops back to the question rather than guessing (`_MAX_ASKS` = 3), because
  rewriting the wrong night's hotel is worse than asking again. Food picks for
  the affected nights, and every night not named, are preserved.
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
