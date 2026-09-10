import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  History, RotateCcw, MapPin, CalendarDays, Compass, Route, Map as MapIcon,
  Bus, Car, Fuel, Wallet, SlidersHorizontal, ChevronDown, BedDouble, Undo2,
} from "lucide-react";

import { TopBar } from "@/components/TopBar";
import { TripRequestPanel } from "@/components/dashboard/TripRequestPanel";
import { AttractionPicker } from "@/components/dashboard/AttractionPicker";
import { ItineraryPanel } from "@/components/dashboard/ItineraryPanel";
import { ItineraryStaysPanel } from "@/components/dashboard/ItineraryStaysPanel";
import { MapPanel } from "@/components/dashboard/MapPanel";
import { RecommendationsPanel } from "@/components/dashboard/RecommendationsPanel";
import { DrivePanel } from "@/components/dashboard/DrivePanel";
import { ReturnTripPanel } from "@/components/dashboard/ReturnTripPanel";
import { DriveAssistant } from "@/components/dashboard/DriveAssistant";
import { HistoryDrawer } from "@/components/dashboard/HistoryDrawer";
import { PlanningProgress } from "@/components/dashboard/PlanningProgress";
import { CostEstimate } from "@/components/dashboard/CostEstimate";
import { JourneyNav, type JourneySection } from "@/components/dashboard/JourneyNav";
import { Doodles } from "@/components/decor/Doodles";
import { Companion } from "@/components/decor/Companion";
import { Confetti } from "@/components/common/Confetti";
import { usePlanJob } from "@/hooks/usePlanJob";
import { prettyDate, todayISO } from "@/lib/format";
import { classifyChange } from "@/lib/planDiff";
import { recostPlan } from "@/api/plan";
import { apiErrorMessage } from "@/lib/api";
import toast from "react-hot-toast";
import type { PlanInput, PlanStop } from "@/api/plan";
import type { PlanJob, RouteMarker, TripDetail } from "@/types/api";

