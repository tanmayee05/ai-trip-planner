/**
 * TypeScript mirrors of the FastAPI responses. Keeping these in sync with
 * backend/main.py + backend/connectivity.py is what makes the whole app
 * type-safe end to end.
 */

// ---- auth ----
export interface User {
  id: number;
  email: string;
  name: string;
}

// ---- chat / slot filling (POST /chat) ----
export type TravelModeSlot = "own_vehicle" | "public_transport";

export interface TripSlots {
  destination: string | null;
  source: string | null;
  num_days: number | null;
  start_date: string | null; // YYYY-MM-DD if the user stated one
  num_people: number | null;
  budget: number | null;
  travel_mode: TravelModeSlot | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

/** A question the assistant is waiting on before it will change the plan. */
export interface PendingAction {
  kind: string; // "stay_band"
  question: string;
  options: string[];
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  slots: TripSlots;
  ready_to_plan: boolean;
  messages: ChatMessage[]; // full transcript persisted on the backend
  /** set while the assistant is waiting for the traveller to say how far to
   *  apply a change — nothing has been altered yet */
  pending_action?: PendingAction | null;
  /** the agreed replacement for the plan's overnight stays */
  stays_patch?: ItineraryStayFood[] | null;
}

export interface AuthResponse {
  token: string;
  user: User;
}

// ---- geo ----
export interface GeoPoint {
  name: string;
  lat: number;
  lon: number;
  display_name: string;
}

// ---- plan result (from connectivity.check_all_modes) ----
export type TransportMode = "train" | "bus" | "flight";
export type AdminTier = 1 | 2 | 3; // 1 same district, 2 same state, 3 elsewhere

export interface FareOption {
  mode: string; // "local_bus" | "auto"
  estimated_fare: number;
}

export interface LastMile {
  distance_km: number;
  duration_hr: number;
  estimated: boolean; // true = straight-line fallback, ORS was unavailable
  options: FareOption[];
}

export interface TrainService {
  train_number: string;
  train_name: string;
  train_class: string; // "SF" | "EXP" | "PASS"
  departure_time: string; // at the boarding station
  arrival_time: string; // at the arrival station
}

export interface FlightService {
  flight_number: string;
  airline: string | null;
  departure_time: string; // stored as "YYYY-MM-DD HH:MM+05:30"
  arrival_time: string;
}

/** One boarding hub. Plain candidates only carry the first block of fields;
 *  "working options" additionally carry the arrival_* / *_available fields. */
export interface HubOption {
  name: string;
  lat: number;
  lon: number;
  distance_km: number;
  type: TransportMode;
  iata?: string | null;
  train_count?: number;
  major_hub?: boolean;

