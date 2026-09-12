import { motion } from "framer-motion";
import { Clock } from "lucide-react";

import type { NarrativeDay } from "@/types/api";
import { SectionHeader } from "@/components/common/SectionHeader";

/** The trip read as a schedule rather than a list of names: how you travel,
 *  when you check in, which stop is first, how long each takes, where dinner
 *  is. Every time comes from the same visit-length and driving figures the
 *  planner packed the days with, so this can't drift from the itinerary — and
 *  an unrealistic day is obvious here in a way a list of places never is. */
export function DayPlanPanel({ days }: { days?: NarrativeDay[] }) {
  if (!days?.length) return null;

  return (
    <div className="card p-5 sm:p-6">
      <SectionHeader
        emoji="🗓️"
        tone="brand"
        title="Your day, hour by hour"
        subtitle="Estimated times — built from how long each place takes plus the driving"
      />

      <div className="space-y-4">
        {days.map((d, di) => (
          <motion.div
            key={d.day}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: di * 0.05 }}
            className="rounded-2xl border border-ink/10 bg-cream/50 p-4"
          >
            <div className="mb-2.5 flex items-start gap-2">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand-500 text-[10px] font-extrabold text-white">
                {d.day}
              </span>
              <div className="min-w-0">
                <p className="text-[11px] font-bold uppercase tracking-wide text-brand-600">
                  Day {d.day}
                </p>
                <p className="text-xs font-medium leading-snug text-ink-soft">{d.title}</p>
              </div>
            </div>

            <ol className="relative space-y-2 border-l border-dashed border-ink/15 pl-4">
              {d.steps.map((st, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-brand-300 ring-2 ring-cream" />
                  <div className="flex gap-2.5">
                    <span className="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-md bg-paper px-1.5 py-0.5 font-mono text-[11px] font-bold text-ink-soft ring-1 ring-inset ring-ink/10">
                      <Clock className="h-2.5 w-2.5" />
                      {st.time}
                    </span>
                    <span className="text-xs leading-relaxed text-ink">{st.text}</span>
                  </div>
                </li>
              ))}
            </ol>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
