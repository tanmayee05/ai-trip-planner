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
