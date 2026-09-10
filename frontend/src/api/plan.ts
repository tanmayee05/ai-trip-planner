import { api } from "@/lib/api";
import type { CostBreakdown, PlanJob } from "@/types/api";

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
  chat_session_id?: string | null; // links the saved trip back to its chat transcript
}

/** Kick off a plan. Returns immediately with a job in state "running". */
export function startPlan(body: PlanInput) {
  return api.post<PlanJob>("/plan", body).then((r) => r.data);
}

/** Recompute just the budget for a plan already on screen. Party size doesn't
 *  change the route, so this spares the traveller a full re-plan; the maths
 *  stays on the server so it can't drift from the planner's own. */
export function recostPlan(body: {
  num_days: number;
  num_people: number;
  travel_mode?: TravelMode;
  result: unknown;
}) {
  return api.post<CostBreakdown>("/plan/costs", body).then((r) => r.data);
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

/** Thrown when the job is still running after `timeoutMs`. Its own class so
 *  the UI can say "still working, we stopped watching" rather than the
 *  catch-all "could not plan this trip", which is a different thing. */
export class PlanTimeoutError extends Error {
  constructor(readonly jobId: string, readonly elapsedMs: number) {
    super(
      `Still planning after ${Math.round(elapsedMs / 1000)}s — the map and travel-data ` +
        `services are being slow. Your trip may still finish; try again in a few minutes.`,
    );
    this.name = "PlanTimeoutError";
  }
}

/**
 * Poll a plan job until it finishes. Resolves with the final job (state
 * "done" or "error"); rejects on timeout or if aborted.
 */
export async function pollPlan(
  jobId: string,
  { intervalMs = 2000, timeoutMs = 600_000, onTick, signal }: PollOptions = {},
): Promise<PlanJob> {
  const started = Date.now();
  for (;;) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const job = await getPlanJob(jobId);
    const elapsed = Date.now() - started;
    onTick?.(job, elapsed);
    if (job.state !== "running") return job;
    if (elapsed > timeoutMs) throw new PlanTimeoutError(jobId, elapsed);
    await new Promise((res) => setTimeout(res, intervalMs));
  }
}
