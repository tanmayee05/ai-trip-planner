import { useMemo } from "react";
import { motion } from "framer-motion";
import {
  Mountain,
  Waves,
  Umbrella,
  Bird,
  Landmark,
  Building2,
  Castle,
  Droplets,
  MapPin,
  Pencil,
  Sparkles,
  Car,
  Coffee,
} from "lucide-react";

import type { ItineraryNote, ItineraryStop } from "@/types/api";
import { SectionHeader } from "@/components/common/SectionHeader";

const CAT_ICON: Record<string, typeof Mountain> = {
  "hill station": Mountain,
  backwater: Waves,
  beach: Umbrella,
  wildlife: Bird,
  heritage: Landmark,
  city: Building2,
  temple: Landmark,
  fort: Castle,
  waterfall: Droplets,
  lake: Waves,
  other: MapPin,
};

interface Props {
  itinerary: ItineraryStop[];
  notes?: ItineraryNote[];
  onEdit: () => void;
}

export function ItineraryPanel({ itinerary, notes = [], onEdit }: Props) {
  const byDay = useMemo(() => {
    const m = new Map<number, ItineraryStop[]>();
    // Seed from the NOTES as well as the stops. A long haul legitimately has a
    // day with no sightseeing on it — getting there is the day's work — and
    // the planner writes a rationale saying so. Building this map from stops
    // alone made that day vanish from the list entirely, so the trip appeared
    // to start on Day 2 with no explanation.
    for (const n of notes) if (!m.has(n.day)) m.set(n.day, []);
    for (const s of itinerary) {
      if (!m.has(s.day)) m.set(s.day, []);
      m.get(s.day)!.push(s);
    }
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  }, [itinerary, notes]);

  // A blank day means different things at different points in the trip: on day
  // one you're travelling in, after the last sight you're free or heading home.
  const lastDayWithStops = useMemo(
    () => itinerary.reduce((max, s) => Math.max(max, s.day), 0),
    [itinerary],
  );

  const rationaleFor = useMemo(() => {
    const m = new Map<number, string>();
    for (const n of notes) m.set(n.day, n.rationale);
    return m;
  }, [notes]);

  if (itinerary.length === 0) return null;

  return (
    <div className="card card-hover card-teal p-5 sm:p-6">
      <SectionHeader
        emoji="🗺️"
        tone="teal"
        title="Your itinerary"
        subtitle={`${itinerary.length} stop${itinerary.length > 1 ? "s" : ""}, in travel order`}
        right={
          <button onClick={onEdit} className="btn-ghost !px-3 text-xs">
            <Pencil className="h-3.5 w-3.5" /> Edit places
          </button>
        }
      />

      <ol className="relative space-y-4 border-l-2 border-dashed border-brand-200 pl-5">
        {byDay.map(([day, stops], di) => (
          <motion.li
            key={day}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: di * 0.06 }}
            className="relative"
          >
            <span className="absolute -left-[27px] grid h-5 w-5 place-items-center rounded-full bg-brand-500 text-[10px] font-bold text-white ring-4 ring-cream">
              {day}
            </span>
            <p className="text-[11px] font-bold uppercase tracking-wide text-brand-600">
              Day {day}
            </p>
            {rationaleFor.get(day) && (
              <p className="mt-1 flex gap-1.5 rounded-lg bg-brand-50 px-2.5 py-1.5 text-[11px] leading-snug text-brand-700">
                <Sparkles className="mt-0.5 h-3 w-3 shrink-0" />
                {rationaleFor.get(day)}
              </p>
            )}
            {stops.length === 0 &&
              (day === 1 ? (
                <p className="mt-1.5 flex items-center gap-1.5 rounded-xl bg-cream px-3 py-2.5 text-xs font-semibold text-ink-soft">
                  <Car className="h-4 w-4 shrink-0 text-ink-faint" />
                  On the road — getting there is the day
                </p>
              ) : day > lastDayWithStops ? (
                <p className="mt-1.5 flex items-center gap-1.5 rounded-xl bg-cream px-3 py-2.5 text-xs font-semibold text-ink-soft">
                  <Coffee className="h-4 w-4 shrink-0 text-ink-faint" />
                  Free day — nothing scheduled, so take it slow or head back early
                </p>
              ) : (
                <p className="mt-1.5 flex items-center gap-1.5 rounded-xl bg-cream px-3 py-2.5 text-xs font-semibold text-ink-soft">
                  <Coffee className="h-4 w-4 shrink-0 text-ink-faint" />
                  Nothing scheduled for this day
                </p>
              ))}
            <div className="mt-1.5 space-y-2">
              {stops.map((s) => {
                const Icon = CAT_ICON[s.category ?? "other"] ?? MapPin;
                return (
                  <div key={s.name} className="rounded-xl bg-cream p-3">
                    <div className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                      <Icon className="h-4 w-4 text-brand-500" />
                      {s.name}
                    </div>
                    {s.blurb && (
                      <p className="mt-0.5 text-xs leading-snug text-ink-soft">{s.blurb}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </motion.li>
        ))}
      </ol>
    </div>
  );
}
