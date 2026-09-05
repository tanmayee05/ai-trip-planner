import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { History, RotateCcw, MapPin, CalendarDays } from "lucide-react";

import { TopBar } from "@/components/TopBar";
import { TripRequestPanel } from "@/components/dashboard/TripRequestPanel";
import { AttractionPicker } from "@/components/dashboard/AttractionPicker";
import { ItineraryPanel } from "@/components/dashboard/ItineraryPanel";
import { MapPanel } from "@/components/dashboard/MapPanel";
import { RecommendationsPanel } from "@/components/dashboard/RecommendationsPanel";
import { DrivePanel } from "@/components/dashboard/DrivePanel";
import { HistoryDrawer } from "@/components/dashboard/HistoryDrawer";
import { PlanningProgress } from "@/components/dashboard/PlanningProgress";
import { CostEstimate } from "@/components/dashboard/CostEstimate";
import { Doodles } from "@/components/decor/Doodles";
import { Companion } from "@/components/decor/Companion";
import { Confetti } from "@/components/common/Confetti";
import { usePlanJob } from "@/hooks/usePlanJob";
import { prettyDate } from "@/lib/format";
import type { PlanInput, PlanStop } from "@/api/plan";
import type { PlanJob, TripDetail } from "@/types/api";

const zone = {
  hidden: { opacity: 0, y: 16 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.06 * i, duration: 0.4, ease: [0.22, 1, 0.36, 1] as const },
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

  const running = plan.phase === "running";
  const job = plan.job;
  const result = plan.phase === "done" ? job?.result ?? null : null;
  const itinerary = result?.itinerary ?? job?.itinerary ?? [];
  const isDrive = result?.mode === "drive";
  const routeLabel =
    job && `${job.source.name.split(",")[0]} → ${job.destination.name.split(",")[0]}`;

  const picking = !!draft; // draft set = we're on the "choose stops" step

  // fire confetti the moment a plan lands
  const [celebrate, setCelebrate] = useState(0);
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && plan.phase === "done") setCelebrate((c) => c + 1);
    wasRunning.current = plan.phase === "running";
  }, [plan.phase]);

  function handleDetails(values: PlanInput) {
    setDraft(values);
    setLastInput(values);
    setPickedNames([]);
  }

  function handlePlan(stops: PlanStop[]) {
    if (!draft) return;
    setPickedNames(stops.map((s) => s.name));
    const full = { ...draft, stops };
    setLastInput(full);
    plan.run(full);
    setDraft(null);
  }

  /** re-open the stop picker with the same trip basics + current selection */
  function editStops() {
    if (!lastInput) return;
    setDraft(lastInput);
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
    setDraft(null);
    plan.showExisting(asJob);
  }

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-cream bg-mesh">
      <div className="pointer-events-none absolute -left-24 top-32 h-64 w-64 rounded-blob bg-brand-100/60 blur-2xl animate-float-slow" />
      <div className="pointer-events-none absolute -right-20 top-[40rem] h-72 w-72 rounded-blob bg-teal-100/50 blur-2xl animate-float-slow [animation-delay:-4s]" />
      <Doodles />
      <Confetti fireKey={celebrate} />

      <TopBar
        right={
          <button
            onClick={() => setHistoryOpen(true)}
            className="btn-ghost !px-3"
            aria-label="Open history"
          >
            <History className="h-4 w-4" />
            <span className="hidden sm:inline">History</span>
          </button>
        }
      />

      <main className="relative mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        <div className="grid gap-5 lg:grid-cols-[minmax(320px,380px)_1fr] lg:items-start">
          {/* left column */}
          <motion.div
            variants={zone}
            custom={0}
            initial="hidden"
            animate="show"
            className="space-y-4 lg:sticky lg:top-24"
          >
            <TripRequestPanel
              onSubmit={handleDetails}
              busy={running}
              initial={lastInput ?? undefined}
            />

            {job && !picking && (
              <div className="rounded-3xl border-2 border-ink bg-teal-100 p-4 text-xs shadow-chunky">
                <p className="flex items-center gap-1.5 font-display text-sm font-extrabold text-ink">
                  <MapPin className="h-4 w-4 text-teal-700" />
                  {job.source.name.split(",")[0]} → {job.destination.name.split(",")[0]}
                </p>
                <p className="mt-1 flex items-center gap-1.5 font-semibold text-teal-800">
                  <CalendarDays className="h-3.5 w-3.5" />
                  {prettyDate(job.travel_date)}
                  {itinerary.length > 0 && ` · ${itinerary.length} stops`}
                </p>
                <p className="mt-2 text-[11px] font-medium text-teal-800/80">
                  Edit the fields above and hit <strong>Next</strong> to re-plan.
                  {itinerary.length > 0 && (
                    <>
                      {" "}Or{" "}
                      <button onClick={editStops} className="font-extrabold text-brand-600 underline">
                        change your stops
                      </button>
                      .
                    </>
                  )}
                </p>
              </div>
            )}

            {plan.phase === "error" && (
              <div className="card flex items-center justify-between gap-3 border-l-4 border-brand-500 p-4">
                <p className="text-xs text-ink-soft">{plan.errorMessage}</p>
                <button className="btn-ghost !px-2 !py-1 text-xs" onClick={plan.reset}>
                  <RotateCcw className="h-3.5 w-3.5" /> Dismiss
                </button>
              </div>
            )}
          </motion.div>

          {/* right column */}
          <div className="space-y-5">
            <AnimatePresence mode="wait">
              {picking && draft ? (
                <motion.div
                  key="picker"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                >
                  <AttractionPicker
                    destination={draft.destination}
                    initialSelected={pickedNames}
                    onPlan={handlePlan}
                    onBack={() => setDraft(null)}
                  />
                </motion.div>
              ) : running && job ? (
                <motion.div
                  key="progress"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                >
                  <PlanningProgress
                    source={job.source.name}
                    destination={job.destination.name}
                    elapsedMs={plan.elapsedMs}
                  />
                </motion.div>
              ) : (
                <motion.div
                  key="results"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="space-y-5"
                >
                  {!job && (
                    <motion.div
                      variants={zone}
                      custom={0}
                      initial="hidden"
                      animate="show"
                      className="relative overflow-hidden rounded-3xl border-2 border-ink bg-sunset p-6 text-white shadow-chunky-lg"
                    >
                      <div className="pointer-events-none absolute -right-6 -top-6 h-28 w-28 rounded-blob bg-white/20" />
                      <div className="pointer-events-none absolute -bottom-8 left-1/3 h-24 w-24 rounded-blob bg-black/10" />
                      <div className="relative flex items-center gap-4">
                        <span className="grid h-16 w-16 shrink-0 place-items-center rounded-2xl border-2 border-ink bg-white/95 shadow-chunky">
                          <Companion mood="wave" size={52} />
                        </span>
                        <div>
                          <h2 className="font-display text-2xl font-extrabold leading-none text-white">
                            Hi, I'm Pip! 👋
                          </h2>
                          <p className="mt-1.5 text-sm font-medium text-white/90">
                            Fill in a trip on the left (or just chat), pick some places,
                            and I'll figure out how to get you there.
                          </p>
                        </div>
                      </div>
                    </motion.div>
                  )}
                  {itinerary.length > 0 && (
                    <motion.div variants={zone} custom={0} initial="hidden" animate="show">
                      <ItineraryPanel itinerary={itinerary} onEdit={editStops} />
                    </motion.div>
                  )}
                  <motion.div variants={zone} custom={1} initial="hidden" animate="show">
                    <MapPanel
                      source={job?.source}
                      destination={job?.destination}
                      itinerary={itinerary}
                    />
                  </motion.div>
                  <motion.div variants={zone} custom={2} initial="hidden" animate="show">
                    {isDrive ? (
                      <DrivePanel
                        drive={result?.drive}
                        routeLabel={routeLabel || undefined}
                        hasStops={itinerary.length > 0}
                      />
                    ) : (
                      <RecommendationsPanel result={result} routeLabel={routeLabel || undefined} />
                    )}
                  </motion.div>
                  {result?.costs && (
                    <motion.div variants={zone} custom={3} initial="hidden" animate="show">
                      <CostEstimate costs={result.costs} />
                    </motion.div>
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
      />
    </div>
  );
}
