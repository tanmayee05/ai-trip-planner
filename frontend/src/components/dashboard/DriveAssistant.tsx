import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Fuel, Car, Bike, Check, X, Clock3, MapPinned, Loader2, EyeOff,
  UtensilsCrossed, BedDouble, MapPin, TicketCheck,
} from "lucide-react";
import toast from "react-hot-toast";

import { enrichPlan } from "@/api/plan";
import type {
  DriveOffer, DriveResult, FuelStop, FoodResult, StayResult, RouteMarker, GeoPoint, TollInfo,
} from "@/types/api";
import { apiErrorMessage } from "@/lib/api";
import { SectionHeader } from "@/components/common/SectionHeader";
import { Counter } from "@/components/common/Counter";
import { cn } from "@/lib/cn";

type FuelType = "petrol" | "diesel" | "cng";
type Pref = "any" | "meals" | "snacks" | "tiffins";

const VEHICLES = [
  { label: "Bike", icon: Bike, kmpl: 45 },
  { label: "Car", icon: Car, kmpl: 15 },
] as const;

const COMPANIES = ["Any", "Indian Oil", "Bharat Petroleum", "HP", "Shell", "Reliance", "Nayara"];
const PRIVATE = new Set(["shell", "reliance", "nayara"]);

const PRICE: Record<FuelType, number> = { petrol: 105, diesel: 92, cng: 80 };
const BAND_TONE: Record<string, string> = {
  budget: "bg-lime/20 text-[#146B52]",
  mid: "bg-sky/20 text-[#12486D]",
  premium: "bg-bubble/15 text-bubble",
};

interface Props {
  drive: DriveResult;
  offers: DriveOffer[];
  tolls?: TollInfo | null;
  source?: GeoPoint;
  destination?: GeoPoint;
  onRouteMarkers: (markers: RouteMarker[]) => void;
}

type OfferStatus = "open" | "no" | "skipped" | "yes";

