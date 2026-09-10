import { motion } from "framer-motion";
import { ProfileMenu } from "@/components/ProfileMenu";

/** App header — a frosted rail with a slowly-drifting compass mark. */
export function TopBar({ right }: { right?: React.ReactNode }) {
  return (
    <header className="sticky top-0 z-40 border-b border-ink/[0.07] bg-cream/80 backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto flex h-[4.25rem] max-w-6xl items-center justify-between px-4 sm:px-6">
        <a href="/app" className="group flex items-center gap-2.5">
          <motion.span
            className="relative grid h-10 w-10 place-items-center overflow-hidden rounded-2xl bg-brand-gradient text-lg shadow-soft"
            whileHover={{ rotate: -10, scale: 1.06 }}
            transition={{ type: "spring", stiffness: 400, damping: 12 }}
          >
            <motion.span
              className="absolute inset-0 rounded-2xl bg-dawn opacity-0 transition-opacity duration-500 group-hover:opacity-70"
              aria-hidden
            />
            <span className="relative">🧭</span>
          </motion.span>
          <span className="font-display text-xl font-extrabold tracking-tight text-ink">
            Way<span className="gradient-text">farer</span>
          </span>
        </a>

        <div className="flex items-center gap-2 sm:gap-3">
          {right}
          <ProfileMenu />
        </div>
      </div>
    </header>
  );
}
