import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TrainFront, BusFront, Plane, Car, MapPin } from "lucide-react";
import { Companion } from "@/components/decor/Companion";

interface Props {
  source: string;
  destination: string;
  elapsedMs: number;
}

const STEPS = [
  "Pinning your places on the map…",
  "Scouting nearby stations, stands & airports…",
  "Checking trains for your date…",
  "Checking flights for your date…",
  "Working out the smartest route…",
  "Almost there — tidying up the plan…",
];

const VEHICLES = [Car, BusFront, TrainFront, Plane];
const LANDMARKS = ["🌴", "⛰️", "🏛️", "🏖️", "🕌", "🌊"];

export function PlanningProgress({ source, destination, elapsedMs }: Props) {
  const secs = Math.floor(elapsedMs / 1000);
  const stepIdx = Math.min(Math.floor(secs / 7), STEPS.length - 1);
  const Vehicle = VEHICLES[Math.floor(secs / 4) % VEHICLES.length];
  const [dots, setDots] = useState("");

  useEffect(() => {
    const t = setInterval(() => setDots((d) => (d.length >= 3 ? "" : d + ".")), 420);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="card overflow-hidden p-6 text-center sm:p-8">
      <Companion mood="think" size={72} className="mx-auto" />

      <p className="mt-3 flex items-center justify-center gap-2 font-display text-xl font-extrabold">
        <MapPin className="h-4 w-4 text-brand-500" />
        <span className="max-w-[8rem] truncate">{source}</span>
        <span className="text-ink-faint">→</span>
        <span className="max-w-[8rem] truncate">{destination}</span>
      </p>

      {/* the little journey track */}
      <div className="relative mx-auto mt-6 h-12 max-w-sm">
        <div className="absolute left-0 right-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-ink/5" />
        <div
          className="absolute left-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-brand-gradient"
          style={{ width: `${Math.min(95, 12 + secs * 3)}%`, transition: "width 1s linear" }}
        />
        {/* passing landmarks */}
        {LANDMARKS.map((l, i) => (
          <span
            key={i}
            className="absolute top-0 text-sm"
            style={{ left: `${10 + i * 15}%` }}
          >
            {l}
          </span>
        ))}
        {/* the traveller */}
        <motion.div
          className="absolute top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full bg-paper text-brand-600 shadow-lift"
          animate={{ left: `${Math.min(88, 4 + secs * 3)}%`, rotate: [0, -6, 6, 0] }}
          transition={{ left: { duration: 1, ease: "linear" }, rotate: { duration: 0.8, repeat: Infinity } }}
        >
          <Vehicle className="h-5 w-5" />
        </motion.div>
      </div>

      <p className="mt-5 text-sm font-medium text-ink-soft">
        {STEPS[stepIdx]}
        {dots}
      </p>

      <p className="mt-3 text-xs text-ink-faint">
        {secs}s · first look at a new region can take a couple of minutes (free map
        data is rate-limited) — instant after that.
      </p>
    </div>
  );
}
