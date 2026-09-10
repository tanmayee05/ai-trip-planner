import uuid   #uuid is Python's built-in module for generating unique IDs.
import threading
import traceback
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
import sqlite3

from trip_slots import TripSlots, next_question, PLANNER_FIELDS
from slot_extraction import update_slots
from geocoding import geocode
from attractions import get_attractions
from chat_reply import answer_question, looks_like_question, wants_change
from stay_prefs import detect_stay_band
import stay_revision
from itinerary import region_center
from agent import run_trip_plan, plan_stages, estimate_costs   # the LangGraph trip-planning agent
from enrichments import estimate_fuel, fuel_stops_along_route, enrich_food, enrich_stay
"""
init_db(): Create database/tables if needed
load_session():Retrieve existing conversation
save_session():Store current conversation
"""
from database import (
    init_db, load_session, save_session,
    create_user, get_user_by_email, get_user_by_id,
    save_trip, list_trips, get_trip, delete_trip,
)
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user_id, get_optional_user_id,
)

app = FastAPI(title="AI Trip Planner API")

# Create every table on startup if it doesn't exist yet
init_db()

# The React dev server runs on a different origin (localhost:5173). Browsers
# block cross-origin XHR unless the server explicitly allows it - that's CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",  # vite preview
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================================================
# Auth
# ==========================================================================
class SignupRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str


class AuthResponse(BaseModel):
    token: str
    user: UserOut


@app.post("/auth/signup", response_model=AuthResponse)
def signup(req: SignupRequest):
    try:
        user = create_user(req.email, req.name, hash_password(req.password))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with that email already exists")

    token = create_access_token(user["id"], user["email"])
    return AuthResponse(token=token, user=UserOut(**user))


@app.post("/auth/login", response_model=AuthResponse)
def login(req: LoginRequest):
    user = get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong email or password")

    token = create_access_token(user["id"], user["email"])
    return AuthResponse(
        token=token,
        user=UserOut(id=user["id"], email=user["email"], name=user["name"]),
    )


@app.get("/auth/me", response_model=UserOut)
def me(user_id: int = Depends(get_current_user_id)):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(id=user["id"], email=user["email"], name=user["name"])


# ==========================================================================
# Attractions  (for the "pick your stops" step before planning transport)
# ==========================================================================
class AttractionsRequest(BaseModel):
    destination: str = Field(min_length=2, max_length=80)  # a region / state / city


class Attraction(BaseModel):
    name: str
    town: str
    category: str
    blurb: str
    lat: float
    lon: float
    scope: str = "in"                    # "in" the destination, or "nearby" (day-trip)
    distance_km: float | None = None     # from the destination centre
    approx_hours: float | None = None    # rough one-way road time


class AttractionsResponse(BaseModel):
    destination: str
    places: list[Attraction]


@app.post("/attractions", response_model=AttractionsResponse)
def attractions(req: AttractionsRequest):
    data = get_attractions(req.destination)
    places = data["places"]
    if not places:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Couldn't find places for '{req.destination}'. Check the spelling, "
                f"add the state (e.g. 'Tiruvannamalai, Tamil Nadu'), or try again — "
                f"the map lookup is sometimes rate-limited."
            ),
        )
    # `data["destination"]` is the resolved spelling — it can differ from what
    # the user typed when we recovered from a misspelling.
    return AttractionsResponse(destination=data["destination"], places=places)


# ==========================================================================
# Planner  (async: a plan takes 20s-3min, so we run it as a background job
#           and let the frontend poll for the result with a progress UI)
# ==========================================================================
class PlanStop(BaseModel):
    name: str
    lat: float
    lon: float
    category: str | None = None
    blurb: str | None = None


class PlanRequest(BaseModel):
    source: str = Field(min_length=2, max_length=120)       # place name, e.g. "Rebala, Andhra Pradesh"
    destination: str = Field(min_length=2, max_length=120)
    travel_date: date                                       # Pydantic validates YYYY-MM-DD for us
    num_days: int | None = Field(default=None, ge=1, le=60)
    num_people: int | None = Field(default=None, ge=1, le=30)
    travel_mode: Literal["public_transport", "own_vehicle"] = "public_transport"
    stops: list[PlanStop] = []          # picked attractions; empty = plain point-to-point
    chat_session_id: str | None = None  # links the saved trip back to its chat transcript, if any


class GeoPoint(BaseModel):
    name: str
    lat: float
    lon: float
    display_name: str


