import { cn } from "@/lib/cn";

interface Props {
  emoji: string;
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  tone?: "brand" | "teal" | "sunny" | "sky" | "grape";
  className?: string;
}

const TONE: Record<NonNullable<Props["tone"]>, string> = {
  brand: "bg-brand-100 text-brand-700",
  teal: "bg-teal-100 text-teal-700",
  sunny: "bg-sunny/25 text-[#8a5a00]",
  sky: "bg-sky/20 text-[#2E4FA8]",
  grape: "bg-grape/15 text-grape",
};

/** Big playful emoji blob + bold title. */
export function SectionHeader({ emoji, title, subtitle, right, tone = "brand", className }: Props) {
  return (
    <div className={cn("mb-4 flex items-start justify-between gap-3", className)}>
      <div className="flex items-start gap-3">
        <span className={cn("blob-chip hover-wiggle border-ink/10", TONE[tone])}>{emoji}</span>
        <div className="pt-0.5">
          <h2 className="font-display text-xl font-extrabold leading-none">{title}</h2>
          {subtitle && <p className="mt-1 text-xs font-medium text-ink-faint">{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  );
}
