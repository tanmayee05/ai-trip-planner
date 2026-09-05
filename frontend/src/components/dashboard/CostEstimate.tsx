import { motion } from "framer-motion";
import { Fuel, UtensilsCrossed, BedDouble, Wallet } from "lucide-react";

import type { CostBreakdown } from "@/types/api";
import { Counter } from "@/components/common/Counter";
import { SectionHeader } from "@/components/common/SectionHeader";

const ICONS: Record<string, typeof Fuel> = {
  Fuel: Fuel,
  "Fuel (round trip)": Fuel,
  Food: UtensilsCrossed,
  Stay: BedDouble,
};

export function CostEstimate({ costs }: { costs: CostBreakdown }) {
  return (
    <div className="card card-hover card-sunny p-5 sm:p-6">
      <SectionHeader
        emoji="💰"
        tone="sunny"
        title="Rough cost"
        subtitle={`for ${costs.assumptions.people} ${costs.assumptions.people > 1 ? "people" : "person"} · ${costs.assumptions.days} ${costs.assumptions.days > 1 ? "days" : "day"}`}
      />

      <ul className="mt-1 space-y-2">
        {costs.items.map((it, i) => {
          const Icon = ICONS[it.label] ?? Wallet;
          return (
            <motion.li
              key={it.label}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05 }}
              className="flex items-center justify-between rounded-xl bg-cream px-3 py-2.5"
            >
              <span className="flex items-center gap-2 text-sm">
                <Icon className="h-4 w-4 text-ink-soft" />
                <span className="font-medium text-ink">{it.label}</span>
              </span>
              <span className="text-right">
                <Counter
                  value={it.amount}
                  prefix="₹"
                  className="font-display text-sm font-bold text-ink"
                />
                <span className="block text-[10px] text-ink-faint">{it.note}</span>
              </span>
            </motion.li>
          );
        })}
      </ul>

      <motion.div
        className="mt-3 flex items-center justify-between rounded-xl bg-brand-50 px-3 py-3"
        initial={{ scale: 0.97 }}
        animate={{ scale: 1 }}
      >
        <span className="text-sm font-semibold text-brand-700">Estimated total</span>
        <Counter
          value={costs.total}
          prefix="₹"
          duration={1100}
          className="font-display text-lg font-extrabold text-brand-700"
        />
      </motion.div>

      <p className="mt-2 text-[11px] leading-snug text-ink-faint">{costs.note}</p>
    </div>
  );
}
