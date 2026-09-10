import type { PlanInput } from "@/api/plan";

/**
 * What a form edit means for a plan that's already on screen.
 *
 *   "none"     nothing actually changed
 *   "cosmetic" only inputs the plan doesn't depend on — set the value, keep the plan
 *   "replan"   the plan is now wrong: same stops, but everything must be worked out again
 *   "restops"  the destination moved, so the chosen stops don't belong to this trip
 */
export type PlanChange = "none" | "cosmetic" | "replan" | "restops";

/**
 * Which fields the plan genuinely depends on:
 *
 *  - `source`, `destination`  route, hubs, distances — everything.
 *  - `num_days`              how the stops are split across days, nights of
 *                            accommodation, and the return date used for
 *                            timetable lookups.
 *  - `travel_mode`           an entirely different plan.
 *  - `travel_date`           material ONLY for public transport, where trains
 *                            and flights are looked up for that exact date. A
 *                            drive doesn't care what day it is, so for an
 *                            own-vehicle trip the date is just a value to store.
 *  - `num_people`            never material. It moves the per-head budget and
 *                            nothing else, so it's re-costed in place instead
 *                            of costing the traveller a full re-plan.
 */
export function classifyChange(
  planned: PlanInput | null | undefined,
  next: PlanInput,
): PlanChange {
  if (!planned) return "restops"; // nothing planned yet — pick stops first

  const norm = (s?: string | null) => (s ?? "").trim().toLowerCase();

  if (norm(planned.destination) !== norm(next.destination)) return "restops";

  const material =
    norm(planned.source) !== norm(next.source) ||
    (planned.num_days ?? null) !== (next.num_days ?? null) ||
    (planned.travel_mode ?? "public_transport") !== (next.travel_mode ?? "public_transport");

  // the date only matters if either the old or the new plan rides a timetable
  const ridesTimetable =
    planned.travel_mode !== "own_vehicle" || next.travel_mode !== "own_vehicle";
  const dateMatters = ridesTimetable && planned.travel_date !== next.travel_date;

  if (material || dateMatters) return "replan";

  const cosmetic =
    (planned.num_people ?? null) !== (next.num_people ?? null) ||
    planned.travel_date !== next.travel_date; // own-vehicle date
  return cosmetic ? "cosmetic" : "none";
}

/** Button wording, so what it says matches what it will do. */
export function nextActionLabel(change: PlanChange): string {
  switch (change) {
    case "restops":
      return "Next: choose stops";
    case "replan":
      return "Re-plan this trip";
    case "cosmetic":
      return "Update trip details";
    default:
      return "Nothing to change";
  }
}
