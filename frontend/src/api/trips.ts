import { api } from "@/lib/api";
import type { TripDetail, TripSummary } from "@/types/api";

export function listTrips() {
  return api.get<TripSummary[]>("/trips").then((r) => r.data);
}

export function getTrip(id: number) {
  return api.get<TripDetail>(`/trips/${id}`).then((r) => r.data);
}

export function deleteTrip(id: number) {
  return api.delete(`/trips/${id}`).then(() => undefined);
}