class ItineraryStop(BaseModel):
    day: int
    name: str
    lat: float
    lon: float
    category: str | None = None
    blurb: str | None = None


class PlanJobStarted(BaseModel):
    job_id: str
    state: str                          # always "running" here
    source: GeoPoint
    destination: GeoPoint
    travel_date: str
    itinerary: list[ItineraryStop] = []   # ordered day-by-day plan (empty for point-to-point)


class PlanStage(BaseModel):
    key: str                            # "itinerary" | "transport" | ...
    label: str                          # what to show the traveller


class PlanJobStatus(BaseModel):
    job_id: str
    state: str                          # "running" | "done" | "error"
    source: GeoPoint
    destination: GeoPoint
    travel_date: str
    itinerary: list[ItineraryStop] = []
    trip_id: int | None = None          # set on "done" if the user was logged in
    result: dict | None = None          # the full check_all_modes() output on "done"
    error: str | None = None
    # --- live progress, so the UI can show the plan being built ---
    stages: list[PlanStage] = []        # every stage THIS trip will go through
    stages_done: list[str] = []         # the keys finished so far
    partial: dict | None = None         # the plan as it stands, same shape as `result`


# in-memory job table. Fine for a single-process dev server; a job is lost on
# restart (the frontend just re-submits). A real deployment would use a queue.
_PLAN_JOBS: dict[str, dict] = {}


def _geocode_or_400(place: str, label: str) -> dict:
    hit = geocode(place)  # returns None on "no such place" OR a transient network failure
    if not hit:
        raise HTTPException(
            status_code=422,
            detail=f"Could not locate '{place}' ({label}). Check the spelling, or add the state.",
        )
    return hit


def _run_plan_job(job_id: str, req: PlanRequest, src: dict, dst: dict, user_id: int | None):
    """Background worker: hand the trip to the LangGraph agent, then persist."""
    job = _PLAN_JOBS[job_id]
    travel_date = req.travel_date.isoformat()

    def on_progress(partial: dict, done: list[str]) -> None:
        # Plain dict assignment: the job table is only ever read by the poll
        # endpoint, and a dict write is atomic under the GIL, so no lock is
        # needed for the reader to see a consistent snapshot.
        job["partial"] = partial
        job["stages_done"] = done

    try:
        result = run_trip_plan(
            source=req.source,
            destination=req.destination,
            travel_date=travel_date,
            travel_mode=req.travel_mode,
            num_days=req.num_days,
            num_people=req.num_people,
            source_geo=src,
            dest_geo=dst,
            stops=job["stops"],      # the agent reasons the day-by-day plan itself
            on_progress=on_progress,  # stream the plan out as it comes together
        )

        if user_id is not None:  # remember it for logged-in users (History)
            saved = save_trip(
                user_id,
                meta={
                    "title": f"{req.source.split(',')[0]} -> {req.destination.split(',')[0]}",
                    "source": req.source, "destination": req.destination,
                    "travel_date": travel_date,
                    "source_lat": src["lat"], "source_lon": src["lon"],
                    "dest_lat": dst["lat"], "dest_lon": dst["lon"],
                    "chat_session_id": req.chat_session_id,
                },
                result=result,
            )
            job["trip_id"] = saved["id"]
        job["result"] = result
        job["state"] = "done"
    except Exception as e:
        # Every stage of the agent degrades on its own now, so reaching here
        # means something genuinely unexpected broke. Keep the traceback in
        # the log for us, but hand the client one readable sentence — the
        # frontend used to show a bare "Could not plan this trip." because
        # there was nothing better in the payload.
        print(traceback.format_exc())
        job["error"] = f"{type(e).__name__}: {e}"[:300]
        job["state"] = "error"
    job["finished_at"] = datetime.now(timezone.utc).isoformat()


