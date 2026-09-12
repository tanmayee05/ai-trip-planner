import { useState } from "react";
import { motion } from "framer-motion";
import { CalendarPlus, ListMinus, Hourglass, X } from "lucide-react";

import type { Feasibility } from "@/types/api";

interface Props {
  fit: Feasibility;
  /** the traveller wants a longer trip — this many extra days */
  onAddDays: (extra: number) => void;
  /** the traveller would rather change the places */
  onEditPlaces: () => void;
  onCancel: () => void;
}

/**
 * Asked BEFORE planning, when the chosen places can't fit the chosen days.
 *
 * The planner is perfectly capable of planning "the ones that fit" — but
 * deciding WHICH places to sacrifice is the traveller's call, not ours.
 * Picking three of ten and presenting it as the plan is the wrong answer even
 * when the three are well chosen.
 */
export function TooManyPlacesDialog({ fit, onAddDays, onEditPlaces, onCancel }: Props) {
  const shortBy = Math.max(1, fit.short_by ?? fit.needed_days - fit.given_days);
  const [extra, setExtra] = useState(shortBy);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-[1000] grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="too-many-title"
    >
      <motion.div
        initial={{ opacity: 0, y: 14, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
        className="card relative w-full max-w-md p-5 sm:p-6"
      >
        <button
          onClick={onCancel}
          aria-label="Close"
          className="absolute right-3 top-3 grid h-8 w-8 place-items-center rounded-xl text-ink-faint transition hover:bg-ink/[0.05] hover:text-ink"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-100 text-brand-700">
            <Hourglass className="h-4.5 w-4.5" />
          </span>
          <div className="min-w-0 pr-6">
            <h3 id="too-many-title" className="font-display text-lg font-extrabold leading-tight text-ink">
              That's a lot for {fit.given_days} day{fit.given_days === 1 ? "" : "s"}
            </h3>
            <p className="mt-1 text-xs font-medium leading-relaxed text-ink-soft">
              Your {fit.places} places need about <strong className="text-ink">{fit.needed_days} days</strong>{" "}
              at a comfortable pace
              {fit.total_hours ? ` — roughly ${fit.total_hours} hours of visiting and driving` : ""}.
              How would you like to handle it?
            </p>
          </div>
        </div>

        <div className="mt-5 space-y-2.5">
          {/* option 1 — a longer trip */}
          <div className="rounded-2xl border border-ink/10 bg-cream p-3.5">
            <p className="flex items-center gap-1.5 font-display text-sm font-extrabold text-ink">
              <CalendarPlus className="h-4 w-4 text-brand-500" />
              Make the trip longer
            </p>
            <div className="mt-2.5 flex items-end gap-2">
              <label className="flex-1">
                <span className="mb-1 block text-[11px] font-bold uppercase tracking-wide text-ink-faint">
                  Extra days
                </span>
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={extra}
                  onChange={(e) => setExtra(Math.max(1, Math.min(30, Number(e.target.value) || 1)))}
                  className="input !py-2"
                />
              </label>
              <button className="btn-primary !py-2" onClick={() => onAddDays(extra)}>
                Plan {fit.given_days + extra} days
              </button>
            </div>
            <p className="mt-1.5 text-[11px] font-medium text-ink-faint">
              {extra >= shortBy
                ? `${fit.given_days + extra} days fits all ${fit.places} places.`
                : `Still ${shortBy - extra} day${shortBy - extra === 1 ? "" : "s"} short of all ${fit.places} — some would be left out.`}
            </p>
          </div>

          {/* option 2 — fewer places */}
          <button
            onClick={onEditPlaces}
            className="card card-hover flex w-full items-center gap-3 p-3.5 text-left"
          >
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-teal-100 text-teal-700">
              <ListMinus className="h-4 w-4" />
            </span>
            <span className="min-w-0">
              <span className="block font-display text-sm font-extrabold text-ink">
                Choose fewer places
              </span>
              <span className="block text-[11px] font-medium text-ink-faint">
                Back to your places — drop the ones you can live without
              </span>
            </span>
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
