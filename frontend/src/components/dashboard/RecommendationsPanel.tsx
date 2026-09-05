import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TrainFront, BusFront, Plane, CircleCheck } from "lucide-react";

import type { PlanResult, TransportMode } from "@/types/api";
import { ModeResultView } from "@/components/dashboard/ModeResultView";
import { Companion } from "@/components/decor/Companion";
import { SectionHeader } from "@/components/common/SectionHeader";
import { cn } from "@/lib/cn";

const TABS: { mode: TransportMode; label: string; icon: typeof TrainFront }[] = [
  { mode: "train", label: "Train", icon: TrainFront },
  { mode: "bus", label: "Bus", icon: BusFront },
  { mode: "flight", label: "Flight", icon: Plane },
];

interface Props {
  result: PlanResult | null;
  routeLabel?: string; // "Rebala → Madikeri"
}

export function RecommendationsPanel({ result, routeLabel }: Props) {
  const [active, setActive] = useState<TransportMode>("train");

  // when a fresh result lands, jump to the first mode that has a recommendation
  useEffect(() => {
    if (!result) return;
    const firstConfirmed = TABS.find((t) => result[t.mode]?.recommended)?.mode;
    if (firstConfirmed) setActive(firstConfirmed);
  }, [result]);

  return (
    <div className="card card-hover p-5 sm:p-6">
      <SectionHeader
        emoji="🚊"
        tone="brand"
        title="How to get there"
        right={
          routeLabel ? (
            <span className="truncate rounded-full border-2 border-ink/10 bg-cream px-2.5 py-1 text-xs font-bold text-ink-soft">
              {routeLabel}
            </span>
          ) : undefined
        }
      />

      <div className="flex gap-1 rounded-2xl border-2 border-ink/10 bg-cream p-1">
        {TABS.map(({ mode, label, icon: Icon }) => {
          const confirmed = !!result?.[mode]?.recommended;
          return (
            <button
              key={mode}
              onClick={() => setActive(mode)}
              className={cn(
                "relative flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold transition-colors",
                active === mode ? "text-white" : "text-ink-soft hover:text-ink",
              )}
            >
              {active === mode && (
                <motion.span
                  layoutId="rec-tab-pill"
                  className="absolute inset-0 rounded-xl bg-brand-500 shadow-chunky-sm"
                  transition={{ type: "spring", stiffness: 400, damping: 32 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-1.5">
                <Icon className="h-4 w-4" />
                {label}
                {confirmed && <CircleCheck className="h-3.5 w-3.5 text-teal-300" />}
              </span>
            </button>
          );
        })}
      </div>

      {result?.[active] ? (
        <ModeResultView mode={active} data={result[active]!} />
      ) : (
        <div className="mt-6 flex flex-col items-center gap-2 rounded-2xl border border-dashed border-ink/10 bg-cream/50 px-6 py-10 text-center">
          <Companion mood="idle" size={58} />
          <p className="text-sm font-semibold text-ink">No plan yet</p>
          <p className="max-w-xs text-xs text-ink-faint">
            Fill in the trip form (or describe it in chat) and hit{" "}
            <strong>Plan my trip</strong>. Confirmed trains, buses and flights
            for your date show up here.
          </p>
        </div>
      )}
    </div>
  );
}