@app.post("/plan", response_model=PlanJobStarted, status_code=202)
def start_plan(req: PlanRequest, user_id: int | None = Depends(get_optional_user_id)):
    src = _geocode_or_400(req.source, "source")  # always needed; bad name -> 422 fast

    stops = [s.model_dump() for s in req.stops]
    if stops:
        # transport target = the CENTROID of the picked places, so the arrival
        # hub lands in the middle of the trip region (not a vague state point)
        clat, clon = region_center(stops)
        dst = {
            "lat": clat, "lon": clon,
            "display_name": f"{req.destination} — {len(stops)} stop"
            + ("s" if len(stops) != 1 else ""),
        }
    else:
        dst = _geocode_or_400(req.destination, "destination")

    job_id = str(uuid.uuid4())
    src_pt = GeoPoint(name=req.source, **src)
    dst_pt = GeoPoint(name=req.destination, **dst)
    _PLAN_JOBS[job_id] = {
        "state": "running", "result": None, "error": None, "trip_id": None,
        "source": src_pt, "destination": dst_pt, "travel_date": req.travel_date.isoformat(),
        "stops": stops,              # the agent turns these into a day-by-day itinerary
        "started_at": datetime.now(timezone.utc).isoformat(),
        # progress scaffolding — the stage list is known before any work starts,
        # so the UI can draw the whole checklist on the very first poll
        "stages": plan_stages(req.travel_mode, bool(stops)),
        "stages_done": [],
        "partial": None,
    }

    threading.Thread(
        target=_run_plan_job, args=(job_id, req, src, dst, user_id), daemon=True
    ).start()

    # the itinerary is computed by the agent, so it's not ready yet (empty here,
    # populated in the final /plan/{job_id} result)
    return PlanJobStarted(
        job_id=job_id, state="running",
        source=src_pt, destination=dst_pt, travel_date=req.travel_date.isoformat(),
        itinerary=[],
    )


@app.get("/plan/{job_id}", response_model=PlanJobStatus)
def plan_status(job_id: str):
    job = _PLAN_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="No such plan job (it may have expired on a server restart)")
    # while running, the itinerary comes from the partial so the UI can show
    # the day-by-day plan the moment it exists rather than at the very end
    result = job["result"] or job.get("partial") or {}
    return PlanJobStatus(
        job_id=job_id, state=job["state"],
        source=job["source"], destination=job["destination"], travel_date=job["travel_date"],
        itinerary=result.get("itinerary", []),
        trip_id=job["trip_id"], result=job["result"], error=job["error"],
        stages=[PlanStage(**s) for s in job.get("stages", [])],
        stages_done=job.get("stages_done", []),
        partial=job.get("partial"),
    )


# --------------------------------------------------------------------------
# Re-cost an existing plan.
#
# Party size changes nothing about HOW you get there — the route, timetables and
# stops are all identical — it only moves the per-head arithmetic. Re-running the
# whole agent for it would cost the traveller minutes to change a 2 to a 3. This
# recomputes just the budget from the plan already on screen, reusing the very
# same estimate_costs() the agent uses so the two can never disagree.
# --------------------------------------------------------------------------
class RecostRequest(BaseModel):
    num_days: int = Field(ge=1, le=60)
    num_people: int = Field(ge=1, le=30)
    travel_mode: Literal["public_transport", "own_vehicle"] = "public_transport"
    result: dict          # the finished plan we're re-costing


@app.post("/plan/costs")
def recost_plan(req: RecostRequest):
    res = req.result or {}
    is_drive = req.travel_mode == "own_vehicle"
    state = {
        "travel_mode": req.travel_mode,
        "num_days": req.num_days,
        "num_people": req.num_people,
        # only the fields estimate_costs actually reads
        "transport": {"drive": res.get("drive") or {}} if is_drive else {},
        "tolls": res.get("tolls") or {},
        "return_transport": res.get("return") or {},
    }
    return estimate_costs(state)["costs"]


# --------------------------------------------------------------------------
# Own-vehicle enrichments — called on demand when the user taps "yes" on an
# offer, or asks in chat. Fuel is quick; food/stay (Step C-2) are LLM-backed.
# --------------------------------------------------------------------------
class FuelParams(BaseModel):
    mileage_kmpl: float = Field(gt=0, le=120)
    fuel_type: Literal["petrol", "diesel", "cng"] = "petrol"


class LatLon(BaseModel):
    lat: float
    lon: float


class EnrichRequest(BaseModel):
    kind: Literal["fuel", "fuel_stops", "food", "stay"]
    distance_km: float | None = None
    drive_hours: float | None = None
    geometry: list[list[float]] = []        # [[lat, lon], ...] downsampled route from result.drive.geometry
    source: LatLon | None = None            # endpoints — used to draw a fallback line if geometry is missing
    destination: LatLon | None = None
    fuel: FuelParams | None = None
    company: str | None = None              # HP / Indian Oil / Bharat Petroleum / Shell / ...
    preference: Literal["snacks", "meals", "tiffins", "any"] = "any"
    radius_km: int = Field(default=15, ge=1, le=600)   # how far from "here" to look for food / a hotel
    note: str | None = None                 # optional extra ask ("veg only", "near a temple", ...)


