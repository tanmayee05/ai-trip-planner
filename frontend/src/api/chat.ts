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
}) {
  return api.post<ChatResponse>("/chat", body).then((r) => r.data);
}

/** Rehydrate a saved conversation (transcript + slots) by its session_id. */
export function getChatHistory(sessionId: string) {
  return api.get<ChatResponse>(`/chat/${sessionId}`).then((r) => r.data);
}