export function DriveAssistant({ drive, offers, tolls, source, destination, onRouteMarkers }: Props) {
  const geometry = drive.geometry ?? [];
  const ends = source && destination
    ? { source: { lat: source.lat, lon: source.lon }, destination: { lat: destination.lat, lon: destination.lon } }
    : {};

  // ---------------- fuel (client-side, instant) ----------------
  const [vehicle, setVehicle] = useState<string | null>(null);
  const [customKmpl, setCustomKmpl] = useState("");
  const [fuelType, setFuelType] = useState<FuelType>("petrol");
  const [company, setCompany] = useState("Any");
  const kmpl = useMemo(() => {
    if (vehicle === "custom") return parseFloat(customKmpl) || 0;
    return VEHICLES.find((v) => v.label === vehicle)?.kmpl ?? 0;
  }, [vehicle, customKmpl]);
  const fuel = useMemo(() => {
    if (!kmpl) return null;
    const ow = drive.distance_km / kmpl;
    let p = PRICE[fuelType];
    if (PRIVATE.has(company.toLowerCase())) p += 3; // private pumps run a bit dearer
    return { lOW: +ow.toFixed(1), cOW: Math.round(ow * p), lRT: +(ow * 2).toFixed(1), cRT: Math.round(ow * 2 * p), p };
  }, [kmpl, fuelType, company, drive.distance_km]);

  // ---------------- results ----------------
  const [fuelStops, setFuelStops] = useState<FuelStop[]>([]);
  const [food, setFood] = useState<FoodResult | null>(null);
  const [stay, setStay] = useState<StayResult | null>(null);
  const [showTolls, setShowTolls] = useState(true);
  const [loading, setLoading] = useState<string | null>(null);

  // push everything to the map whenever a result changes
  useEffect(() => {
    const m: RouteMarker[] = [];
    for (const f of fuelStops) m.push({ name: f.name, lat: f.lat, lon: f.lon, kind: "fuel", sub: `${f.town ?? ""} · ~${f.km_from_start ?? 0} km in` });
    for (const p of food?.places ?? []) m.push({ name: p.name, lat: p.lat, lon: p.lon, kind: "food", sub: `${p.where}${p.approx ? " (approx)" : ""} · ${p.kind}` });
    for (const o of stay?.options ?? []) m.push({ name: o.name, lat: o.lat, lon: o.lon, kind: "stay", sub: `${o.where}${o.approx ? " (approx)" : ""} · ${o.band}` });
    if (showTolls)
      for (const t of tolls?.plazas ?? []) m.push({ name: t.name, lat: t.lat, lon: t.lon, kind: "toll", sub: `${t.area} · ~₹${t.car_cost} car${t.cost_estimated ? " (est.)" : ""} · ~${t.km_from_start} km in` });
    onRouteMarkers(m);
  }, [fuelStops, food, stay, tolls, showTolls, onRouteMarkers]);

  async function run<T>(key: string, body: Parameters<typeof enrichPlan>[0], onOk: (r: T) => void) {
    setLoading(key);
    try {
      onOk(await enrichPlan<T>(body));
    } catch (e) {
      toast.error(apiErrorMessage(e, "That lookup failed — try again."));
    } finally {
      setLoading(null);
    }
  }

  // ---------------- offers ----------------
  const [status, setStatus] = useState<Record<string, OfferStatus>>({});
  const setOffer = (id: string, s: OfferStatus) => setStatus((m) => ({ ...m, [id]: s }));
  const skipped = offers.filter((o) => status[o.id] === "skipped");
  const active = offers.filter((o) => (status[o.id] ?? "open") === "open" || status[o.id] === "yes");

  // food sub-form — look for eateries within N km of where you are now
  const [pref, setPref] = useState<Pref>("any");
  const [foodRadius, setFoodRadius] = useState("15");
  // stay sub-form — look for a hotel within N km of where you are now
  const [stayRadius, setStayRadius] = useState("150");

  function toggleFood() {
    if (food) { setFood(null); return; } // hide — the useEffect drops the pins
    run<FoodResult>("food", {
      kind: "food", geometry, ...ends,
      radius_km: parseInt(foodRadius, 10) || 15,
      preference: pref,
    }, (r) => {
      setFood(r);
      toast.success(r.places.length ? `${r.places.length} places near ${r.town}` : "Nothing found nearby");
    });
  }

  function toggleStay() {
    if (stay) { setStay(null); return; }
    run<StayResult>("stay", {
      kind: "stay", geometry, ...ends,
      radius_km: parseInt(stayRadius, 10) || 150,
    }, (r) => {
      setStay(r);
      toast.success(r.options.length ? `${r.options.length} hotels near ${r.town}` : "No hotels found in range");
    });
  }

  function togglePumps() {
    if (fuelStops.length) {
      setFuelStops([]); // hide — the useEffect drops them from the map
      return;
    }
    run<{ stops: FuelStop[] }>("pumps", { kind: "fuel_stops", geometry, company }, (r) => {
      setFuelStops(r.stops);
      toast.success(r.stops.length ? `${r.stops.length} pumps plotted` : "No matching pumps found");
    });
  }

  return (
    <div className="card card-hover card-sky p-5 sm:p-6">
      <SectionHeader emoji="⛽" tone="sky" title="On the road" subtitle="Fuel, food & rest stops — just for driving" />

      {/* ---- fuel ---- */}
      <p className="label">Your vehicle</p>
      <div className="flex flex-wrap gap-1.5">
        {VEHICLES.map((v) => (
          <button
            key={v.label}
            onClick={() => setVehicle(v.label)}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-extrabold transition active:scale-95",
              vehicle === v.label ? "border-ink bg-brand-500 text-white shadow-chunky-sm" : "border-ink/15 bg-cream text-ink-soft hover:border-ink/30",
            )}
          >
            <v.icon className="h-3.5 w-3.5" /> {v.label} · {v.kmpl}
          </button>
        ))}
        <button
          onClick={() => setVehicle("custom")}
          className={cn(
            "rounded-full border px-2.5 py-1 text-[11px] font-extrabold transition active:scale-95",
            vehicle === "custom" ? "border-ink bg-brand-500 text-white shadow-chunky-sm" : "border-ink/15 bg-cream text-ink-soft hover:border-ink/30",
          )}
        >
          Custom
        </button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {vehicle === "custom" && (
          <input type="number" min={1} max={120} placeholder="km / litre" value={customKmpl}
            onChange={(e) => setCustomKmpl(e.target.value)} className="input !w-28 !py-1.5 text-xs" />
        )}
        {(["petrol", "diesel", "cng"] as FuelType[]).map((f) => (
          <button key={f} onClick={() => setFuelType(f)}
            className={cn("rounded-full border px-2.5 py-1 text-[11px] font-bold capitalize transition",
              fuelType === f ? "border-ink bg-ink text-white" : "border-ink/15 text-ink-soft")}>
            {f}
          </button>
        ))}
      </div>

      <p className="label mt-3">Fuel company</p>
      <div className="flex flex-wrap gap-1.5">
        {COMPANIES.map((c) => (
          <button key={c} onClick={() => setCompany(c)}
            className={cn("rounded-full border px-2.5 py-1 text-[11px] font-bold transition active:scale-95",
              company === c ? "border-ink bg-brand-500 text-white shadow-chunky-sm" : "border-ink/15 bg-cream text-ink-soft hover:border-ink/30")}>
            {c}
          </button>
        ))}
      </div>

      <AnimatePresence>
        {fuel ? (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="mt-3 rounded-2xl bg-paper/80 p-3 ring-1 ring-inset ring-ink/10">
            <p className="flex items-center gap-1.5 text-xs font-bold text-ink-soft">
              <Fuel className="h-4 w-4 text-brand-500" /> Approx. fuel needed
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2 text-center">
              <div className="rounded-xl bg-cream p-2.5">
                <p className="text-[10px] font-bold uppercase text-ink-faint">One way</p>
                <p className="font-display text-sm font-extrabold text-ink"><Counter value={fuel.lOW} decimals={1} suffix=" L" /></p>
                <p className="text-[11px] text-ink-soft"><Counter value={fuel.cOW} prefix="₹" /></p>
              </div>
              <div className="rounded-xl bg-brand-50 p-2.5">
                <p className="text-[10px] font-bold uppercase text-brand-600">Round trip</p>
                <p className="font-display text-sm font-extrabold text-ink"><Counter value={fuel.lRT} decimals={1} suffix=" L" /></p>
                <p className="text-[11px] text-brand-700"><Counter value={fuel.cRT} prefix="₹" /></p>
              </div>
            </div>
            <p className="mt-1.5 text-[10px] text-ink-faint">at {kmpl} km/L · ₹{fuel.p}/L {fuelType}</p>
          </motion.div>
        ) : (
          <p className="mt-2 text-[11px] text-ink-faint">Pick your vehicle to see fuel litres + cost.</p>
        )}
      </AnimatePresence>

      {/* ---- fuel stops (toggle) ---- */}
      <button onClick={togglePumps}
        disabled={loading === "pumps" || !geometry.length}
        className={cn("mt-3 w-full !py-2 text-xs disabled:opacity-50", fuelStops.length ? "btn-ghost !border !border-ink/15" : "btn-teal")}>
        {loading === "pumps" ? <Loader2 className="h-4 w-4 animate-spin" />
          : fuelStops.length ? <EyeOff className="h-4 w-4" /> : <MapPinned className="h-4 w-4" />}
        {fuelStops.length ? `Hide petrol pumps (${fuelStops.length})` : "Show petrol pumps along the route"}
      </button>
      {fuelStops.length > 0 && (
        <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto pr-1">
          {fuelStops.map((f, i) => (
            <li key={i} className="flex items-center justify-between rounded-lg bg-cream px-2.5 py-1.5 text-[11px]">
              <span className="font-semibold text-ink">{f.name}</span>
              <span className="text-ink-faint">{f.town} · ~{f.km_from_start} km in</span>
            </li>
          ))}
          <li className="px-1 pt-1 text-[10px] text-ink-faint">{fuelStops[0]?.price_hint}</li>
        </ul>
      )}

      {/* ---- toll plazas (automatic for own-vehicle) ---- */}
      {tolls && tolls.count > 0 && (
        <div className="mt-3 rounded-2xl bg-paper/80 p-3 ring-1 ring-inset ring-ink/10">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-xs font-bold text-ink-soft">
              <TicketCheck className="h-4 w-4 text-[#7A6A9B]" />
              {tolls.count} toll plaza{tolls.count > 1 ? "s" : ""} · ~₹{tolls.car_cost_round_trip} car (round trip)
            </p>
            <button onClick={() => setShowTolls((v) => !v)}
              className="flex items-center gap-1 rounded-full border border-ink/15 px-2 py-0.5 text-[10px] font-bold text-ink-soft hover:border-ink/30">
              <EyeOff className="h-3 w-3" /> {showTolls ? "Hide" : "Show"}
            </button>
          </div>
          <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto pr-1">
            {tolls.plazas.map((t, i) => (
              <li key={i} className="flex items-center justify-between gap-2 rounded-lg bg-cream px-2.5 py-1.5 text-[11px]">
                <span className="min-w-0">
                  <span className="block truncate font-semibold text-ink">{t.name}</span>
                  <span className="text-ink-faint">{t.area} · ~{t.km_from_start} km in</span>
                </span>
                <span className="shrink-0 font-bold text-ink">
                  ~₹{t.car_cost}{t.cost_estimated ? "*" : ""}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-[10px] text-ink-faint">
            {tolls.note || "Car toll estimate."} {tolls.plazas.some((t) => t.cost_estimated) && "* estimated"}
          </p>
        </div>
      )}

      {/* ---- skipped chips ---- */}
      {skipped.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {skipped.map((o) => (
            <button key={o.id} onClick={() => setOffer(o.id, "open")}
              className="flex items-center gap-1 rounded-full border border-dashed border-ink/20 px-2.5 py-1 text-[11px] font-bold text-ink-soft hover:border-brand-400 hover:text-brand-600">
              {o.kind === "food" ? <UtensilsCrossed className="h-3 w-3" /> : <BedDouble className="h-3 w-3" />}
              {o.kind === "food" ? "Food near me?" : "Rest stop?"}
            </button>
          ))}
        </div>
      )}

      {/* ---- offer cards ---- */}
      <div className="mt-3 space-y-2">
        {active.map((o) => {
          const s = status[o.id] ?? "open";
          const question = o.kind === "food"
            ? "Want me to find places to eat near you?"
            : o.question;
          return (
            <div key={o.id} className="rounded-2xl border border-ink/10 bg-cream p-3">
              <p className="flex items-start gap-2 text-sm font-semibold text-ink">
                {o.kind === "food" ? <UtensilsCrossed className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" /> : <BedDouble className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />}
                {question}
              </p>

              {s === "open" && (
                <div className="mt-2 flex gap-1.5">
                  <button onClick={() => setOffer(o.id, "yes")} className="btn-primary !px-3 !py-1 text-xs"><Check className="h-3.5 w-3.5" /> Yes</button>
                  <button onClick={() => setOffer(o.id, "no")} className="btn-ghost !px-3 !py-1 text-xs"><X className="h-3.5 w-3.5" /> No</button>
                  <button onClick={() => setOffer(o.id, "skipped")} className="btn-ghost !px-3 !py-1 text-xs"><Clock3 className="h-3.5 w-3.5" /> Skip for now</button>
                </div>
              )}

              {s === "yes" && o.kind === "food" && (
                <div className="mt-2 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="flex items-center gap-1.5 text-[11px] font-bold text-ink-soft">
                      Within
                      <input type="number" min={1} max={200} value={foodRadius}
                        onChange={(e) => setFoodRadius(e.target.value)}
                        className="input !w-16 !py-1 text-xs" />
                      km of me
                    </label>
                    {(["any", "meals", "snacks", "tiffins"] as Pref[]).map((p) => (
                      <button key={p} onClick={() => setPref(p)}
                        className={cn("rounded-full border px-2 py-0.5 text-[10px] font-bold capitalize",
                          pref === p ? "border-ink bg-ink text-white" : "border-ink/15 text-ink-soft")}>{p}</button>
                    ))}
                  </div>
                  <button onClick={toggleFood}
                    disabled={loading === "food"}
                    className={cn("w-full !py-1.5 text-xs disabled:opacity-50", food ? "btn-ghost !border !border-ink/15" : "btn-teal")}>
                    {loading === "food" ? <Loader2 className="h-4 w-4 animate-spin" />
                      : food ? <EyeOff className="h-3.5 w-3.5" /> : <UtensilsCrossed className="h-3.5 w-3.5" />}
                    {food ? `Hide food stops (${food.places.length})` : "Find food near me"}
                  </button>
                  {food && <FoodResults food={food} />}
                </div>
              )}

              {s === "yes" && o.kind === "stay" && (
                <div className="mt-2 space-y-2">
                  <label className="flex items-center gap-1.5 text-[11px] font-bold text-ink-soft">
                    Check hotels within
                    <input type="number" min={5} max={500} step={5} value={stayRadius}
                      onChange={(e) => setStayRadius(e.target.value)}
                      className="input !w-20 !py-1 text-xs" />
                    km of where I am
                  </label>
                  <button onClick={toggleStay}
                    disabled={loading === "stay"}
                    className={cn("w-full !py-1.5 text-xs disabled:opacity-50", stay ? "btn-ghost !border !border-ink/15" : "btn-teal")}>
                    {loading === "stay" ? <Loader2 className="h-4 w-4 animate-spin" />
                      : stay ? <EyeOff className="h-3.5 w-3.5" /> : <BedDouble className="h-3.5 w-3.5" />}
                    {stay ? `Hide hotels (${stay.options.length})` : "Find a rest stop"}
                  </button>
                  {stay && <StayResults stay={stay} />}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FoodResults({ food }: { food: FoodResult }) {
  if (food.places.length === 0)
    return <p className="text-[11px] text-ink-faint">Nothing found within {food.radius_km} km — try a wider radius.</p>;
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] font-bold text-ink-soft">
        Near {food.town} · within {food.radius_km} km
      </p>
      {food.places.map((p) => (
        <div key={p.name} className="rounded-xl bg-paper/80 p-2.5 text-[11px] ring-1 ring-inset ring-ink/10">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-ink">{p.name}</span>
            <span className="shrink-0 rounded-full bg-cream px-1.5 py-0.5 text-[10px] font-bold capitalize text-ink-soft">{p.kind}</span>
          </div>
          <p className="mt-0.5 flex items-center gap-1 text-ink-faint">
            <MapPin className="h-3 w-3 shrink-0" />
            {p.where}{p.approx ? " (approx)" : ""}
          </p>
          <p className="mt-0.5 text-ink-soft">{p.why}</p>
        </div>
      ))}
      <p className="text-[10px] text-ink-faint">{food.note}</p>
    </div>
  );
}

function StayResults({ stay }: { stay: StayResult }) {
  if (!stay.town || stay.options.length === 0)
    return <p className="text-[11px] text-ink-faint">No hotels found within {stay.radius_km ?? 150} km — try a wider radius.</p>;
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] font-bold text-ink-soft">
        Around {stay.town}
        {typeof stay.km_from_start === "number" && stay.km_from_start > 0 && ` · ~${stay.km_from_start} km along your route`}
      </p>
      {stay.options.map((o) => (
        <div key={o.name} className="rounded-xl bg-paper/80 p-2.5 text-[11px] ring-1 ring-inset ring-ink/10">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-ink">{o.name}</span>
            <span className={cn("shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-extrabold capitalize", BAND_TONE[o.band] ?? BAND_TONE.mid)}>
              {o.band} · {o.price_hint}
            </span>
          </div>
          <p className="mt-0.5 flex items-center gap-1 text-ink-faint">
            <MapPin className="h-3 w-3 shrink-0" />
            {o.where}{o.approx ? " (approx)" : ""}
          </p>
          <p className="mt-0.5 text-ink-soft">{o.why}</p>
        </div>
      ))}
      <p className="text-[10px] text-ink-faint">{stay.note}</p>
    </div>
  );
}
