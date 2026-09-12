import { UtensilsCrossed, BedDouble, MapPin } from "lucide-react";

import type { ItineraryStayFood } from "@/types/api";
import { SectionHeader } from "@/components/common/SectionHeader";

const BAND_LABEL: Record<string, string> = {
  budget: "Budget",
  mid: "Mid-range",
  premium: "Premium",
};

interface Props {
  stays: ItineraryStayFood[];
}

/** Where to eat and where to stay each night of the itinerary — works the
 *  same whether the traveller drove, flew, or took a train, since it's
 *  about the destination side, not how they got there. */
export function ItineraryStaysPanel({ stays }: Props) {
  if (stays.length === 0) return null;

  return (
    <div className="card p-5 sm:p-6">
      <SectionHeader
        emoji="🛏️"
        title="Food & stay along the way"
        subtitle={(() => {
          const nights = stays.filter((s) => s.needs_hotel !== false).length;
          const d = `${stays.length} day${stays.length === 1 ? "" : "s"}`;
          return nights
            ? `Food for all ${d}, and a bed for ${nights} night${nights === 1 ? "" : "s"}`
            : `Food for all ${d}`;
        })()}
        tone="coral"
      />

      <div className="space-y-4">
        {stays.map((s) => (
          <div key={s.day} className="rounded-2xl border border-ink/10 bg-cream/50 p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-bubble text-[10px] font-extrabold text-white">
                {s.day}
              </span>
              <p className="flex flex-wrap items-center gap-1.5 text-xs font-bold text-ink">
                <MapPin className="h-3.5 w-3.5 shrink-0 text-bubble" />
                {s.needs_hotel === false
                  ? `Day ${s.day} (last day) · near ${s.anchor}`
                  : `Day ${s.day}, night nearby · near ${s.anchor}`}
                {s.travel_day && (
                  <span className="rounded-full bg-ink/[0.06] px-2 py-0.5 text-[10px] font-bold text-ink-soft">
                    travel day
                  </span>
                )}
              </p>
            </div>

            {/* A night we never got to look up is not a night with nothing
                near it — say which one this is. */}
            {s.skipped ? (
              <p className="rounded-xl bg-ink/[0.04] px-3 py-2 text-xs text-ink-soft ring-1 ring-inset ring-ink/10">
                Food and stay suggestions for this day weren't fetched — the
                lookup ran out of time. Ask in the chat and I'll pull them up.
              </p>
            ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="mb-1.5 flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-wide text-ink-faint">
                  <UtensilsCrossed className="h-3.5 w-3.5" /> Food nearby
                </p>
                {s.food.length === 0 ? (
                  <p className="text-xs text-ink-faint">No suggestions found.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {s.food.map((p) => (
                      <li key={p.name} className="rounded-xl bg-paper/70 px-3 py-2">
                        <p className="text-sm font-semibold text-ink">{p.name}</p>
                        <p className="text-[11px] text-ink-faint">
                          {p.kind} · {p.where}
                          {p.approx && " (approx)"}
                        </p>
                        {p.why && <p className="mt-0.5 text-[11px] text-ink-soft">{p.why}</p>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <p className="mb-1.5 flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-wide text-ink-faint">
                  <BedDouble className="h-3.5 w-3.5" /> Places to stay
                </p>
                {s.needs_hotel === false ? (
                  <p className="text-xs text-ink-faint">
                    You head home this day — no room needed.
                  </p>
                ) : s.stay.length === 0 ? (
                  <p className="text-xs text-ink-faint">No suggestions found.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {s.stay.map((h) => (
                      <li key={h.name} className="rounded-xl bg-paper/70 px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-ink">{h.name}</p>
                          <span className="shrink-0 text-[10px] font-bold text-brand-600">
                            {BAND_LABEL[h.band] ?? h.band}
                          </span>
                        </div>
                        <p className="text-[11px] text-ink-faint">
                          {h.where}
                          {h.approx && " (approx)"} · {h.price_hint}
                        </p>
                        {h.why && <p className="mt-0.5 text-[11px] text-ink-soft">{h.why}</p>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            )}
          </div>
        ))}
      </div>

      <p className="mt-3 text-[10px] leading-snug text-ink-faint">
        AI suggestions with rough price bands — confirm hours and rates before you rely on them.
      </p>
    </div>
  );
}
