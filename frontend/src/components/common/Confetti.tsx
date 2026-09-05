import { useEffect, useState } from "react";
import { motion } from "framer-motion";

const COLORS = ["#FF6B4A", "#2DD4BF", "#FFC53D", "#7C5CFF", "#4CC9F0"];
const SHAPES = ["▲", "●", "■", "✦", "★"];

interface Piece {
  id: number;
  x: number;
  rot: number;
  delay: number;
  color: string;
  shape: string;
  drift: number;
}

/** One-shot celebratory burst. Bump `fireKey` to replay. */
export function Confetti({ fireKey }: { fireKey: number | string }) {
  const [pieces, setPieces] = useState<Piece[]>([]);

  useEffect(() => {
    if (!fireKey) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const next: Piece[] = Array.from({ length: 44 }).map((_, i) => ({
      id: i,
      x: Math.random() * 100,
      rot: Math.random() * 360,
      delay: Math.random() * 0.25,
      color: COLORS[i % COLORS.length],
      shape: SHAPES[i % SHAPES.length],
      drift: (Math.random() - 0.5) * 40,
    }));
    setPieces(next);
    const t = setTimeout(() => setPieces([]), 2600);
    return () => clearTimeout(t);
  }, [fireKey]);

  if (pieces.length === 0) return null;

  return (
    <div className="pointer-events-none fixed inset-0 z-[60] overflow-hidden" aria-hidden>
      {pieces.map((p) => (
        <motion.span
          key={p.id}
          className="absolute text-lg"
          style={{ left: `${p.x}%`, top: -20, color: p.color }}
          initial={{ y: -20, opacity: 1, rotate: p.rot }}
          animate={{ y: "108vh", x: p.drift, opacity: [1, 1, 0], rotate: p.rot + 540 }}
          transition={{ duration: 2.2, delay: p.delay, ease: "easeIn" }}
        >
          {p.shape}
        </motion.span>
      ))}
    </div>
  );
}
