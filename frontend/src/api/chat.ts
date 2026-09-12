import { api } from "@/lib/api";
import type { ChatResponse } from "@/types/api";

/** Whatever the shared trip draft already holds, in TripSlots shape. Sent with
 *  every turn so the assistant never re-asks for something on screen. */
export interface KnownSlots {
  source?: string | null;
  destination?: string | null;
  num_days?: number | null;
  start_date?: string | null;
  num_people?: number | null;
  travel_mode?: string | null;
}

/** One turn of the slot-filling conversation. Pass back the session_id you
 *  got last time to continue the same conversation. */
export function sendChat(body: {
  session_id?: string | null;
  message: string;
  known?: KnownSlots;
  /** the plan on screen, so a request like "recommend premium stays" can be
   *  offered against the real itinerary rather than answered in the abstract */
  itinerary?: unknown[];
  itinerary_stays?: unknown[];
  /** where the trip starts — a re-planned itinerary is ordered from here */
  source_geo?: { lat: number; lon: number };
}) {
  // A plain reply is quick, but a turn that APPLIES a change (e.g. agreeing to
  // premium stays) re-picks hotels: one Gemini call plus several Nominatim
  // lookups that are throttled to ~1/second. Measured at ~20s on a warm cache
  // and well past the 25s default on a cold city — which surfaced as
  // "The request timed out" even though the server had finished the work.
  // Matches the allowance /plan/enrich already gets for the same kind of work.
  return api
    .post<ChatResponse>("/chat", body, { timeout: 180_000 })
    .then((r) => r.data);
}

/** Rehydrate a saved conversation (transcript + slots) by its session_id. */
export function getChatHistory(sessionId: string) {
  return api.get<ChatResponse>(`/chat/${sessionId}`).then((r) => r.data);
}
