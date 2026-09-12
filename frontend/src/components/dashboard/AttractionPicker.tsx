import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Mountain,
  Waves,
  Umbrella,
  Bird,
  Landmark,
  Building2,
  Castle,
  Droplets,
  MapPin,
  Check,
  ArrowLeft,
  Wand2,
  RotateCcw,
  Loader2,
} from "lucide-react";

import { fetchAttractions } from "@/api/attractions";
import type { PlanStop } from "@/api/plan";
import type { Attraction } from "@/types/api";
import { apiErrorMessage } from "@/lib/api";
import { Companion } from "@/components/decor/Companion";
import { cn } from "@/lib/cn";

const CAT_ICON: Record<string, typeof Mountain> = {
  "hill station": Mountain,
  backwater: Waves,
  beach: Umbrella,
  wildlife: Bird,
  heritage: Landmark,
  city: Building2,
  temple: Landmark,
  fort: Castle,
  waterfall: Droplets,
  lake: Waves,
  other: MapPin,
};

const CAT_TONE: Record<string, string> = {
  "hill station": "bg-lime/20 text-[#146B52]",
  backwater: "bg-teal-100 text-teal-700",
  beach: "bg-sky/20 text-[#12486D]",
  wildlife: "bg-lime/20 text-[#146B52]",
  heritage: "bg-sunny/25 text-[#8A5A12]",
  city: "bg-grape/15 text-grape",
  temple: "bg-bubble/15 text-bubble",
  fort: "bg-sunny/25 text-[#8A5A12]",
  waterfall: "bg-sky/20 text-[#12486D]",
  lake: "bg-teal-100 text-teal-700",
  other: "bg-brand-100 text-brand-700",
};

interface Props {
  destination: string;
  initialSelected?: string[];
  onPlan: (stops: PlanStop[]) => void;
  onBack: () => void;
  /** a plan is being checked or started — stops a second click firing twice */
  busy?: boolean;
}

export function AttractionPicker({
  destination, initialSelected = [], onPlan, onBack, busy = false,
}: Props) {
  const q = useQuery({
    queryKey: ["attractions", destination.trim().toLowerCase()],
    queryFn: () => fetchAttractions(destination),
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });

  const [selected, setSelected] = useState<Set<string>>(new Set(initialSelected));
  const [cat, setCat] = useState<string>("all");

  const places = q.data?.places ?? [];
  // the backend echoes back the RESOLVED destination, which can differ from
  // what was typed when it recovered from a misspelling
  const shownName = q.data?.destination || destination;

  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of places) counts.set(p.category, (counts.get(p.category) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [places]);

  const shown = cat === "all" ? places : places.filter((p) => p.category === cat);

  // nearby places grouped by their town/district, nearest group first
  const nearbyByTown = useMemo(() => {
    const groups = new Map<string, Attraction[]>();
    for (const p of shown) {
      if (p.scope !== "nearby") continue;
      const key = p.town || "Nearby";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(p);
    }
    return [...groups.entries()].sort(
      (a, b) => (a[1][0].distance_km ?? 0) - (b[1][0].distance_km ?? 0),
    );
  }, [shown]);

  function toggle(name: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  function submit() {
    const stops: PlanStop[] = places
      .filter((p) => selected.has(p.name))
      .map((p) => ({
        name: p.name,
        lat: p.lat,
        lon: p.lon,
        category: p.category,
        blurb: p.blurb,
      }));
    onPlan(stops);
  }

  return (
    <div className="card flex max-h-[calc(100vh-8rem)] flex-col p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="blob-chip bg-teal-100 text-teal-700">📍</span>
          <div className="pt-0.5">
            <h2 className="font-display text-xl font-extrabold leading-none">Choose your stops</h2>
            <p className="mt-1 text-xs font-medium text-ink-faint">
              Popular places in {shownName}. Pick the ones you want to visit.
            </p>
          </div>
        </div>
        <button onClick={onBack} className="btn-ghost !px-2 !py-1 text-xs">
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </button>
      </div>

      {/* category filter */}
      {categories.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          <FilterChip label="All" count={places.length} active={cat === "all"} onClick={() => setCat("all")} />
          {categories.map(([c, n]) => (
            <FilterChip key={c} label={c} count={n} active={cat === c} onClick={() => setCat(c)} />
          ))}
        </div>
      )}

      {/* body */}
      <div className="mt-4 flex-1 overflow-y-auto pr-1">
        {q.isLoading && <SkeletonGrid destination={shownName} />}

        {q.isError && (
          <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-ink/10 bg-cream/50 px-6 py-8 text-center">
            <Companion mood="think" size={54} />
            <p className="text-sm font-semibold text-ink">Couldn't load places</p>
            <p className="max-w-xs text-xs text-ink-faint">{apiErrorMessage(q.error)}</p>
            <button className="btn-ghost mt-1 text-xs" onClick={() => q.refetch()}>
              <RotateCcw className="h-3.5 w-3.5" /> Retry
            </button>
          </div>
        )}

        {q.isSuccess && (
          <div className="space-y-5">
            {/* in the destination */}
            {shown.some((p) => p.scope === "in") && (
              <PlaceSection title={`In ${destination}`}>
                {shown
                  .filter((p) => p.scope === "in")
                  .map((p) => (
                    <PlaceCard key={p.name} place={p} selected={selected.has(p.name)} onToggle={() => toggle(p.name)} />
                  ))}
              </PlaceSection>
            )}

            {/* nearby — one section per town/district, headed by its name */}
            {nearbyByTown.map(([town, group]) => (
              <PlaceSection
                key={town}
                title={`Around ${town}`}
                hint={`~${group[0].approx_hours ?? "?"} h away`}
              >
                {group.map((p) => (
                  <PlaceCard key={p.name} place={p} selected={selected.has(p.name)} onToggle={() => toggle(p.name)} />
                ))}
              </PlaceSection>
            ))}

            {shown.length === 0 && (
              <p className="py-8 text-center text-xs text-ink-faint">Nothing in this category.</p>
            )}
          </div>
        )}
      </div>

      {/* action bar */}
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-ink/5 pt-4">
        <span className="text-xs font-medium text-ink-soft">
          {selected.size === 0
            ? "Pick at least one place to continue"
            : `${selected.size} stop${selected.size > 1 ? "s" : ""} selected`}
        </span>
        <button
          className="btn-primary"
          onClick={submit}
          disabled={q.isLoading || selected.size === 0 || busy}
        >
          <Wand2 className="h-4 w-4" />
          {busy ? "Checking…" : "Plan my trip"}
        </button>
      </div>
    </div>
  );
}

