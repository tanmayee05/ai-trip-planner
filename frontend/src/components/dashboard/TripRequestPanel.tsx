import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { SlidersHorizontal, MessagesSquare } from "lucide-react";

import type { PlanInput, TravelMode } from "@/api/plan";
import { TripRequestForm } from "@/components/dashboard/TripRequestForm";
import { TripChat } from "@/components/dashboard/TripChat";
import { todayISO } from "@/lib/format";
import { cn } from "@/lib/cn";

type Tab = "form" | "chat";

/** The single shared trip draft. Form and chat both read + write this, so
 *  answers given in one show up in the other. `num_days` stays a string to
 *  match the <input>. */
export interface TripDraft {
  source: string;
  destination: string;
  travel_date: string;
  num_days: string;
  num_people: string;
  travel_mode: TravelMode;
}

interface Props {
  onSubmit: (values: PlanInput) => void;
  busy?: boolean;
  initial?: Partial<PlanInput>;
}

export function TripRequestPanel({ onSubmit, busy = false, initial }: Props) {
  const [tab, setTab] = useState<Tab>("form");

  const [draft, setDraft] = useState<TripDraft>(() => ({
    source: initial?.source ?? "",
    destination: initial?.destination ?? "",
    travel_date: initial?.travel_date ?? todayISO(),
    num_days: initial?.num_days ? String(initial.num_days) : "",
    num_people: initial?.num_people ? String(initial.num_people) : "",
    travel_mode: initial?.travel_mode ?? "public_transport",
  }));

  const patch = (p: Partial<TripDraft>) => setDraft((d) => ({ ...d, ...p }));

  const planInput = useMemo<PlanInput | null>(() => {
    if (draft.source.trim().length < 2) return null;
    if (draft.destination.trim().length < 2) return null;
    if (!draft.travel_date) return null;
    const nd = parseInt(draft.num_days, 10);
    const np = parseInt(draft.num_people, 10);
    return {
      source: draft.source.trim(),
      destination: draft.destination.trim(),
      travel_date: draft.travel_date,
      num_days: Number.isFinite(nd) && nd > 0 ? nd : undefined,
      num_people: Number.isFinite(np) && np > 0 ? np : undefined,
      travel_mode: draft.travel_mode,
    };
  }, [draft]);

  function next() {
    if (planInput) onSubmit(planInput);
  }

  return (
    <div className="card p-5 sm:p-6">
      <div className="mb-5 flex items-center justify-between gap-3">
        <h2 className="font-display text-xl font-extrabold">Plan a trip</h2>

        <div className="flex gap-1 rounded-2xl border-2 border-ink/10 bg-cream p-1">
          {(
            [
              ["form", "Form", SlidersHorizontal],
              ["chat", "Chat", MessagesSquare],
            ] as const
          ).map(([t, label, Icon]) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "relative flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors",
                tab === t ? "text-white" : "text-ink-soft hover:text-ink",
              )}
            >
              {tab === t && (
                <motion.span
                  layoutId="trip-mode-pill"
                  className="absolute inset-0 rounded-xl bg-brand-500 shadow-chunky-sm"
                  transition={{ type: "spring", stiffness: 400, damping: 32 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-1.5">
                <Icon className="h-3.5 w-3.5" />
                {label}
              </span>
            </button>
          ))}
        </div>
      </div>

      {tab === "form" ? (
        <TripRequestForm draft={draft} patch={patch} onNext={next} canNext={!!planInput} busy={busy} />
      ) : (
        <TripChat draft={draft} patch={patch} onNext={next} canNext={!!planInput} busy={busy} />
      )}
    </div>
  );
}
