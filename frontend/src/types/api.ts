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

export interface ChatResponse {
  session_id: string;
  reply: string;
  slots: TripSlots;
  ready_to_plan: boolean;
  messages: ChatMessage[]; // full transcript persisted on the backend
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

export interface DriveResult {
  distance_km: number;
  duration_hr: number;
  estimated: boolean; // true = straight-line fallback (ORS couldn't route)
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

  itinerary?: ItineraryStop[]; // present when the plan was built from picked stops
  costs?: CostBreakdown;
}

// ---- plan job (async) ----
export type PlanState = "running" | "done" | "error";

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
}
