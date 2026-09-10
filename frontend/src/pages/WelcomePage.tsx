import { motion } from "framer-motion";
import { Compass, TrainFront, Plane, BusFront } from "lucide-react";
import { AuthForm } from "@/components/auth/AuthForm";
import { Companion } from "@/components/decor/Companion";
import { Doodles } from "@/components/decor/Doodles";

export function WelcomePage() {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* left: brand / illustration — a night-flight sky */}
      <div className="relative hidden overflow-hidden bg-dusk p-12 text-white lg:block">
        <div
          className="absolute inset-0 animate-gradient-pan bg-dusk"
          style={{ backgroundSize: "220% 220%" }}
          aria-hidden
        />
        <div className="contours pointer-events-none absolute inset-0 opacity-60" aria-hidden />

        {/* golden horizon glow */}
        <div
          className="pointer-events-none absolute inset-x-0 bottom-0 h-64"
          style={{
            background:
              "radial-gradient(120% 80% at 50% 130%, rgba(232,163,61,0.45), rgba(244,120,79,0.18) 45%, transparent 70%)",
          }}
          aria-hidden
        />
        <div className="pointer-events-none absolute -left-16 top-24 h-72 w-72 rounded-blob bg-teal-500/20 blur-3xl animate-float-slow" />
        <div className="pointer-events-none absolute -right-10 bottom-10 h-56 w-56 rounded-blob bg-bubble/20 blur-3xl animate-float-slow [animation-delay:-3s]" />

        {/* dotted flight arc */}
        <svg
          className="pointer-events-none absolute right-0 top-1/3 h-48 w-full opacity-50"
          viewBox="0 0 400 160"
          fill="none"
          aria-hidden
        >
          <path
            d="M-10 148 C 90 140, 170 74, 240 40 S 370 6, 410 18"
            stroke="white"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray="6 12"
            className="animate-dash-flow"
          />
        </svg>

        <div className="relative z-10 flex h-full flex-col justify-between">
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/15 backdrop-blur">
              <Compass className="h-5 w-5 animate-spin-slow" />
            </span>
            <span className="font-display text-xl font-bold tracking-tight">Wayfarer</span>
          </div>

          <div className="max-w-md">
            <Companion mood="wave" size={84} className="mb-4 text-white" />
            <p className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-white/60">
              Plan · Connect · Go
            </p>
            <h1 className="mt-3 font-display text-5xl font-extrabold leading-[1.05]">
              Trips that
              <br />
              actually connect.
            </h1>
            <p className="mt-5 text-lg leading-relaxed text-white/85">
              Tell us where you start and where you're going. We check real
              trains, buses and flights for your travel date — and tell you
              exactly why each one was picked.
            </p>
            <div className="mt-8 flex gap-3">
              {[TrainFront, BusFront, Plane].map((Icon, i) => (
                <motion.div
                  key={i}
                  className="grid h-12 w-12 place-items-center rounded-2xl border border-white/20 bg-white/12 backdrop-blur-md"
                  animate={{ y: [0, -8, 0] }}
                  transition={{ duration: 3, repeat: Infinity, delay: i * 0.4 }}
                >
                  <Icon className="h-6 w-6" />
                </motion.div>
              ))}
            </div>
          </div>

          <p className="text-sm text-white/55">
            Built on OpenStreetMap · Indian Railways · live flight schedules
          </p>
        </div>
      </div>

      {/* right: real auth form */}
      <div className="relative grid place-items-center overflow-hidden bg-cream bg-mesh p-6 sm:p-8">
        <Doodles />
        <div className="relative z-10 w-full max-w-sm">
          <div className="mx-auto mb-6 grid h-14 w-14 place-items-center rounded-2xl bg-brand-gradient text-white shadow-lift lg:hidden">
            <Compass className="h-7 w-7" />
          </div>
          <AuthForm />
        </div>
      </div>
    </div>
  );
}
