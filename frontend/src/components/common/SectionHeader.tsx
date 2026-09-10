import { motion } from "framer-motion";
import { cn } from "@/lib/cn";

interface Props {
  emoji: string;
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  tone?: "brand" | "teal" | "sunny" | "sky" | "grape" | "coral";
  className?: string;
}

const TONE: Record<NonNullable<Props["tone"]>, { chip: string; rule: string }> = {
  brand: { chip: "bg-brand-100 text-brand-700", rule: "from-brand-500" },
  teal: { chip: "bg-teal-100 text-teal-700", rule: "from-teal-500" },
  sunny: { chip: "bg-sunny/20 text-[#8A5A12]", rule: "from-sunny" },
  sky: { chip: "bg-sky/20 text-brand-700", rule: "from-sky" },
  grape: { chip: "bg-grape/15 text-grape", rule: "from-grape" },
  coral: { chip: "bg-bubble/15 text-bubble", rule: "from-bubble" },
};

/** Icon medallion + title, with a short gradient rule that draws itself in. */
export function SectionHeader({ emoji, title, subtitle, right, tone = "brand", className }: Props) {
  const t = TONE[tone];
  return (
    <div className={cn("mb-4 flex items-start justify-between gap-3", className)}>
      <div className="flex items-start gap-3">
        <span className={cn("blob-chip hover-wiggle", t.chip)}>{emoji}</span>
        <div className="pt-0.5">
          <h2 className="font-display text-xl font-extrabold leading-none tracking-tight">
            {title}
          </h2>
          <motion.span
            className={cn("mt-1.5 block h-[3px] rounded-full bg-gradient-to-r to-transparent", t.rule)}
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 44, opacity: 1 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 0.1 }}
          />
          {subtitle && (
            <p className="mt-1.5 text-xs font-medium leading-snug text-ink-faint">{subtitle}</p>
          )}
        </div>
      </div>
      {right}
    </div>
  );
}
