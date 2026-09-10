import { useCallback, useRef, useState } from "react";
import toast from "react-hot-toast";

import { startPlan, pollPlan, PlanTimeoutError, type PlanInput } from "@/api/plan";
import { apiErrorMessage } from "@/lib/api";
import type { PlanJob } from "@/types/api";

export type PlanPhase = "idle" | "running" | "done" | "error";

export interface PlanJobState {
  phase: PlanPhase;
  job: PlanJob | null; // carries source / destination / result / trip_id
  elapsedMs: number;
  errorMessage: string | null;
}

/**
 * Drives the async /plan flow: POST /plan -> poll /plan/{id} until done.
 * A new run() cancels any in-flight poll.
 */
export function usePlanJob() {
  const [state, setState] = useState<PlanJobState>({
    phase: "idle",
    job: null,
    elapsedMs: 0,
    errorMessage: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async (input: PlanInput) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setState({ phase: "running", job: null, elapsedMs: 0, errorMessage: null });

    try {
      const started = await startPlan(input);
      if (ctrl.signal.aborted) return;
      setState((s) => ({ ...s, job: started }));

      const finished = await pollPlan(started.job_id, {
        // each poll is an in-memory dict read on the server, and a tighter
        // interval is what makes the streamed sections feel like they arrive
        // as they're ready rather than in 2-second jumps
        intervalMs: 1200,
        signal: ctrl.signal,
        onTick: (job, elapsedMs) => {
          setState((s) => ({ ...s, job: { ...job }, elapsedMs }));
        },
      });
      if (ctrl.signal.aborted) return;

      if (finished.state === "error") {
        // the backend now sends one readable sentence; fall back only if it
        // somehow didn't
        const why = finished.error?.trim();
        setState((s) => ({
          ...s,
          phase: "error",
          job: finished,
          errorMessage: why
            ? `The planner hit an error: ${why}`
            : "The planner hit an error. Try again in a moment.",
        }));
        toast.error("Planning failed — try again.");
      } else {
        setState((s) => ({ ...s, phase: "done", job: finished }));
      }
    } catch (err) {
      if (ctrl.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
      // A timeout is not a failure to plan — the job is still running on the
      // server. Say that, instead of the catch-all that told the user nothing.
      const msg =
        err instanceof PlanTimeoutError
          ? err.message
          : apiErrorMessage(err, "Could not plan this trip.");
      setState((s) => ({ ...s, phase: "error", errorMessage: msg }));
      toast.error(msg);
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState({ phase: "idle", job: null, elapsedMs: 0, errorMessage: null });
  }, []);

  /** Drop a saved trip straight in as the current result (History → reopen). */
  const showExisting = useCallback((job: PlanJob) => {
    abortRef.current?.abort();
    setState({ phase: "done", job, elapsedMs: 0, errorMessage: null });
  }, []);

  return { ...state, run, reset, showExisting };
}
