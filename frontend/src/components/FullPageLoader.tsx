import { motion } from "framer-motion";

/** Centered brand spinner for route-level waits. */
export function FullPageLoader({ label }: { label?: string }) {
  return (
    <div className="grid min-h-screen place-items-center bg-cream bg-mesh">
      <div className="flex flex-col items-center gap-4">
        <motion.div
          className="h-14 w-14 rounded-blob bg-brand-gradient shadow-lift"
          animate={{ rotate: 360, borderRadius: ["42% 58% 63% 37% / 41% 44% 56% 59%", "58% 42% 37% 63% / 56% 59% 41% 44%", "42% 58% 63% 37% / 41% 44% 56% 59%"] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        />
        {label && <p className="text-sm font-medium text-ink-soft">{label}</p>}
      </div>
    </div>
  );
}
