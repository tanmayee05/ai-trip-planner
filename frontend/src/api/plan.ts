import { api } from "@/lib/api";
import type { PlanJob } from "@/types/api";

export interface PlanStop {
  name: string;
  lat: number;
  lon: number;
  category?: string | null;
  blurb?: string | null;
}

export type TravelMode = "public_transport" | "own_vehicle";

export interface PlanInput {
  source: string;
  destination: string;
  travel_date: string; // YYYY-MM-DD
  num_days?: number | null;
  num_people?: number | null;
  travel_mode?: TravelMode;
  stops?: PlanStop[];
}

/** Kick off a plan. Returns immediately with a job in state "running". */
export function startPlan(body: PlanInput) {
  return api.post<PlanJob>("/plan", body).then((r) => r.data);
}

export function getPlanJob(jobId: string) {
  return api.get<PlanJob>(`/plan/${jobId}`).then((r) => r.data);
}

// ---- own-vehicle enrichments (fuel stops, food, stay) ----
export interface EnrichBody {
  kind: "fuel" | "fuel_stops" | "food" | "stay";
  distance_km?: number;
  drive_hours?: number;
  geometry?: [number, number][];
  source?: { lat: number; lon: number };
  destination?: { lat: number; lon: number };
  fuel?: { mileage_kmpl: number; fuel_type: "petrol" | "diesel" | "cng" };
  company?: string; // fuel brand
  preference?: "snacks" | "meals" | "tiffins" | "any";
  radius_km?: number; // how far from the start to look for food / a hotel
  note?: string;
}

export function enrichPlan<T = unknown>(body: EnrichBody) {
  // food/stay do several throttled Gemini + Nominatim calls — give them room
  return api.post<T>("/plan/enrich", body, { timeout: 150_000 }).then((r) => r.data);
}

interface PollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  onTick?: (job: PlanJob, elapsedMs: number) => void;
  signal?: AbortSignal;
}

/**
 * Poll a plan job until it finishes. Resolves with the final job (state
 * "done" or "error"); rejects on timeout or if aborted.
 */
export async function pollPlan(
  jobId: string,
  { intervalMs = 2000, timeoutMs = 300_000, onTick, signal }: PollOptions = {},
): Promise<PlanJob> {
  const started = Date.now();
  for (;;) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const job = await getPlanJob(jobId);
    const elapsed = Date.now() - started;
    onTick?.(job, elapsed);
    if (job.state !== "running") return job;
    if (elapsed > timeoutMs) throw new Error("Planning is taking too long — try again.");
    await new Promise((res) => setTimeout(res, intervalMs));
  }
}
