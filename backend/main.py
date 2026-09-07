import uuid   #uuid is Python's built-in module for generating unique IDs.
import threading
import traceback
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
import sqlite3

from trip_slots import TripSlots, next_question
from slot_extraction import update_slots
from geocoding import geocode
from attractions import get_attractions
from itinerary import region_center
from agent import run_trip_plan   # the LangGraph trip-planning agent
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
    places = get_attractions(req.destination)
    if not places:
        raise HTTPException(
            status_code=422,
            detail=f"Couldn't find well-known places for '{req.destination}'. Try a broader region name.",
        )
    return AttractionsResponse(destination=req.destination, places=places)


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
                },
                result=result,
            )
            job["trip_id"] = saved["id"]
        job["result"] = result
        job["state"] = "done"
    except Exception:
        job["error"] = traceback.format_exc(limit=3)
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
    result = job["result"] or {}
    return PlanJobStatus(
        job_id=job_id, state=job["state"],
        source=job["source"], destination=job["destination"], travel_date=job["travel_date"],
        itinerary=result.get("itinerary", []),
        trip_id=job["trip_id"], result=job["result"], error=job["error"],
    )


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


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    slots: dict
    ready_to_plan: bool
    messages: list[ChatMessage]     # full transcript so far


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

    slots = update_slots(slots, req.message, last_question)
    question = next_question(slots)

    if question is None:
        reply = "Great, I have everything I need!"
        ready = True
        last_question = None
    else:
        reply = question
        last_question = question
        ready = False

    messages.append({"role": "user", "text": req.message})
    messages.append({"role": "assistant", "text": reply})
    save_session(session_id, slots, last_question, messages)

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        slots=slots.model_dump(),
        ready_to_plan=ready,
        messages=[ChatMessage(**m) for m in messages],
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
        ready_to_plan=next_question(existing["slots"]) is None,
        messages=[ChatMessage(**m) for m in existing["messages"]],
    )


@app.get("/health")
def health():
    return {"status": "ok"}
