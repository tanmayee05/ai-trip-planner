import { motion } from "framer-motion";
import { Car, Route, Clock, RefreshCw, Info } from "lucide-react";

import type { DriveResult } from "@/types/api";
import { Counter } from "@/components/common/Counter";
import { SectionHeader } from "@/components/common/SectionHeader";

interface Props {
  drive: DriveResult | null | undefined;
  routeLabel?: string;
  hasStops: boolean;
}

export function DrivePanel({ drive, routeLabel, hasStops }: Props) {
  return (
    <div className="card card-hover card-sky p-5 sm:p-6">
      <SectionHeader
        emoji="🚗"
        tone="sky"
        title="Driving it yourself"
        right={
          routeLabel ? (
            <span className="truncate rounded-full border-2 border-ink/10 bg-paper px-2.5 py-1 text-xs font-bold text-ink-soft">
              {routeLabel}
            </span>
          ) : undefined
        }
      />

      {drive ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl bg-teal-100/50 p-4 ring-1 ring-inset ring-teal-500/20"
        >
          <div className="flex items-center gap-2 text-sm font-semibold text-teal-700">
            <Car className="h-4 w-4" /> Road route to the region
          </div>

          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Stat
              icon={<Route className="h-4 w-4" />}
              value={<Counter value={drive.distance_km} suffix=" km" decimals={1} />}
              label="one way"
            />
            <Stat
              icon={<Clock className="h-4 w-4" />}
              value={<Counter value={drive.duration_hr} suffix=" hr" decimals={1} />}
              label="driving time"
            />
            <Stat
              icon={<RefreshCw className="h-4 w-4" />}
              value={<Counter value={Math.round(drive.distance_km * 2)} suffix=" km" />}
              label="round trip"
            />
          </div>

          <p className="mt-3 text-xs text-ink-soft">
            {drive.estimated
              ? "Straight-line estimate — routing was unavailable, so treat this as a lower bound."
              : "Estimated at typical road speeds — not live traffic."}
            {hasStops && " Add the hops between your chosen stops on top of this."}
            {" "}Set your vehicle in <strong>On the road</strong> below for fuel litres &amp; cost.
          </p>
        </motion.div>
      ) : (
        <div className="flex gap-2 rounded-xl bg-sunny/15 p-3 text-xs text-[#8a5a00]">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <p>Couldn't compute a road route for this trip. The distance may be too long, or the map service was unavailable — try again in a moment.</p>
        </div>
      )}
    </div>
  );
}

function Stat({ icon, value, label }: { icon: React.ReactNode; value: React.ReactNode; label: string }) {
  return (
    <div className="rounded-xl bg-paper/70 p-3">
      <div className="mx-auto flex w-fit text-brand-500">{icon}</div>
      <p className="mt-1 font-display text-base font-bold text-ink">{value}</p>
      <p className="text-[11px] text-ink-faint">{label}</p>
    </div>
  );
}