@app.post("/plan/enrich")
def enrich(req: EnrichRequest):
    src = req.source.model_dump() if req.source else None
    dst = req.destination.model_dump() if req.destination else None

    if req.kind == "fuel":
        if not (req.fuel and req.distance_km):
            raise HTTPException(status_code=422, detail="fuel enrichment needs distance_km + fuel params")
        return {"kind": "fuel", "fuel": estimate_fuel(
            req.distance_km, req.fuel.mileage_kmpl, req.fuel.fuel_type, req.company,
        )}

    if req.kind == "fuel_stops":
        if not req.geometry:
            raise HTTPException(status_code=422, detail="fuel_stops needs the route geometry")
        return {"kind": "fuel_stops",
                "stops": fuel_stops_along_route(req.geometry, company=req.company)}

    if req.kind == "food":
        return enrich_food(req.geometry, req.radius_km, req.preference, req.note, src, dst)

    if req.kind == "stay":
        return enrich_stay(req.geometry, req.radius_km, req.note, src, dst)

    raise HTTPException(status_code=422, detail=f"unknown enrichment kind '{req.kind}'")


# ==========================================================================
# Trips (saved plans = History)
# ==========================================================================
class TripSummary(BaseModel):
    id: int
    title: str | None
    source: str | None
    destination: str | None
    travel_date: str | None
    created_at: str


@app.get("/trips", response_model=list[TripSummary])
def get_my_trips(user_id: int = Depends(get_current_user_id)):
    return list_trips(user_id)


