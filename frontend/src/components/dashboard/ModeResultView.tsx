import { useState } from "react";
import { motion } from "framer-motion";
import {
  TrainFront,
  BusFront,
  Plane,
  ArrowRight,
  MapPin,
  Route,
  Info,
  ChevronDown,
  CircleCheck,
  CircleAlert,
  CloudOff,
} from "lucide-react";

import type { HubOption, ModeResult, TransportMode } from "@/types/api";
import { clockTime } from "@/lib/format";
import { cn } from "@/lib/cn";

const MODE_ICON: Record<TransportMode, typeof TrainFront> = {
  train: TrainFront,
  bus: BusFront,
  flight: Plane,
};

function tierChip(tier?: 1 | 2 | 3, state?: string | null) {
  if (!tier) return null;
  const label =
    tier === 1 ? "same district" : tier === 2 ? "same state" : "neighbouring state";
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[11px] font-semibold",
        tier <= 2 ? "bg-teal-100 text-teal-700" : "bg-sunny/25 text-[#8A5A12]",
      )}
    >
      {state ? `${state} · ${label}` : label}
    </span>
  );
}

function LastMile({ hub }: { hub: HubOption }) {
  const lm = hub.last_mile;
  if (!lm) return null;
  const auto = lm.options.find((o) => o.mode === "auto");
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-cream px-3 py-2 text-xs text-ink-soft">
      <span className="flex items-center gap-1 font-medium">
        <Route className="h-3.5 w-3.5" />
        {lm.distance_km} km · {lm.duration_hr} hr by road{lm.estimated ? " (est.)" : ""}
      </span>
      {auto && <span className="text-ink-faint">≈ ₹{auto.estimated_fare} by auto</span>}
    </div>
  );
}

function ServiceRows({ hub, mode }: { hub: HubOption; mode: TransportMode }) {
  if (mode === "train" && hub.trains_available?.length) {
    return (
      <ul className="mt-2 space-y-1.5">
        {hub.trains_available.map((t) => (
          <li key={t.train_number} className="rounded-lg bg-cream px-3 py-2 text-xs">
            <div className="flex items-center justify-between font-semibold text-ink">
              <span>#{t.train_number} {t.train_name}</span>
              <span className="rounded bg-ink/5 px-1.5 py-0.5 text-[10px] text-ink-soft">
                {t.train_class}
              </span>
            </div>
            <div className="mt-0.5 text-ink-soft">
              dep {clockTime(t.departure_time)} → arr {clockTime(t.arrival_time)}
            </div>
          </li>
        ))}
      </ul>
    );
  }
  if (mode === "flight" && hub.flights_available?.length) {
    return (
      <ul className="mt-2 space-y-1.5">
        {hub.flights_available.map((f) => (
          <li key={f.flight_number} className="rounded-lg bg-cream px-3 py-2 text-xs">
            <div className="font-semibold text-ink">
              {f.flight_number} {f.airline ? `· ${f.airline}` : ""}
            </div>
            <div className="mt-0.5 text-ink-soft">
              dep {clockTime(f.departure_time)} → arr {clockTime(f.arrival_time)}
            </div>
          </li>
        ))}
      </ul>
    );
  }
  return null;
}

function Collapsible({
  label,
  count,
  children,
}: {
  label: string;
  count?: number;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-lg px-1 py-1.5 text-xs font-semibold text-ink-soft hover:text-ink"
      >
        <span>
          {label}
          {count != null && <span className="ml-1 text-ink-faint">({count})</span>}
        </span>
        <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="px-1 pb-1 pt-1 text-xs text-ink-soft">{children}</div>}
    </div>
  );
}