function PlaceSection({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <h3 className="font-display text-sm font-extrabold text-ink">{title}</h3>
        {hint && <span className="sticker !bg-sky/20 !text-[#12486D]">{hint}</span>}
        <span className="h-0.5 flex-1 rounded-full bg-ink/10" />
      </div>
      <div className="grid gap-2.5 sm:grid-cols-2">{children}</div>
    </section>
  );
}

function FilterChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-full border px-2.5 py-1 text-[11px] font-extrabold capitalize transition active:scale-95",
        active
          ? "border-ink bg-brand-500 text-white shadow-chunky-sm"
          : "border-ink/15 bg-cream text-ink-soft hover:border-ink/30 hover:text-ink",
      )}
    >
      {label} <span className={cn("ml-0.5", active ? "text-white/70" : "text-ink-faint")}>{count}</span>
    </button>
  );
}

function PlaceCard({
  place,
  selected,
  onToggle,
}: {
  place: Attraction;
  selected: boolean;
  onToggle: () => void;
}) {
  const Icon = CAT_ICON[place.category] ?? MapPin;
  const tone = CAT_TONE[place.category] ?? CAT_TONE.other;
  return (
    <motion.button
      type="button"
      onClick={onToggle}
      whileTap={{ scale: 0.97 }}
      className={cn(
        "relative flex flex-col rounded-2xl border p-3 text-left transition-all hover:-translate-y-1",
        selected
          ? "border-teal-500/60 bg-teal-100/60 shadow-soft ring-2 ring-teal-500/25"
          : "border-ink/10 bg-cream hover:border-ink/25 hover:shadow-chunky-sm",
      )}
    >
      <span
        className={cn(
          "absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-full border transition",
          selected ? "border-ink bg-teal-500 text-white" : "border-ink/20 bg-paper",
        )}
      >
        <AnimatePresence>
          {selected && (
            <motion.span initial={{ scale: 0, rotate: -90 }} animate={{ scale: 1, rotate: 0 }} exit={{ scale: 0 }}>
              <Check className="h-3.5 w-3.5" strokeWidth={3} />
            </motion.span>
          )}
        </AnimatePresence>
      </span>

      <div className="flex items-center gap-1.5">
        <span className={cn("grid h-7 w-7 place-items-center rounded-lg", tone)}>
          <Icon className="h-4 w-4" />
        </span>
        <span className="text-[10px] font-extrabold uppercase tracking-wider text-ink-faint">
          {place.category}
        </span>
        {place.scope === "nearby" && place.approx_hours != null && (
          <span className="sticker !bg-sky/20 !text-[#12486D] !shadow-none">~{place.approx_hours}h</span>
        )}
      </div>
      <span className="mt-1.5 pr-6 font-display text-sm font-extrabold text-ink">{place.name}</span>
      <span className="text-[11px] font-medium text-ink-faint">{place.town}</span>
      <span className="mt-1 line-clamp-2 text-xs leading-snug text-ink-soft">{place.blurb}</span>
    </motion.button>
  );
}

/** The shimmer alone is silent, and finding places for somewhere we haven't
 *  seen before takes ~40s (each place the model suggests is checked against the
 *  map, one rate-limited lookup at a time). Left unexplained that reads as a
 *  hang, so the shimmer keeps its place and gets a line saying what's happening
 *  — the same deal the planning card makes with the traveller. */
function SkeletonGrid({ destination }: { destination: string }) {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2.5 rounded-2xl bg-cream p-3">
        <Companion mood="think" size={34} className="shrink-0" />
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-xs font-extrabold text-ink">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-500" />
            Looking up the best places in {destination}…
          </p>
          <p className="mt-0.5 text-[11px] font-medium leading-snug text-ink-faint">
            {secs}s · we check each one against the map so the pins are real. A
            place we haven't seen before can take up to a minute — instant next time.
          </p>
        </div>
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-28 skeleton rounded-2xl" />
        ))}
      </div>
    </div>
  );
}
