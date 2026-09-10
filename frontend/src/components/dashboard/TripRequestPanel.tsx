import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { SlidersHorizontal, MessagesSquare, RefreshCw, Minimize2 } from "lucide-react";

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
  /** when given, shows a minimise button that folds the panel down to an icon */
  onCollapse?: () => void;
  /** chat transcript id — owned by the page so it lives as long as the form */
  chatSessionId: string | null;
  onChatSessionId: (id: string | null) => void;
  /** a plan is already on screen — the chat is now for changes, so it stops
   *  driving itself to the next step and offers a re-plan instead */
  planned?: boolean;
}

export function TripRequestPanel({ onSubmit, busy = false, initial, onCollapse, chatSessionId, onChatSessionId, planned = false }: Props) {
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

  const planInput = useMemo<PlanInput | null>(() => toPlanInput(draft), [draft]);

  /** Move on to the next step (fetching places) with the shared draft.
   *  `override` lets a caller that has just patched the draft hand its own
   *  values in — `draft` in this closure is still the pre-patch one, and a
   *  chat turn that fills the last slot has to advance on the same tick. */
  function next(override?: Partial<TripDraft>) {
    const values = toPlanInput(override ? { ...draft, ...override } : draft);
    if (values) onSubmit(values);
  }

  /** Wipe the shared draft AND the chat transcript so the user can start a
   *  fresh trip from scratch. Remounting TripChat via `resetKey` clears its
   *  local state without needing to reach into it. */
  const [resetKey, setResetKey] = useState(0);
  const dirty =
    !!draft.source || !!draft.destination || !!draft.num_days || !!draft.num_people;

  function startOver() {
    setDraft({
      source: "",
      destination: "",
      travel_date: todayISO(),
      num_days: "",
      num_people: "",
      travel_mode: "public_transport",
    });
    onChatSessionId(null); // drop the transcript too — a new trip, a new chat
    setResetKey((k) => k + 1);
  }

  return (
    <div className="card p-5 sm:p-6">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="font-display text-xl font-extrabold">Plan a trip</h2>
          {dirty && (
            <button
              onClick={startOver}
              disabled={busy}
              title="Clear everything and start a new trip"
              className="flex items-center gap-1 rounded-full border border-ink/10 px-2 py-1 text-[10px] font-bold text-ink-soft transition hover:border-brand-300 hover:text-brand-600 disabled:opacity-40"
            >
              <RefreshCw className="h-3 w-3" /> New
            </button>
          )}
        </div>

        <div className="flex items-center gap-1.5">
        <div className="flex gap-1 rounded-2xl border border-ink/10 bg-cream p-1">
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

        {onCollapse && (
          <button
            onClick={onCollapse}
            title="Minimise"
            aria-label="Minimise the trip panel"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-xl text-ink-faint transition hover:bg-ink/[0.05] hover:text-ink"
          >
            <Minimize2 className="h-4 w-4" />
          </button>
        )}
        </div>
      </div>

      {tab === "form" ? (
        <TripRequestForm draft={draft} patch={patch} onNext={next} canNext={!!planInput} busy={busy} />
      ) : (
        <TripChat
          key={resetKey}
          draft={draft}
          patch={patch}
          onNext={next}
          canNext={!!planInput}
          busy={busy}
          sessionId={chatSessionId}
          onSessionId={onChatSessionId}
          planned={planned}
        />
      )}
    </div>
  );
}

/** The shared draft → planner input. Returns null while anything the planner
 *  needs is still missing, which is what gates every "Next" in the panel.
 *  Days and people are required: the itinerary is split per day and every
 *  cost estimate is per head, so neither has a sane default. */
export function toPlanInput(d: TripDraft): PlanInput | null {
  if (d.source.trim().length < 2) return null;
  if (d.destination.trim().length < 2) return null;
  if (!d.travel_date) return null;
  const nd = parseInt(d.num_days, 10);
  const np = parseInt(d.num_people, 10);
  if (!Number.isFinite(nd) || nd < 1) return null;
  if (!Number.isFinite(np) || np < 1) return null;
  return {
    source: d.source.trim(),
    destination: d.destination.trim(),
    travel_date: d.travel_date,
    num_days: nd,
    num_people: np,
    travel_mode: d.travel_mode,
  };
}
