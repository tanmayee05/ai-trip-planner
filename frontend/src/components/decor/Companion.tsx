import { motion } from "framer-motion";
import { cn } from "@/lib/cn";

type Mood = "idle" | "wave" | "think" | "cheer" | "sleep";

interface Props {
  size?: number;
  mood?: Mood;
  className?: string;
}

/** "Pip" — the little paper-plane travel buddy. Blinks, bobs, and reacts. */
export function Companion({ size = 72, mood = "idle", className }: Props) {
  const sleeping = mood === "sleep";

  return (
    <motion.div
      className={cn("relative select-none", className)}
      style={{ width: size, height: size }}
      animate={
        mood === "cheer"
          ? { y: [0, -10, 0], rotate: [0, -6, 6, 0] }
          : { y: [0, -6, 0] }
      }
      transition={{ duration: mood === "cheer" ? 0.9 : 3, repeat: Infinity, ease: "easeInOut" }}
    >
      <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden>
        <defs>
          <linearGradient id="pip-body" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#A88DFF" />
            <stop offset="55%" stopColor="#6C4CF1" />
            <stop offset="100%" stopColor="#4728B8" />
          </linearGradient>
        </defs>

        {/* dashed vapour trail */}
        <path
          d="M6 78 Q 24 70 30 54"
          fill="none"
          stroke="#B57BFF"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray="2 8"
        />

        {/* paper-plane body */}
        <path
          d="M30 50 L82 20 L64 78 L52 58 Z"
          fill="url(#pip-body)"
          stroke="#241C46"
          strokeWidth="3"
          strokeLinejoin="round"
        />
        <path d="M52 58 L82 20" fill="none" stroke="#241C46" strokeWidth="2.5" opacity="0.5" />

        {/* face */}
        {sleeping ? (
          <>
            <path d="M58 44 q4 4 8 0" fill="none" stroke="#241C46" strokeWidth="3" strokeLinecap="round" />
            <path d="M68 44 q4 4 8 0" fill="none" stroke="#241C46" strokeWidth="3" strokeLinecap="round" />
            <text x="78" y="26" fontSize="12" fill="#241C46" fontWeight="700">z</text>
          </>
        ) : (
          <>
            <motion.g style={{ transformOrigin: "62px 45px" }} animate={{ scaleY: [1, 1, 0.1, 1] }} transition={{ duration: 3.4, repeat: Infinity, times: [0, 0.9, 0.94, 1] }}>
              <circle cx="62" cy="45" r="3.4" fill="#241C46" />
            </motion.g>
            <motion.g style={{ transformOrigin: "73px 42px" }} animate={{ scaleY: [1, 1, 0.1, 1] }} transition={{ duration: 3.4, repeat: Infinity, times: [0, 0.9, 0.94, 1] }}>
              <circle cx="73" cy="42" r="3.4" fill="#241C46" />
            </motion.g>
            <path
              d={mood === "cheer" ? "M60 52 q8 9 16 -2" : "M61 52 q7 5 13 -1"}
              fill="none"
              stroke="#241C46"
              strokeWidth="3"
              strokeLinecap="round"
            />
          </>
        )}
      </svg>

      {/* mood extras */}
      {mood === "cheer" && (
        <>
          {[
            { x: -6, y: 4, d: 0 },
            { x: 60, y: -4, d: 0.15 },
            { x: 30, y: -14, d: 0.3 },
          ].map((s, i) => (
            <motion.span
              key={i}
              className="absolute text-sunny"
              style={{ left: s.x, top: s.y }}
              animate={{ scale: [0, 1, 0], rotate: [0, 90, 180] }}
              transition={{ duration: 1, repeat: Infinity, delay: s.d }}
            >
              ✦
            </motion.span>
          ))}
        </>
      )}
      {mood === "think" && (
        <motion.span
          className="absolute -right-1 -top-1 rounded-full bg-paper px-1.5 py-0.5 text-[10px] shadow-soft"
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.4, repeat: Infinity }}
        >
          …
        </motion.span>
      )}
      {mood === "wave" && (
        <motion.span
          className="absolute -left-2 top-2 text-base"
          animate={{ rotate: [0, 18, -6, 18, 0] }}
          transition={{ duration: 1.4, repeat: Infinity, repeatDelay: 1 }}
        >
          👋
        </motion.span>
      )}
    </motion.div>
  );
}
