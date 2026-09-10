import { useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/cn";

/** Ambient travel backdrop — golden-hour washes, drifting cloud banks, a
 *  compass rose and a plane tracing its dotted route. Decorative only;
 *  never intercepts pointer events. */
export function Doodles({ className }: { className?: string }) {
  const stars = useMemo(
    () =>
      Array.from({ length: 16 }).map(() => ({
        left: Math.random() * 100,
        top: Math.random() * 62,
        size: 2 + Math.random() * 3,
        delay: Math.random() * 4,
        dur: 3 + Math.random() * 3,
        gold: Math.random() > 0.5,
      })),
    [],
  );

  return (
    <div
      className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}
      aria-hidden
    >
      {/* ---- golden-hour washes ---- */}
      <div className="absolute -left-40 -top-40 h-[34rem] w-[34rem] rounded-blob bg-brand-400/25 blur-[130px] animate-blob-morph" />
      <div className="absolute -right-44 top-10 h-[28rem] w-[28rem] rounded-blob bg-bubble/20 blur-[120px] animate-blob-morph [animation-delay:-7s] [animation-duration:26s]" />
      <div className="absolute -bottom-48 left-1/4 h-[30rem] w-[30rem] rounded-blob bg-teal-500/20 blur-[130px] animate-blob-morph [animation-delay:-14s] [animation-duration:30s]" />
      <div className="absolute bottom-12 right-1/4 h-[20rem] w-[20rem] rounded-blob bg-sunny/22 blur-[100px] animate-blob-morph [animation-delay:-4s] [animation-duration:21s]" />

      {/* ---- drifting cloud banks ---- */}
      {[
        { top: "14%", scale: 1, opacity: 0.5, dur: "58s", delay: "0s" },
        { top: "34%", scale: 0.7, opacity: 0.35, dur: "76s", delay: "-24s" },
        { top: "62%", scale: 1.25, opacity: 0.28, dur: "94s", delay: "-52s" },
      ].map((c, i) => (
        <svg
          key={i}
          className="absolute left-0 h-16 w-52 animate-drift text-white"
          viewBox="0 0 200 60"
          style={{
            top: c.top,
            opacity: c.opacity,
            transform: `scale(${c.scale})`,
            animationDuration: c.dur,
            animationDelay: c.delay,
          }}
        >
          <ellipse cx="60" cy="38" rx="42" ry="20" fill="currentColor" />
          <ellipse cx="104" cy="30" rx="34" ry="24" fill="currentColor" />
          <ellipse cx="140" cy="40" rx="30" ry="16" fill="currentColor" />
        </svg>
      ))}

      {/* ---- faint stars, high up ---- */}
      {stars.map((s, i) => (
        <span
          key={i}
          className={cn("absolute rounded-full animate-twinkle", s.gold ? "bg-sunny" : "bg-white")}
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

      {/* ---- a plane tracing its route ---- */}
      <svg
        className="absolute right-[6%] top-[18%] h-40 w-80 opacity-45"
        viewBox="0 0 300 140"
        fill="none"
      >
        <path
          d="M6 128 C 70 122, 118 76, 160 44 S 258 8, 292 14"
          stroke="#2176AE"
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray="6 10"
          className="animate-dash-flow"
          opacity="0.55"
        />
        <motion.g
          animate={{ x: [0, 6, 0], y: [0, -4, 0] }}
          transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
        >
          <path
            d="M286 6 l14 8 -14 8 3.5 -8 z"
            fill="#F4784F"
            transform="rotate(-6 293 14)"
          />
        </motion.g>
      </svg>

      {/* ---- ridgeline, bottom right ---- */}
      <svg className="absolute -bottom-2 right-4 h-32 w-72 opacity-45" viewBox="0 0 240 110">
        <path d="M0 110 L64 24 L112 110 Z" fill="#2176AE" fillOpacity=".55" />
        <path d="M82 110 L152 8 L222 110 Z" fill="#2EC4B6" fillOpacity=".5" />
        <path d="M142 22 l10 -9 10 9 -10 8 z" fill="#F6F2EB" />
      </svg>

      {/* ---- compass rose, top right ---- */}
      <svg className="absolute right-8 top-8 h-20 w-20 opacity-30" viewBox="0 0 64 64">
        <g className="animate-spin-slow" style={{ transformOrigin: "32px 32px" }}>
          <circle cx="32" cy="32" r="27" fill="none" stroke="#2176AE" strokeWidth="1.5" />
          <circle cx="32" cy="32" r="20" fill="none" stroke="#2176AE" strokeWidth="1" strokeDasharray="3 5" />
          <path d="M32 8 L37 32 L32 56 L27 32 Z" fill="#F4784F" />
          <path d="M8 32 L32 27 L56 32 L32 37 Z" fill="#0E1B2C" fillOpacity=".35" />
        </g>
      </svg>
    </div>
  );
}