@app.get("/trips/{trip_id}")
def get_one_trip(trip_id: int, user_id: int = Depends(get_current_user_id)):
    trip = get_trip(user_id, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@app.delete("/trips/{trip_id}", status_code=204)
def remove_trip(trip_id: int, user_id: int = Depends(get_current_user_id)):
    if not delete_trip(user_id, trip_id):
        raise HTTPException(status_code=404, detail="Trip not found")


# ==========================================================================
# Chat / slot filling  (transcript persisted per session_id)
# ==========================================================================
class ChatMessage(BaseModel):
    role: str          # "user" | "assistant"
    text: str


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    # What the UI already has in the shared form draft. Without this the chat
    # session starts blank and re-asks for a source the user can plainly see
    # filled in on screen.
    known: dict | None = None
    # The plan on screen, if there is one. Sent so a request like "recommend
    # premium stays" can be OFFERED against the real itinerary instead of just
    # answered in the abstract.
    itinerary: list[dict] | None = None
    itinerary_stays: list[dict] | None = None


class PendingAction(BaseModel):
    """A question the assistant is waiting on before it changes the plan."""
    kind: str                       # "stay_band"
    question: str
    options: list[str] = []


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    slots: dict
    ready_to_plan: bool
    messages: list[ChatMessage]     # full transcript so far
    # --- plan revision, negotiated in chat ---
    pending_action: PendingAction | None = None   # waiting on the traveller
    stays_patch: list[dict] | None = None         # apply this to the plan on screen


# Which chat sessions are mid-negotiation about their stays, and about what.
# In-memory, like _PLAN_JOBS — a restart drops the pending question and the
# traveller just asks again.
_PENDING_STAY_BAND: dict[str, str] = {}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    existing = load_session(req.session_id) if req.session_id else None

    if existing is None:
        session_id = str(uuid.uuid4())
        slots = TripSlots()
        last_question = None
        messages: list[dict] = []
    else:
        session_id = req.session_id
        slots = existing["slots"]
        last_question = existing["last_question"]
        messages = list(existing["messages"])

    # Fold in what the form already knows BEFORE extracting from the message.
    # The draft is the shared source of truth across form and chat, so its
    # values win; anything it leaves blank keeps whatever the session learned.
    supplied = {
        k: v
        for k, v in (req.known or {}).items()
        if k in TripSlots.model_fields and v not in (None, "")
    }
    if supplied:
        slots = slots.model_copy(update=supplied)

    # ------------------------------------------------------------------
    # Mid-negotiation about stays? Then this message is the ANSWER to that
    # question, not a trip detail — running slot extraction on "just day 2"
    # would have it read as a travel date. Resume the graph instead.
    # ------------------------------------------------------------------
    if session_id in _PENDING_STAY_BAND:
        outcome = stay_revision.resume(session_id, req.message)
        pending = outcome.get("pending")
        if pending:
            reply = pending["question"]          # answer was unclear; ask again
        else:
            _PENDING_STAY_BAND.pop(session_id, None)
            reply = outcome["message"]

        messages.append({"role": "user", "text": req.message})
        messages.append({"role": "assistant", "text": reply})
        save_session(session_id, slots, last_question, messages)
        return ChatResponse(
            session_id=session_id,
            reply=reply,
            slots=slots.model_dump(),
            ready_to_plan=next_question(slots, PLANNER_FIELDS, conditional=False) is None,
            messages=[ChatMessage(**m) for m in messages],
            pending_action=(
                PendingAction(kind=pending["kind"], question=pending["question"],
                              options=pending["options"])
                if pending else None
            ),
            stays_patch=outcome.get("stays"),
        )

    asking = looks_like_question(req.message)

    # Everything we already know going in — from the form OR learned earlier in
    # this conversation. A question may ADD to this, but must never overwrite
    # it: "best hotels in Vizag?" asked about a Kerala trip must leave the
    # destination as Kerala. Statements, and anything phrased as an explicit
    # change, still update slots normally.
    established = slots.model_dump(exclude_none=True)

    try:
        slots = update_slots(slots, req.message, last_question)
    except Exception as e:  # noqa: BLE001
        # A transient LLM/network failure must not take the whole conversation
        # down with a 500 — seen in testing as an httpx RemoteProtocolError
        # mid-extraction. Keep the slots we already had and carry on; the
        # traveller can restate anything that didn't land. (slot_extraction
        # keeps its fail-loud contract for the CLI; it's the web chat that has
        # to degrade.)
        print(f"slot extraction failed, keeping known slots: {type(e).__name__}: {e}")

    if asking and established and not wants_change(req.message):
        slots = slots.model_copy(update=established)

    # the web app collects mode-specific details with its own controls, and
    # never uses budget/end_date — so don't interrogate for them here
    question = next_question(slots, PLANNER_FIELDS, conditional=False)
    ready = question is None

    # If the traveller actually ASKED something, answer it — then fold the next
    # slot question in as a follow-up. Without this the chat just talks over
    # them with the next form field.
    reply = None
    if asking:
        reply = answer_question(req.message, slots, question)

    if reply is None:
        reply = question if question else "Great, I have everything I need!"

    # ------------------------------------------------------------------
    # Asked about stays in a particular price band, with a plan on screen?
    # Answer as usual, then OFFER to put them in — and stop there. The plan is
    # not touched until the traveller says where, because silently replacing
    # every night's hotel when they only wanted a suggestion is worse than
    # doing nothing. stay_revision holds the pause (LangGraph `interrupt()`).
    # ------------------------------------------------------------------
    pending_action = None
    band = detect_stay_band(req.message)
    if band and req.itinerary:
        offer = stay_revision.propose(
            session_id, band, req.itinerary, req.itinerary_stays or []
        )
        if offer:
            _PENDING_STAY_BAND[session_id] = band
            reply = reply + "\n\n" + offer["question"]
            pending_action = PendingAction(
                kind=offer["kind"], question=offer["question"], options=offer["options"]
            )
            # the follow-up now owns the conversation, so don't also leave a
            # slot question hanging as the extraction context
            question = None

    # the pending slot question stays the extraction context for the next turn,
    # even when we wrapped it inside a longer answer
    last_question = question

    messages.append({"role": "user", "text": req.message})
    messages.append({"role": "assistant", "text": reply})
    save_session(session_id, slots, last_question, messages)

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        slots=slots.model_dump(),
        ready_to_plan=ready,
        messages=[ChatMessage(**m) for m in messages],
        pending_action=pending_action,
    )


@app.get("/chat/{session_id}", response_model=ChatResponse)
def chat_history(session_id: str):
    existing = load_session(session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="No such chat session")
    return ChatResponse(
        session_id=session_id,
        reply="",  # nothing new this call
        slots=existing["slots"].model_dump(),
        # same checklist the live /chat turn uses, so a rehydrated session
        # doesn't claim it still needs a budget/end_date the app never asks for
        ready_to_plan=next_question(existing["slots"], PLANNER_FIELDS, conditional=False) is None,
        messages=[ChatMessage(**m) for m in existing["messages"]],
    )


@app.get("/health")
def health():
    return {"status": "ok"}