export function ModeResultView({ mode, data }: { mode: TransportMode; data: ModeResult }) {
  const Icon = MODE_ICON[mode];
  const rec = data.recommended;
  const others = data.working_options.filter((o) => o.name !== rec?.name);
  const nonConnecting = data.all_options.filter(
    (o) => !data.working_options.some((w) => w.name === o.name),
  );

  return (
    <motion.div
      key={mode}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="mt-5"
    >
      {/* status line */}
      <div className="flex items-center gap-2 text-sm">
        <Icon className="h-4 w-4 text-brand-500" />
        {rec ? (
          <span className="flex items-center gap-1.5 font-semibold text-teal-700">
            <CircleCheck className="h-4 w-4" />
            {mode === "bus" ? "Nearest stand" : `${data.working_options.length} confirmed for your date`}
          </span>
        ) : (
          <span className="flex items-center gap-1.5 font-semibold text-ink-soft">
            <CircleAlert className="h-4 w-4" />
            No confirmed {mode} option
          </span>
        )}
      </div>

      {/* recommended */}
      {rec && (
        <div className="mt-3 rounded-2xl bg-teal-100/50 p-4 ring-1 ring-inset ring-teal-500/20">
          <p className="text-[11px] font-bold uppercase tracking-wide text-teal-700">
            Recommended
          </p>

          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 font-display text-base font-bold text-ink">
            <span className="flex items-center gap-1">
              <MapPin className="h-4 w-4 text-brand-500" />
              {rec.name}
            </span>
            {rec.distance_km != null && (
              <span className="text-xs font-medium text-ink-faint">
                {rec.distance_km} km away
              </span>
            )}
          </div>

          {(rec.arrival_station || rec.arrival_airport) && (
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-soft">
              <ArrowRight className="h-4 w-4" />
              <span className="font-semibold text-ink">
                {rec.arrival_station ?? rec.arrival_airport}
              </span>
              {tierChip(rec.arrival_admin_tier, rec.arrival_state)}
            </div>
          )}

          <ServiceRows hub={rec} mode={mode} />
          <LastMile hub={rec} />

          {data.recommended_reason && (
            <p className="mt-3 rounded-lg bg-paper/70 p-3 text-xs leading-relaxed text-ink-soft">
              <span className="mr-1 font-semibold text-ink">Why:</span>
              {data.recommended_reason}
            </p>
          )}
        </div>
      )}

      {/* note (bus always has one; other modes when nothing/partial).
          "We couldn't check" gets its own neutral treatment — showing it in
          the same amber as "nothing runs that day" would tell the traveller
          this mode is ruled out, when in fact it's simply unknown. */}
      {data.note && (
        <div
          className={cn(
            "mt-3 flex gap-2 rounded-xl p-3 text-xs",
            data.data_unavailable
              ? "bg-ink/[0.04] text-ink-soft ring-1 ring-inset ring-ink/10"
              : "bg-sunny/15 text-[#8A5A12]",
          )}
        >
          {data.data_unavailable ? (
            <CloudOff className="mt-0.5 h-4 w-4 shrink-0" />
          ) : (
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
          )}
          <p>{data.note}</p>
        </div>
      )}

      {/* other working options */}
      {others.length > 0 && (
        <Collapsible label="Other confirmed options" count={others.length}>
          <ul className="space-y-1.5">
            {others.map((o) => (
              <li key={o.name} className="rounded-lg bg-cream px-3 py-2">
                <span className="font-medium text-ink">{o.name}</span>{" "}
                <span className="text-ink-faint">({o.distance_km} km)</span> →{" "}
                {o.arrival_station ?? o.arrival_airport}
              </li>
            ))}
          </ul>
        </Collapsible>
      )}

      {/* transparency: hubs considered + near-source non-connecting */}
      {data.dest_hubs_considered && data.dest_hubs_considered.length > 0 && (
        <Collapsible label="Arrival hubs considered" count={data.dest_hubs_considered.length}>
          <ul className="list-disc space-y-1 pl-4">
            {data.dest_hubs_considered.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </Collapsible>
      )}

      {mode !== "bus" && nonConnecting.length > 0 && (
        <Collapsible label="Near the source, but no direct service" count={nonConnecting.length}>
          <ul className="space-y-1">
            {nonConnecting.map((o) => (
              <li key={o.name}>
                {o.name} <span className="text-ink-faint">({o.distance_km} km)</span>
              </li>
            ))}
          </ul>
        </Collapsible>
      )}
    </motion.div>
  );
}
