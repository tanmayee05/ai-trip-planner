import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowUpDown, MapPin, Flag, CalendarDays, ArrowRight, Bus, Car } from "lucide-react";

import type { TravelMode } from "@/api/plan";
import type { TripDraft } from "@/components/dashboard/TripRequestPanel";
import { todayISO } from "@/lib/format";
import { cn } from "@/lib/cn";

interface Props {
  draft: TripDraft;
  patch: (p: Partial<TripDraft>) => void;
  onNext: () => void;
  canNext: boolean;
  busy?: boolean;
}

export function TripRequestForm({ draft, patch, onNext, canNext, busy = false }: Props) {
  const [touched, setTouched] = useState(false);

  const days = parseInt(draft.num_days, 10);
  const people = parseInt(draft.num_people, 10);
  const daysBad = !Number.isFinite(days) || days < 1;
  const peopleBad = !Number.isFinite(people) || people < 1;

  function swap() {
    patch({ source: draft.destination, destination: draft.source });
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (canNext && !busy) onNext();
  }

  return (
    <div>
      <p className="text-xs text-ink-faint">
        Place names work best with a state, e.g. &ldquo;Rebala, Andhra Pradesh&rdquo;.
        Fields marked <span className="font-bold text-brand-500">*</span> are required.
      </p>

      <form onSubmit={submit}>
        <div className="relative mt-4 space-y-3">
          <FieldRow
            icon={<MapPin className="h-4 w-4 text-brand-500" />}
            label="From"
            value={draft.source}
            onChange={(v) => patch({ source: v })}
            placeholder="Your starting point"
            invalid={touched && draft.source.trim().length < 2}
            disabled={busy}
          />

          <button
            type="button"
            onClick={swap}
            disabled={busy}
            aria-label="Swap start and destination"
            className="absolute right-3 top-1/2 z-10 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full bg-paper text-ink-soft shadow-soft ring-1 ring-ink/10 transition hover:text-brand-600 hover:shadow-lift active:scale-95"
          >
            <ArrowUpDown className="h-4 w-4" />
          </button>

          <FieldRow
            icon={<Flag className="h-4 w-4 text-teal-600" />}
            label="To"
            value={draft.destination}
            onChange={(v) => patch({ destination: v })}
            placeholder="A place or region (e.g. Kerala)"
            invalid={touched && draft.destination.trim().length < 2}
            disabled={busy}
          />
        </div>

        <div className="mt-3 grid grid-cols-[1fr_auto_auto] gap-2">
          <div>
            <label className="label flex items-center gap-1.5">
              <CalendarDays className="h-3.5 w-3.5" /> Travel date
            </label>
            <input
              type="date"
              className="input"
              value={draft.travel_date}
              min={todayISO()}
              onChange={(e) => patch({ travel_date: e.target.value })}
              disabled={busy}
            />
          </div>
          <div className="w-16">
            <label className="label">
              Days <span className="text-brand-500">*</span>
            </label>
            <input
              type="number"
              min={1}
              max={60}
              className={cn("input px-2", touched && daysBad && "ring-2 ring-brand-400")}
              placeholder="2"
              value={draft.num_days}
              onChange={(e) => patch({ num_days: e.target.value })}
              disabled={busy}
            />
          </div>
          <div className="w-16">
            <label className="label">
              People <span className="text-brand-500">*</span>
            </label>
            <input
              type="number"
              min={1}
              max={30}
              className={cn("input px-2", touched && peopleBad && "ring-2 ring-brand-400")}
              placeholder="2"
              value={draft.num_people}
              onChange={(e) => patch({ num_people: e.target.value })}
              disabled={busy}
            />
          </div>
        </div>

        <div className="mt-3">
          <span className="label">How are you travelling?</span>
          <div className="grid grid-cols-2 gap-1 rounded-2xl border border-ink/10 bg-cream p-1">
            {(
              [
                ["public_transport", "Public transport", Bus],
                ["own_vehicle", "Own vehicle", Car],
              ] as const
            ).map(([m, label, Icon]) => (
              <button
                key={m}
                type="button"
                onClick={() => patch({ travel_mode: m as TravelMode })}
                disabled={busy}
                className={cn(
                  "relative flex items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-xs font-semibold transition-colors",
                  draft.travel_mode === m ? "text-white" : "text-ink-soft hover:text-ink",
                )}
              >
                {draft.travel_mode === m && (
                  <motion.span
                    layoutId="travel-mode-pill"
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

        {touched && !canNext && (
          <p className="mt-3 text-[11px] font-semibold text-brand-600">
            Fill in every required field — including how many days and how many
            people — before choosing stops.
          </p>
        )}

        <motion.button
          type="submit"
          className="btn-primary mt-5 w-full"
          disabled={busy}
          whileTap={{ scale: 0.98 }}
        >
          Next: choose stops
          <ArrowRight className="h-4 w-4" />
        </motion.button>
      </form>
    </div>
  );
}

function FieldRow({
  icon,
  label,
  value,
  onChange,
  placeholder,
  invalid,
  disabled,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  invalid?: boolean;
  disabled?: boolean;
}) {
  return (
    <div>
      <span className="label">{label}</span>
      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2">{icon}</span>
        <input
          className={cn("input pl-9 pr-11", invalid && "ring-2 ring-brand-400")}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
      </div>
    </div>
  );
}
