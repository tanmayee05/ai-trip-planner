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

- **First plan for a new region is slow (~2–3 min)** — Nominatim (the free
  geocoder) allows only ~1 request/second and a plan needs ~30 place lookups.
  Results are cached to disk (`.geo_cache/`, `.overpass_cache/`, `.route_cache/`),
  so the same region afterwards takes ~7–45 s. The frontend runs the plan as a
  background job and polls for it, so the UI stays responsive.
- **Plan jobs are in-memory** — restarting the backend loses any in-flight job
  (the frontend just re-submits). Saved trips (History) are in `sessions.db` and
  persist.
- If the frontend shows *"Can't reach the server"*, the backend isn't running on
  :8000 (or `VITE_API_BASE_URL` is wrong).
- CORS is pre-configured for `localhost:5173` and `localhost:4173`.