  // present only on working options
  reaches_destination?: boolean;
  arrival_station?: string;
  arrival_airport?: string;
  arrival_iata?: string;
  arrival_distance_km?: number;
  arrival_state?: string | null;
  arrival_admin_tier?: AdminTier;
  trains_available?: TrainService[];
  flights_available?: FlightService[];
  last_mile?: LastMile;
}

export interface ModeResult {
  mode: TransportMode;
  all_options: HubOption[];
  working_options: HubOption[];
  recommended: HubOption | null;
  recommended_reason?: string;
  note?: string;
  /** true when we could not CHECK this mode (provider rate-limited / down) —
   *  which is a different answer from "checked, nothing runs" */
  data_unavailable?: boolean;
  dest_hubs_considered?: string[];
  district_stands?: HubOption[]; // bus only
}

// ---- attractions + itinerary ----
export type AttractionScope = "in" | "nearby";

export interface Attraction {
  name: string;
  town: string;
  category: string;
  blurb: string;
  lat: number;
  lon: number;
  scope: AttractionScope;
  distance_km: number | null;
  approx_hours: number | null;
}

export interface AttractionsResponse {
  destination: string;
  places: Attraction[];
}

export interface ItineraryStop {
  day: number;
  name: string;
  lat: number;
  lon: number;
  category?: string | null;
  blurb?: string | null;
}

/** Per-day reasoning from the LangGraph itinerary node ("why this day"). */
export interface ItineraryNote {
  day: number;
  rationale: string;
}

export interface DriveResult {
  distance_km: number;
  duration_hr: number;
  estimated: boolean; // true = straight-line fallback (ORS couldn't route)
  geometry?: [number, number][]; // downsampled [lat, lon] road path
}

/** An optional "want food / a rest stop?" prompt the UI shows for own-vehicle trips. */
export interface DriveOffer {
  id: string;
  kind: "food" | "stay";
  question: string;
  reason?: string;
  status: string;
}

export interface FuelStop {
  name: string;
  lat: number;
  lon: number;
  brand?: string | null;
  town?: string;
  km_from_start?: number;
  opening_hours?: string | null;
  price_hint?: string;
}

// ---- food near the driver's current location ----
export interface EateryPlace {
  name: string;
  kind: string; // dhaba / restaurant / food court / tiffin centre / cafe
  why: string;
  where: string; // locality, town — so the UI can say where it is
  lat: number;
  lon: number;
  approx?: boolean;
}
export interface FoodResult {
  kind: "food";
  town: string | null;
  radius_km: number;
  places: EateryPlace[];
  note: string;
}

/** Anything we drop on the map along a driving route. */
export interface RouteMarker {
  name: string;
  lat: number;
  lon: number;
  kind: "fuel" | "food" | "stay" | "toll";
  sub?: string;
}

// ---- toll plazas on the route (own-vehicle, computed during planning) ----
export interface TollPlaza {
  name: string;
  area: string; // town / district the plaza sits in
  km_from_start: number;
  car_cost: number; // ₹ for one pass, a 2-axle car
  cost_estimated: boolean; // true = flat estimate, false = priced in OSM
  lat: number;
  lon: number;
}
export interface TollInfo {
  plazas: TollPlaza[];
  count: number;
  car_cost_one_way: number;
  car_cost_round_trip: number;
  note?: string;
}

// ---- rest-stop stay ----
export interface StayOption {
  name: string;
  band: "budget" | "mid" | "premium";
  price_hint: string;
  why: string;
  where: string; // locality, town — where the hotel actually is
  lat: number;
  lon: number;
  approx?: boolean;
}
export interface StayResult {
  kind: "stay";
  town: string | null;
  radius_km?: number;
  km_from_start?: number;
  options: StayOption[];
  note?: string;
}

// ---- food + hotel suggestions around the ITINERARY (any travel mode) ----
export interface ItineraryStayFood {
  day: number;
  anchor: string; // the last place visited that day — where you'd be staying the night
  town: string | null;
  food: EateryPlace[];
  stay: StayOption[];
  /** the night was left unfilled — the lookup ran out of its time budget or
   *  failed, rather than genuinely finding nothing */
  skipped?: boolean;
}

// ---- the trip back — same shape as the outbound `PlanResult` transport
// fields, plus who/where it starts and ends at ----
export interface ReturnLeg {
  from_label?: string;
  to_label?: string;
  // own-vehicle:
  mode?: "drive";
  drive?: DriveResult | null;
  drive_hours?: number | null;
  tolls?: TollInfo | null;
  // public transport:
  train?: ModeResult;
  bus?: ModeResult;
  flight?: ModeResult;
}

export interface FuelEstimate {
  fuel_type: string;
  mileage_kmpl: number;
  price_per_litre: number;
  one_way: { litres: number; cost: number };
  round_trip: { litres: number; cost: number };
  note: string;
}

export interface CostItem {
  label: string;
  amount: number;
  note: string;
}

export interface CostBreakdown {
  items: CostItem[];
  total: number;
  assumptions: { people: number; days: number };
  note: string;
}

export interface PlanResult {
  // public-transport plans carry these three:
  train?: ModeResult;
  bus?: ModeResult;
  flight?: ModeResult;
  // own-vehicle plans carry these instead:
  mode?: "drive";
  drive?: DriveResult | null;
  drive_hours?: number | null;
  tolls?: TollInfo | null; // toll plazas on the route + car-cost estimate
  offers?: DriveOffer[]; // food / rest-stop prompts for own-vehicle

  itinerary?: ItineraryStop[]; // present when the plan was built from picked stops
  itinerary_notes?: ItineraryNote[]; // the agent's "why this day" reasoning
  itinerary_stays?: ItineraryStayFood[]; // food + hotel picks for each overnight stop
  return?: ReturnLeg; // the trip back, in the reverse direction
  costs?: CostBreakdown;
}

// ---- plan job (async) ----
export type PlanState = "running" | "done" | "error";

/** One step of the planning run, as the backend advertises it up front. */
export interface PlanStage {
  key: string; // "itinerary" | "stays" | "transport" | "drive" | "return" | "costs"
  label: string; // what to show the traveller
}

export interface PlanJob {
  job_id: string;
  state: PlanState;
  source: GeoPoint;
  destination: GeoPoint;
  travel_date: string; // YYYY-MM-DD
  itinerary: ItineraryStop[]; // ordered day-by-day; [] for point-to-point
  trip_id?: number | null;
  result?: PlanResult | null;
  error?: string | null;
  // ---- live progress while state === "running" ----
  /** every stage THIS trip will go through, known before any work starts */
  stages?: PlanStage[];
  /** the stage keys finished so far */
  stages_done?: string[];
  /** the plan as it stands — same shape as `result`, filled in as it builds */
  partial?: PlanResult | null;
}

// ---- trips (history) ----
export interface TripSummary {
  id: number;
  title: string | null;
  source: string | null;
  destination: string | null;
  travel_date: string | null;
  created_at: string; // ISO
}

export interface TripDetail extends TripSummary {
  source_lat: number;
  source_lon: number;
  dest_lat: number;
  dest_lon: number;
  result: PlanResult;
  chat_session_id?: string | null; // the chat that planned this trip, if any
}
