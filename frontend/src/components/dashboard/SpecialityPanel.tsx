import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { UtensilsCrossed, Candy, CupSoda, Scissors, Sparkles, MapPin, Globe } from "lucide-react";

import type { Specialities, Speciality } from "@/types/api";
import { SectionHeader } from "@/components/common/SectionHeader";
import { cn } from "@/lib/cn";

const KIND: Record<Speciality["kind"], { label: string; icon: typeof Candy; tone: string }> = {
  food: { label: "Eat", icon: UtensilsCrossed, tone: "bg-brand-100 text-brand-700" },
  sweet: { label: "Sweet", icon: Candy, tone: "bg-bubble/15 text-bubble" },
  drink: { label: "Drink", icon: CupSoda, tone: "bg-teal-100 text-teal-700" },
  craft: { label: "Buy", icon: Scissors, tone: "bg-sunny/25 text-[#8A5A12]" },
  experience: { label: "Do", icon: Sparkles, tone: "bg-coral/15 text-coral" },
};

const ORDER: Speciality["kind"][] = ["food", "sweet", "drink", "craft", "experience"];

/** What the place is famous for: the rose milk, the silk saree, the houseboat.
 *  None of this is a map pin or an itinerary stop, and none of it comes out of
 *  OpenStreetMap, but it is often what the trip is remembered for. */
export function SpecialityPanel({ data }: { data?: Specialities }) {
  const items = data?.specialities ?? [];
  const [filter, setFilter] = useState<Speciality["kind"] | "all">("all");

  const kinds = useMemo(() => {
    const present = new Set(items.map((i) => i.kind));
    return ORDER.filter((k) => present.has(k));
  }, [items]);

  if (items.length === 0) return null;
  const shown = filter === "all" ? items : items.filter((i) => i.kind === filter);

  return (
    <div className="card card-hover p-5 sm:p-6">
      <SectionHeader
        emoji="✨"
        tone="coral"
        title={`What ${data?.destination ?? "this place"} is known for`}
        subtitle="Local specialities — worth the detour even if they are not on your list"
        right={
          data?.grounded ? (
            <span
              title="Checked against current web results, not just model memory"
              className="flex items-center gap-1 rounded-full border border-ink/10 bg-cream px-2 py-1 text-[10px] font-bold text-ink-soft"
            >
              <Globe className="h-3 w-3" /> Web-checked
            </span>
          ) : undefined
        }
      />

      {kinds.length > 1 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          <FilterChip label="All" active={filter === "all"} onClick={() => setFilter("all")} />
          {kinds.map((k) => (
            <FilterChip
              key={k}
              label={KIND[k].label}
              active={filter === k}
              onClick={() => setFilter(k)}
            />
          ))}
        </div>
      )}

      <div className="grid gap-2.5 sm:grid-cols-2">
        {shown.map((sp, i) => {
          const meta = KIND[sp.kind] ?? KIND.food;
          const Icon = meta.icon;
          return (
            <motion.div
              key={sp.name}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              className="rounded-2xl bg-cream p-3.5"
            >
              <div className="flex items-start gap-2">
                <span className={cn("grid h-7 w-7 shrink-0 place-items-center rounded-lg", meta.tone)}>
                  <Icon className="h-3.5 w-3.5" />
                </span>
                <div className="min-w-0">
                  <p className="font-display text-sm font-extrabold leading-snug text-ink">
                    {sp.name}
                  </p>
                  <p className="mt-0.5 text-xs leading-snug text-ink-soft">{sp.why}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {sp.where && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-paper px-2 py-0.5 text-[11px] font-bold text-ink-soft ring-1 ring-inset ring-ink/10">
                        <MapPin className="h-2.5 w-2.5" />
                        {sp.where}
                      </span>
                    )}
                    {sp.price_hint && (
                      <span className="rounded-full bg-paper px-2 py-0.5 text-[11px] font-bold text-ink-faint ring-1 ring-inset ring-ink/10">
                        {sp.price_hint}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

function FilterChip({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-full px-2.5 py-1 text-[11px] font-bold transition",
        active
          ? "bg-brand-500 text-white shadow-chunky-sm"
          : "bg-cream text-ink-soft ring-1 ring-inset ring-ink/10 hover:text-ink",
      )}
    >
      {label}
    </button>
  );
}
