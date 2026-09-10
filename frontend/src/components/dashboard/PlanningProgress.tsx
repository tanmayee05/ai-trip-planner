import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TrainFront, BusFront, Plane, Car, MapPin, Check, Loader2 } from "lucide-react";
import { Companion } from "@/components/decor/Companion";
import type { PlanStage } from "@/types/api";
import { cn } from "@/lib/cn";

interface Props {
  source: string;
  destination: string;
  elapsedMs: number;
  /** the steps this trip will go through, straight from the backend */
  stages?: PlanStage[];
  /** which of those are finished — drives the track and the checklist */
  stagesDone?: string[];
}

/** Shown only while a plan is still being built. The sections that ARE ready
 *  stream in below this card, so this one's job is just to say what's still
 *  being worked on — which it now reads from the job's real stage list
 *  instead of guessing from a timer. */
const FALLBACK_STEPS = "Working out your plan…";

const VEHICLES = [Car, BusFront, TrainFront, Plane];
const LANDMARKS = ["🌴", "⛰️", "🏛️", "🏖️", "🕌", "🌊"];

export function PlanningProgress({
  source,
  destination,
  elapsedMs,
  stages = [],
  stagesDone = [],
}: Props) {
  const secs = Math.floor(elapsedMs / 1000);
  const Vehicle = VEHICLES[Math.floor(secs / 4) % VEHICLES.length];
  const [dots, setDots] = useState("");

  useEffect(() => {
    const t = setInterval(() => setDots((d) => (d.length >= 3 ? "" : d + ".")), 420);
    return () => clearInterval(t);
  }, []);

  // "start" is bookkeeping, not something worth showing as a step
  const steps = stages.filter((s) => s.key !== "start");
  const doneSet = new Set(stagesDone);
  const current = steps.find((s) => !doneSet.has(s.key));
  const doneCount = steps.filter((s) => doneSet.has(s.key)).length;

  // real progress when the backend told us the stages; otherwise creep along
  // on the clock so the track still moves
  const pct = steps.length
    ? Math.min(95, 8 + (doneCount / steps.length) * 87)
    : Math.min(95, 12 + secs * 3);

  return (
    <div className="card overflow-hidden p-6 text-center sm:p-8">
      <Companion mood="think" size={72} className="mx-auto" />

      <p className="mt-3 flex items-center justify-center gap-2 font-display text-xl font-extrabold">
        <MapPin className="h-4 w-4 text-brand-500" />
        <span className="max-w-[8rem] truncate">{source}</span>
        <span className="text-ink-faint">→</span>
        <span className="max-w-[8rem] truncate">{destination}</span>
      </p>

      {/* the little journey track */}
      <div className="relative mx-auto mt-6 h-12 max-w-sm">
        <div className="absolute left-0 right-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-ink/5" />
        <motion.div
          className="absolute left-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-brand-gradient"
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
        {/* passing landmarks */}
        {LANDMARKS.map((l, i) => (
          <span key={i} className="absolute top-0 text-sm" style={{ left: `${10 + i * 15}%` }}>
            {l}
          </span>
        ))}
        {/* the traveller */}
        <motion.div
          className="absolute top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full bg-paper text-brand-600 shadow-lift"
          animate={{ left: `${Math.min(88, pct - 4)}%`, rotate: [0, -6, 6, 0] }}
          transition={{
            left: { duration: 0.8, ease: "easeOut" },
            rotate: { duration: 0.8, repeat: Infinity },
          }}
        >
          <Vehicle className="h-5 w-5" />
        </motion.div>
      </div>

      <p className="mt-5 text-sm font-medium text-ink-soft">
        {current ? current.label : FALLBACK_STEPS}
        {dots}
      </p>

      {/* the real checklist — each one ticks off as its section appears below */}
      {steps.length > 0 && (
        <div className="mt-4 flex flex-wrap justify-center gap-1.5">
          {steps.map((s) => {
            const done = doneSet.has(s.key);
            const active = current?.key === s.key;
            return (
              <span
                key={s.key}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors",
                  done
                    ? "bg-teal-100 text-teal-700"
                    : active
                      ? "bg-brand-100 text-brand-700"
                      : "bg-cream text-ink-faint",
                )}
              >
                {done ? (
                  <Check className="h-3 w-3" />
                ) : active ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : null}
                {s.label}
              </span>
            );
          })}
        </div>
      )}

      <p className="mt-3 text-xs text-ink-faint">
        {secs}s · parts of your plan appear below as they're ready. A first look at
        a new region can take a couple of minutes (free map data is rate-limited) —
        instant after that.
      </p>
    </div>
  );
}
