import { motion } from "framer-motion";
import { Compass, TrainFront, Plane, BusFront } from "lucide-react";
import { AuthForm } from "@/components/auth/AuthForm";
import { Companion } from "@/components/decor/Companion";
import { Doodles } from "@/components/decor/Doodles";

export function WelcomePage() {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* left: brand / illustration */}
      <div className="relative hidden overflow-hidden bg-brand-gradient p-12 text-white lg:block">
        <div className="pointer-events-none absolute -left-16 top-24 h-72 w-72 rounded-blob bg-white/10 animate-float-slow" />
        <div className="pointer-events-none absolute -right-10 bottom-10 h-56 w-56 rounded-blob bg-black/10 animate-float-slow [animation-delay:-3s]" />

        <div className="relative z-10 flex h-full flex-col justify-between">
          <div className="flex items-center gap-2.5">
            <Compass className="h-7 w-7" />
            <span className="font-display text-xl font-bold">Wayfarer</span>
          </div>

          <div className="max-w-md">
            <Companion mood="wave" size={84} className="mb-4 text-white" />
            <h1 className="font-display text-5xl font-extrabold leading-[1.05]">
              Trips that
              <br />
              actually connect.
            </h1>
            <p className="mt-5 text-lg text-white/85">
              Tell us where you start and where you're going. We check real
              trains, buses and flights for your travel date — and tell you
              exactly why each one was picked.
            </p>
            <div className="mt-8 flex gap-3">
              {[TrainFront, BusFront, Plane].map((Icon, i) => (
                <motion.div
                  key={i}
                  className="grid h-12 w-12 place-items-center rounded-2xl bg-white/15 backdrop-blur"
                  animate={{ y: [0, -8, 0] }}
                  transition={{ duration: 3, repeat: Infinity, delay: i * 0.4 }}
                >
                  <Icon className="h-6 w-6" />
                </motion.div>
              ))}
            </div>
          </div>

          <p className="text-sm text-white/60">
            Built on OpenStreetMap · Indian Railways · live flight schedules
          </p>
        </div>
      </div>

      {/* right: real auth form */}
      <div className="relative grid place-items-center overflow-hidden bg-cream bg-mesh p-6 sm:p-8">
        <Doodles />
        <div className="relative z-10 w-full max-w-sm">
          <div className="mx-auto mb-6 grid h-14 w-14 place-items-center rounded-blob bg-brand-gradient text-white shadow-lift lg:hidden">
            <Compass className="h-7 w-7" />
          </div>
          <AuthForm />
        </div>
      </div>
    </div>
  );
}
