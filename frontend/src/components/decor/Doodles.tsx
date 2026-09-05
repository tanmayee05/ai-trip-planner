import { useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/cn";

/** Ambient aurora background — morphing gradient blobs, twinkling stars and
 *  the odd shooting star. Decorative only; never intercepts pointer events. */
export function Doodles({ className }: { className?: string }) {
  const stars = useMemo(
    () =>
      Array.from({ length: 22 }).map(() => ({
        left: Math.random() * 100,
        top: Math.random() * 100,
        size: 3 + Math.random() * 5,
        delay: Math.random() * 4,
        dur: 2.6 + Math.random() * 3,
        pink: Math.random() > 0.6,
      })),
    [],
  );

  return (
    <div className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)} aria-hidden>
      {/* ---- aurora blobs ---- */}
      <div className="absolute -left-32 -top-32 h-[30rem] w-[30rem] rounded-blob bg-brand-400/40 blur-[110px] animate-blob-morph" />
      <div className="absolute -right-40 top-6 h-[26rem] w-[26rem] rounded-blob bg-bubble/35 blur-[110px] animate-blob-morph [animation-delay:-6s] [animation-duration:24s]" />
      <div className="absolute -bottom-44 left-1/4 h-[28rem] w-[28rem] rounded-blob bg-teal-500/30 blur-[120px] animate-blob-morph [animation-delay:-13s] [animation-duration:28s]" />
      <div className="absolute bottom-8 right-1/4 h-[18rem] w-[18rem] rounded-blob bg-sunny/30 blur-[90px] animate-blob-morph [animation-delay:-3s] [animation-duration:19s]" />

      {/* ---- twinkling stars ---- */}
      {stars.map((s, i) => (
        <span
          key={i}
          className={cn(
            "absolute rounded-full animate-twinkle",
            s.pink ? "bg-bubble" : "bg-white",
          )}
          style={{
            left: `${s.left}%`,
            top: `${s.top}%`,
            width: s.size,
            height: s.size,
            animationDelay: `${s.delay}s`,
            animationDuration: `${s.dur}s`,
            boxShadow: "0 0 8px currentColor",
          }}
        />
      ))}

      {/* ---- shooting stars ---- */}
      {[
        { top: "12%", left: "70%", delay: 2, gap: 11 },
        { top: "58%", left: "40%", delay: 7, gap: 15 },
      ].map((s, i) => (
        <motion.span
          key={i}
          className="absolute h-[2px] w-24 rounded-full bg-gradient-to-r from-transparent via-white to-transparent"
          style={{ top: s.top, left: s.left }}
          initial={{ x: 0, y: 0, opacity: 0 }}
          animate={{ x: -260, y: 150, opacity: [0, 1, 0] }}
          transition={{ duration: 1.1, repeat: Infinity, repeatDelay: s.gap, delay: s.delay, ease: "easeIn" }}
        />
      ))}

      {/* ---- grounding: outlined peaks bottom-right ---- */}
      <svg className="absolute -bottom-3 right-4 h-28 w-60 opacity-50" viewBox="0 0 220 100">
        <path d="M0 100 L60 22 L104 100 Z" fill="#5B8DEF" stroke="#241C46" strokeWidth="3" strokeOpacity=".25" />
        <path d="M76 100 L142 10 L206 100 Z" fill="#B57BFF" stroke="#241C46" strokeWidth="3" strokeOpacity=".25" />
        <path d="M132 24 l10 -8 10 8 -10 8 z" fill="#F4F1FF" />
      </svg>

      {/* ---- slow compass, top-right ---- */}
      <motion.svg
        className="absolute right-8 top-8 h-16 w-16 opacity-45"
        viewBox="0 0 64 64"
        animate={{ rotate: [0, 16, -12, 0] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
      >
        <circle cx="32" cy="32" r="26" fill="none" stroke="#6C4CF1" strokeWidth="5" />
        <path d="M32 10 L40 32 L32 54 L24 32 Z" fill="#FF5C8A" />
      </motion.svg>
    </div>
  );
}
