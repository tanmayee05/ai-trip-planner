import { api } from "@/lib/api";
import type { ChatResponse } from "@/types/api";

/** One turn of the slot-filling conversation. Pass back the session_id you
 *  got last time to continue the same conversation. */
export function sendChat(body: { session_id?: string | null; message: string }) {
  return api.post<ChatResponse>("/chat", body).then((r) => r.data);
}

/** Rehydrate a saved conversation (transcript + slots) by its session_id. */
export function getChatHistory(sessionId: string) {
  return api.get<ChatResponse>(`/chat/${sessionId}`).then((r) => r.data);
}
