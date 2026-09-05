import { motion } from "framer-motion";
import { ProfileMenu } from "@/components/ProfileMenu";

/** App header — a chunky, colourful bar. */
export function TopBar({ right }: { right?: React.ReactNode }) {
  return (
    <header className="sticky top-0 z-40 border-b-2 border-ink/10 bg-cream/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-2.5">
          <motion.span
            className="grid h-10 w-10 place-items-center rounded-2xl border-2 border-ink bg-brand-500 text-lg shadow-[0_4px_0_0_theme('colors.ink.DEFAULT')]"
            whileHover={{ rotate: -8, scale: 1.05 }}
            transition={{ type: "spring", stiffness: 400, damping: 12 }}
          >
            🧭
          </motion.span>
          <span className="font-display text-xl font-extrabold tracking-tight">
            Way<span className="text-brand-500">farer</span>
          </span>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          {right}
          <ProfileMenu />
        </div>
      </div>
    </header>
  );
}
