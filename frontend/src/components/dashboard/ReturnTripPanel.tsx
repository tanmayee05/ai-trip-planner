import type { PlanResult, ReturnLeg } from "@/types/api";
import { DrivePanel } from "@/components/dashboard/DrivePanel";
import { RecommendationsPanel } from "@/components/dashboard/RecommendationsPanel";

interface Props {
  ret: ReturnLeg | undefined;
  isDrive: boolean;
  hasStops: boolean;
}

/** The trip back — same drive-plan / train-bus-flight treatment as getting
 *  there, just reversed: it starts from wherever the itinerary actually
 *  ends (the last stop, or the destination) and heads back to the source.
 *  Reuses DrivePanel / RecommendationsPanel wholesale (same shape of data,
 *  same UI) with just the heading swapped for a "way back" one. */
export function ReturnTripPanel({ ret, isDrive, hasStops }: Props) {
  const from = ret?.from_label?.split(",")[0];
  const to = ret?.to_label?.split(",")[0];
  const routeLabel = from && to ? `${from} → ${to}` : undefined;

  return isDrive ? (
    <DrivePanel
      drive={ret?.drive}
      routeLabel={routeLabel}
      hasStops={hasStops}
      emoji="↩️"
      title="Driving back"
    />
  ) : (
    <RecommendationsPanel
      result={(ret ?? null) as PlanResult | null}
      routeLabel={routeLabel}
      emoji="↩️"
      title="Getting back"
      emptyText="Couldn't find confirmed return options yet — check back once your outbound plan settles."
    />
  );
}