const zone = {
  hidden: { opacity: 0, y: 18 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.06 * i, duration: 0.5, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

export function DashboardPage() {
  const [historyOpen, setHistoryOpen] = useState(false);
  const plan = usePlanJob();

  // trip basics captured from the form/chat, held while the user picks stops
  const [draft, setDraft] = useState<PlanInput | null>(null);
  const [pickedNames, setPickedNames] = useState<string[]>([]);
  // the full last-submitted input — re-seeds the form so you can tweak & re-plan
  const [lastInput, setLastInput] = useState<PlanInput | null>(null);
  // the input that produced the plan CURRENTLY on screen. `lastInput` follows
  // the form as it's edited; this one doesn't move until a plan actually runs,
  // so comparing the two is what tells us whether the plan has gone stale.
  const [plannedInput, setPlannedInput] = useState<PlanInput | null>(null);

  const [routeMarkers, setRouteMarkers] = useState<RouteMarker[]>([]);

  // once a plan is on screen the form has done its job — fold it to an icon.
  // `formKey` remounts the panel so it re-reads `initial` (History restore).
  const [planOpen, setPlanOpen] = useState(true);
  const [formKey, setFormKey] = useState(0);

  // The chat transcript id. Kept here rather than in localStorage so the
  // conversation has exactly the same lifetime as the form draft — it survives
  // tab switches and the stop-picking step, and is gone on "New" or a reload.
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);

  const running = plan.phase === "running";
  const job = plan.job;
  // While the job runs, `partial` holds the plan as far as it has been built —
  // same shape as the finished `result`, so every section below renders from it
  // unchanged and simply appears as soon as its data lands.
  const result = (plan.phase === "done" ? job?.result : job?.partial) ?? null;
  const itinerary = result?.itinerary ?? job?.itinerary ?? [];
  const isDrive = result?.mode === "drive";
  const routeLabel =
    job && `${job.source.name.split(",")[0]} → ${job.destination.name.split(",")[0]}`;

  // `{}` is truthy in JS, so "the key exists" is not the same as "there is
  // something to draw". These ask the second question — a panel handed an
  // empty object reads its fields and takes the page down with it.
  const hasCosts = !!result?.costs?.items?.length;
  const hasReturn = !!result?.return && Object.keys(result.return).length > 0;

  // Has the transport lookup actually produced something yet? While streaming,
  // an empty transport card is just noise — but once the plan is done we always
  // show the section, including its own "nothing confirmed" empty state.
  const hasTransport = !!(result?.mode || result?.train || result?.bus || result?.flight);

  const picking = !!draft; // draft set = we're on the "choose stops" step
  const showingResults = !picking && !running && !!job;

  /** the sections the journey rail can jump to, in page order */
  const navSections = useMemo<JourneySection[]>(() => {
    const s: JourneySection[] = [{ id: "sec-plan", label: "Plan", icon: Compass }];
    if (itinerary.length > 0) s.push({ id: "sec-itinerary", label: "Itinerary", icon: Route });
    if ((result?.itinerary_stays?.length ?? 0) > 0) {
      s.push({ id: "sec-stays", label: "Stay & food", icon: BedDouble });
    }
    s.push({ id: "sec-map", label: "Map", icon: MapIcon });
    s.push({
      id: "sec-transport",
      label: isDrive ? "Drive" : "Transport",
      icon: isDrive ? Car : Bus,
    });
    if (isDrive && result?.drive) s.push({ id: "sec-road", label: "On the road", icon: Fuel });
    if (hasReturn) s.push({ id: "sec-return", label: "Way back", icon: Undo2 });
    if (hasCosts) s.push({ id: "sec-cost", label: "Budget", icon: Wallet });
    return s;
  }, [itinerary.length, isDrive, result?.drive, hasCosts, result?.itinerary_stays, hasReturn]);

  /** food + hotel pins for each overnight itinerary stop, dropped on the map
   *  alongside any driving-route pins (fuel/food/stay/toll from DriveAssistant) */
  const stayFoodMarkers = useMemo<RouteMarker[]>(() => {
    const m: RouteMarker[] = [];
    for (const s of result?.itinerary_stays ?? []) {
      for (const p of s.food) m.push({ name: p.name, lat: p.lat, lon: p.lon, kind: "food", sub: `Night ${s.day} · ${p.where}` });
      for (const h of s.stay) m.push({ name: h.name, lat: h.lat, lon: h.lon, kind: "stay", sub: `Night ${s.day} · ${h.where}` });
    }
    return m;
  }, [result?.itinerary_stays]);

  // fire confetti the moment a plan lands
  const [celebrate, setCelebrate] = useState(0);
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && plan.phase === "done") {
      setCelebrate((c) => c + 1);
      setPlanOpen(false); // results are in — get the form out of the way
    }
    wasRunning.current = plan.phase === "running";
  }, [plan.phase]);

  /** Form "Next", or the chat once it has every answer.
   *
   *  What this does depends on what actually changed, because editing a field
   *  and being handed back the SAME plan is wrong — the plan no longer matches
   *  its own inputs. See lib/planDiff.ts for the rule; in short:
   *
   *    destination moved  -> the chosen stops aren't in this trip any more,
   *                          so go back to the picker
   *    source/days/mode   -> stops still stand, but the route, the day split
   *    (or date, on public  and the timetable answers are all stale: re-plan
   *     transport)          immediately with the stops already chosen
   *    people only        -> the plan is untouched; only the per-head budget
   *    (or date, driving)   moves, so re-cost in place and keep the plan
   */
  function handleDetails(values: PlanInput) {
    setPlanOpen(true);
    setLastInput(values);

    // Already choosing stops for a trip that hasn't been planned yet? Then this
    // edit belongs to that pending trip. Carry it in and stay in the picker —
    // classifying it against the PREVIOUS plan would decide the edit was
    // cosmetic and drop the traveller out of the step they were in the middle of.
    if (draft) {
      if (values.destination !== draft.destination) setPickedNames([]);
      setDraft(values);
      return;
    }

    const change = classifyChange(plannedInput, values);

    if (change === "restops") {
      if (values.destination !== plannedInput?.destination) setPickedNames([]);
      setDraft(values); // -> AttractionPicker
      return;
    }

    if (change === "replan") {
      const stops = plannedInput?.stops ?? [];
      setRouteMarkers([]);
      setPlannedInput({ ...values, stops });
      plan.run({ ...values, stops, chat_session_id: chatSessionId });
      setDraft(null);
      return;
    }

    if (change === "cosmetic") {
      applyCosmeticChange(values);
      return;
    }

    toast("Nothing changed — your plan is already up to date.");
  }

  /** An input the plan doesn't depend on. Keep the plan, move the budget. */
  async function applyCosmeticChange(values: PlanInput) {
    const stops = plannedInput?.stops ?? [];
    setPlannedInput({ ...values, stops });
    setDraft(null);

    const current = plan.job?.result;
    if (!current || !values.num_days || !values.num_people) return;

    try {
      const costs = await recostPlan({
        num_days: values.num_days,
        num_people: values.num_people,
        travel_mode: values.travel_mode,
        result: current,
      });
      plan.patchResult({ costs });
      toast.success("Details updated — budget recalculated, no re-planning needed.");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update the budget."));
    }
  }

  function handlePlan(stops: PlanStop[]) {
    if (!draft) return;
    setPickedNames(stops.map((s) => s.name));
    const full = { ...draft, stops };
    setLastInput(full);
    setPlannedInput(full); // this is the input the resulting plan belongs to
    setRouteMarkers([]); // clear route pins from the previous plan
    // hand the chat transcript id along so, if this trip gets saved, History
    // can restore the same conversation later instead of starting a blank one
    plan.run({ ...full, chat_session_id: chatSessionId });
    setDraft(null);
  }

  /** re-open the stop picker with the same trip basics + current selection */
  function editStops() {
    if (!lastInput) return;
    setDraft(lastInput);
  }

  /** History → "New trip": drop the current plan and land back on a blank form */
  function startNewTrip() {
    plan.reset();
    setDraft(null);
    setLastInput(null);
    setPlannedInput(null);
    setPickedNames([]);
    setRouteMarkers([]);
    setChatSessionId(null);
    setPlanOpen(true);
    setFormKey((k) => k + 1);
  }

  /** History → reopen a saved trip as the current result */
  function openSavedTrip(t: TripDetail) {
    const asJob: PlanJob = {
      job_id: `trip-${t.id}`,
      state: "done",
      source: { name: t.source ?? "Start", lat: t.source_lat, lon: t.source_lon, display_name: t.source ?? "" },
      destination: { name: t.destination ?? "Destination", lat: t.dest_lat, lon: t.dest_lon, display_name: t.destination ?? "" },
      travel_date: t.travel_date ?? "",
      itinerary: t.result.itinerary ?? [],
      trip_id: t.id,
      result: t.result,
    };
    // Rebuild the original inputs so the form shows source / destination /
    // date / days / people / mode instead of coming back empty. days+people
    // survive in the cost assumptions; the mode is implied by result.mode.
    const restored: PlanInput = {
      source: t.source ?? "",
      destination: t.destination ?? "",
      travel_date: t.travel_date ?? todayISO(),
      num_days: t.result?.costs?.assumptions?.days,
      num_people: t.result?.costs?.assumptions?.people,
      travel_mode: t.result?.mode === "drive" ? "own_vehicle" : "public_transport",
      stops: (t.result?.itinerary ?? []).map((x) => ({
        name: x.name,
        lat: x.lat,
        lon: x.lon,
        category: x.category,
        blurb: x.blurb,
      })),
    };
    setLastInput(restored);
    // The restored plan belongs to these inputs, so an untouched form must read
    // as "nothing changed" — without this, reopening a trip and pressing Next
    // would send the traveller back to the stop picker for no reason.
    setPlannedInput(restored);
    setPickedNames((t.result?.itinerary ?? []).map((x) => x.name));
    // restore the conversation that planned THIS trip (if it has one) instead
    // of always starting blank — older trips saved before this existed just
    // fall back to null, same as before
    setChatSessionId(t.chat_session_id ?? null);
    setFormKey((k) => k + 1); // force the panel to re-read `initial`
    setPlanOpen(false);
    setDraft(null);
    plan.showExisting(asJob);
  }

  return (
    /* overflow-x-clip (not -hidden) — `hidden` would make this a scroll
       container and quietly break every `position: sticky` inside it */
    <div className="relative min-h-screen overflow-x-clip bg-cream bg-mesh">
      <div className="contours pointer-events-none absolute inset-0" aria-hidden />
      <Doodles />
      <Confetti fireKey={celebrate} />

      <TopBar
        right={
          <button
            onClick={() => setHistoryOpen(true)}
            className="btn-outline !px-3 !py-2 text-xs"
            aria-label="Open history"
          >
            <History className="h-4 w-4" />
            <span className="hidden sm:inline">History</span>
          </button>
        }
      />

      <main className="relative mx-auto max-w-6xl px-4 py-5 sm:px-6 sm:py-7">
        {showingResults && <JourneyNav sections={navSections} />}

        <div className="grid gap-5 lg:grid-cols-[minmax(320px,376px)_1fr] lg:items-start">
          {/* ---------------- left column ---------------- */}
          <motion.div
            id="sec-plan"
            variants={zone}
            custom={0}
            initial="hidden"
            animate="show"
            className={`scroll-anchor space-y-4 lg:sticky ${
              showingResults ? "lg:top-[9.5rem]" : "lg:top-24"
            }`}
          >
            {/* One home for the trip details, always: the Form/Chat panel. It
                stays mounted through picking stops and through results, so
                switching steps never swaps the form out for something else —
                the two tabs are separate ways in, over one shared draft. */}
            <div className="relative">
              <AnimatePresence initial={false}>
                {showingResults && !planOpen && (
                  <motion.div
                    key="plan-chip"
                    initial={{ opacity: 0, y: -8, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -8, scale: 0.96 }}
                    transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                  >
                    <PlanChip onOpen={() => setPlanOpen(true)} />
                  </motion.div>
                )}
              </AnimatePresence>

              <motion.div
                className={showingResults && !planOpen ? "hidden" : "block"}
                initial={false}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              >
                <TripRequestPanel
                  key={formKey}
                  onSubmit={handleDetails}
                  busy={running}
                  initial={lastInput ?? undefined}
                  onCollapse={showingResults ? () => setPlanOpen(false) : undefined}
                  chatSessionId={chatSessionId}
                  onChatSessionId={setChatSessionId}
                  planned={showingResults}
                  plannedInput={plannedInput}
                />
              </motion.div>
            </div>

            {job && !picking && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="card card-teal overflow-hidden p-4 text-xs"
              >
                <p className="flex items-center gap-1.5 font-display text-sm font-extrabold text-ink">
                  <span className="grid h-6 w-6 place-items-center rounded-lg bg-teal-500/15">
                    <MapPin className="h-3.5 w-3.5 text-teal-700" />
                  </span>
                  {job.source.name.split(",")[0]} → {job.destination.name.split(",")[0]}
                </p>
                <p className="mt-2 flex items-center gap-1.5 font-semibold text-teal-700">
                  <CalendarDays className="h-3.5 w-3.5" />
                  {prettyDate(job.travel_date)}
                  {itinerary.length > 0 && ` · ${itinerary.length} stops`}
                </p>
                <div className="perf my-2.5" />
                <p className="text-[11px] font-medium leading-relaxed text-ink-soft">
                  Changing the start, destination, days{" "}
                  {plannedInput?.travel_mode === "own_vehicle" ? "or mode" : ", date or mode"}{" "}
                  re-plans the whole trip. Party size
                  {plannedInput?.travel_mode === "own_vehicle" ? " or date" : ""} just updates the
                  budget.
                  {itinerary.length > 0 && (
                    <>
                      {" "}Or{" "}
                      <button
                        onClick={editStops}
                        className="font-extrabold text-brand-600 underline decoration-brand-300 underline-offset-2 transition hover:text-brand-700"
                      >
                        change your stops
                      </button>
                      .
                    </>
                  )}
                </p>
              </motion.div>
            )}

            {plan.phase === "error" && (
              <div className="card card-coral flex items-center justify-between gap-3 p-4">
                <p className="text-xs text-ink-soft">{plan.errorMessage}</p>
                <button className="btn-ghost !px-2 !py-1 text-xs" onClick={plan.reset}>
                  <RotateCcw className="h-3.5 w-3.5" /> Dismiss
                </button>
              </div>
            )}
          </motion.div>

          {/* ---------------- right column ---------------- */}
          <div className="space-y-5">
            <AnimatePresence mode="wait">
              {picking && draft ? (
                <motion.div
                  key="picker"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -12 }}
                >
                  <AttractionPicker
                    key={draft.destination}
                    destination={draft.destination}
                    initialSelected={pickedNames}
                    onPlan={handlePlan}
                    onBack={() => setDraft(null)}
                  />
                </motion.div>
              ) : (
                <motion.div
                  key="results"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="space-y-5"
                >
                  {/* The planning animation now sits ABOVE the results rather
                      than instead of them: finished sections stream in below
                      it while the rest is still being worked out, and it fades
                      away on its own the moment the plan is complete. Keeping
                      it inside the same `key="results"` branch is what stops
                      every section re-mounting and re-animating at the finish. */}
                  <AnimatePresence>
                    {running && job && (
                      <motion.div
                        key="progress"
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -16, height: 0, marginBottom: 0 }}
                        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                        className="overflow-hidden"
                      >
                        <PlanningProgress
                          source={job.source.name}
                          destination={job.destination.name}
                          elapsedMs={plan.elapsedMs}
                          stages={job.stages}
                          stagesDone={job.stages_done}
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {!job && <Hero />}

                  {itinerary.length > 0 && (
                    <motion.section
                      id="sec-itinerary"
                      className="scroll-anchor"
                      variants={zone}
                      custom={0}
                      initial="hidden"
                      animate="show"
                    >
                      <ItineraryPanel
                        itinerary={itinerary}
                        notes={result?.itinerary_notes}
                        onEdit={editStops}
                      />
                    </motion.section>
                  )}

                  {(result?.itinerary_stays?.length ?? 0) > 0 && (
                    <motion.section
                      id="sec-stays"
                      className="scroll-anchor"
                      variants={zone}
                      custom={0.5}
                      initial="hidden"
                      animate="show"
                    >
                      <ItineraryStaysPanel stays={result!.itinerary_stays!} />
                    </motion.section>
                  )}

                  <motion.section
                    id="sec-map"
                    className="scroll-anchor"
                    variants={zone}
                    custom={1}
                    initial="hidden"
                    animate="show"
                  >
                    <MapPanel
                      source={job?.source}
                      destination={job?.destination}
                      itinerary={itinerary}
                      routeLine={isDrive ? result?.drive?.geometry : undefined}
                      routeMarkers={[...routeMarkers, ...stayFoodMarkers]}
                    />
                  </motion.section>

                  {(hasTransport || plan.phase === "done") && (
                  <motion.section
                    id="sec-transport"
                    className="scroll-anchor"
                    variants={zone}
                    custom={2}
                    initial="hidden"
                    animate="show"
                  >
                    {isDrive ? (
                      <DrivePanel
                        drive={result?.drive}
                        routeLabel={routeLabel || undefined}
                        hasStops={itinerary.length > 0}
                      />
                    ) : (
                      <RecommendationsPanel result={result} routeLabel={routeLabel || undefined} />
                    )}
                  </motion.section>
                  )}

                  {isDrive && result?.drive && (
                    <motion.section
                      id="sec-road"
                      className="scroll-anchor"
                      variants={zone}
                      custom={3}
                      initial="hidden"
                      animate="show"
                    >
                      <DriveAssistant
                        drive={result.drive}
                        offers={result.offers ?? []}
                        tolls={result.tolls}
                        source={job?.source}
                        destination={job?.destination}
                        onRouteMarkers={setRouteMarkers}
                      />
                    </motion.section>
                  )}

                  {hasReturn && (
                    <motion.section
                      id="sec-return"
                      className="scroll-anchor"
                      variants={zone}
                      custom={3.5}
                      initial="hidden"
                      animate="show"
                    >
                      <ReturnTripPanel ret={result.return} isDrive={isDrive} hasStops={itinerary.length > 0} />
                    </motion.section>
                  )}

                  {hasCosts && (
                    <motion.section
                      id="sec-cost"
                      className="scroll-anchor"
                      variants={zone}
                      custom={4}
                      initial="hidden"
                      animate="show"
                    >
                      {/* hasCosts guarantees this, but it can't narrow the type */}
                      <CostEstimate costs={result!.costs!} />
                    </motion.section>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>

      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onOpenTrip={openSavedTrip}
        onNewTrip={startNewTrip}
      />
    </div>
  );
}

/** Collapsed stand-in for the trip form: an icon you tap to bring it back. */
function PlanChip({ onOpen }: { onOpen: () => void }) {
  return (
    <motion.button
      onClick={onOpen}
      whileHover={{ y: -3 }}
      whileTap={{ scale: 0.98 }}
      className="card card-hover group flex w-full items-center gap-3 p-3 text-left"
      aria-label="Open the trip planner"
    >
      <span className="blob-chip bg-brand-100 text-brand-700 group-hover:rotate-6">
        <SlidersHorizontal className="h-5 w-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-extrabold text-ink">Plan a trip</span>
        <span className="block text-[11px] font-medium text-ink-faint">
          Tap to change your details
        </span>
      </span>
      <motion.span
        aria-hidden
        animate={{ y: [0, 3, 0] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
        className="text-ink-faint"
      >
        <ChevronDown className="h-4 w-4" />
      </motion.span>
    </motion.button>
  );
}

/** First-run welcome — a boarding-pass style intro. */
function Hero() {
  return (
    <motion.div
      variants={zone}
      custom={0}
      initial="hidden"
      animate="show"
      className="relative overflow-hidden rounded-3xl border border-white/15 bg-sunset p-6 text-white shadow-lift sm:p-7"
      style={{ backgroundSize: "220% 220%" }}
    >
      <div className="absolute inset-0 animate-gradient-pan bg-sunset opacity-90" style={{ backgroundSize: "220% 220%" }} />
      <div className="pointer-events-none absolute inset-0 contours opacity-40" />

      {/* flight path */}
      <svg
        className="pointer-events-none absolute -right-6 top-4 h-28 w-56 opacity-40"
        viewBox="0 0 220 100"
        fill="none"
        aria-hidden
      >
        <path
          d="M4 88 C 60 84, 96 52, 128 26 S 196 6, 214 10"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray="7 9"
          className="animate-dash-flow"
        />
        <circle cx="4" cy="88" r="4" fill="white" />
        <path d="M206 4 l12 6 -12 6 3 -6 z" fill="white" />
      </svg>

      <div className="relative flex items-center gap-4">
        <span className="grid h-16 w-16 shrink-0 place-items-center rounded-2xl border border-white/40 bg-white/95 shadow-soft">
          <Companion mood="wave" size={52} />
        </span>
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-white/70">
            Wayfarer · your route planner
          </p>
          <h2 className="mt-1 font-display text-2xl font-extrabold leading-none text-white">
            Where are we headed?
          </h2>
          <p className="mt-2 max-w-md text-sm font-medium leading-relaxed text-white/90">
            Fill in a trip on the left — or just chat. Pick the places you care about
            and I'll work out how to get you there, day by day.
          </p>
        </div>
      </div>
    </motion.div>
  );
}
