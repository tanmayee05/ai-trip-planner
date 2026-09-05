import { AnimatePresence, motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, History as HistoryIcon, Trash2, MapPin, RotateCcw, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { listTrips, getTrip, deleteTrip } from "@/api/trips";
import { useAuth } from "@/context/AuthContext";
import { apiErrorMessage } from "@/lib/api";
import { prettyDate, prettyDateTime } from "@/lib/format";
import { Companion } from "@/components/decor/Companion";
import type { TripDetail } from "@/types/api";

interface Props {
  open: boolean;
  onClose: () => void;
  onOpenTrip: (trip: TripDetail) => void;
}

export function HistoryDrawer({ open, onClose, onOpenTrip }: Props) {
  const { status } = useAuth();
  const qc = useQueryClient();

  const trips = useQuery({
    queryKey: ["trips"],
    queryFn: listTrips,
    enabled: open && status === "authenticated",
  });

  const openMut = useMutation({
    mutationFn: getTrip,
    onSuccess: (trip) => {
      onOpenTrip(trip);
      onClose();
    },
    onError: (e) => toast.error(apiErrorMessage(e, "Couldn't load that trip.")),
  });

  const delMut = useMutation({
    mutationFn: deleteTrip,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trips"] });
      toast.success("Trip removed");
    },
    onError: (e) => toast.error(apiErrorMessage(e, "Couldn't delete that trip.")),
  });

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col bg-cream shadow-lift"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
          >
            <header className="flex items-center justify-between border-b border-ink/5 px-5 py-4">
              <div className="flex items-center gap-2">
                <HistoryIcon className="h-5 w-5 text-brand-500" />
                <h2 className="font-display text-xl font-extrabold">Your trips</h2>
              </div>
              <button
                onClick={onClose}
                className="grid h-8 w-8 place-items-center rounded-full text-ink-soft transition hover:bg-ink/5 hover:text-ink"
                aria-label="Close history"
              >
                <X className="h-4 w-4" />
              </button>
            </header>

            <div className="flex-1 overflow-y-auto p-4">
              {status !== "authenticated" ? (
                <Empty text="Sign in to save and revisit your trips." />
              ) : trips.isLoading ? (
                <div className="space-y-2.5">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="h-20 skeleton rounded-2xl" />
                  ))}
                </div>
              ) : trips.isError ? (
                <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-ink/10 bg-paper px-6 py-10 text-center">
                  <p className="text-sm font-semibold text-ink">Couldn't load history</p>
                  <p className="text-xs text-ink-faint">{apiErrorMessage(trips.error)}</p>
                  <button className="btn-ghost mt-1 text-xs" onClick={() => trips.refetch()}>
                    <RotateCcw className="h-3.5 w-3.5" /> Retry
                  </button>
                </div>
              ) : (trips.data?.length ?? 0) === 0 ? (
                <Empty text="Nothing saved yet. Plans you run while signed in show up here automatically." />
              ) : (
                <ul className="space-y-2.5">
                  {trips.data!.map((t) => (
                    <li key={t.id}>
                      <div className="group card p-3.5">
                        <button
                          className="w-full text-left"
                          onClick={() => openMut.mutate(t.id)}
                          disabled={openMut.isPending}
                        >
                          <p className="flex items-center gap-1.5 font-display text-sm font-bold text-ink">
                            <MapPin className="h-3.5 w-3.5 text-brand-500" />
                            {t.title ?? `${t.source} → ${t.destination}`}
                          </p>
                          <p className="mt-0.5 text-[11px] text-ink-faint">
                            {t.travel_date ? prettyDate(t.travel_date) : "—"} · saved{" "}
                            {prettyDateTime(t.created_at)}
                          </p>
                        </button>
                        <div className="mt-2 flex items-center justify-between">
                          <span className="text-[11px] font-medium text-brand-600">
                            {openMut.isPending && openMut.variables === t.id ? (
                              <span className="flex items-center gap-1">
                                <Loader2 className="h-3 w-3 animate-spin" /> opening…
                              </span>
                            ) : (
                              "Open →"
                            )}
                          </span>
                          <button
                            onClick={() => delMut.mutate(t.id)}
                            disabled={delMut.isPending}
                            className="rounded-lg p-1.5 text-ink-faint opacity-0 transition hover:bg-brand-50 hover:text-brand-600 group-hover:opacity-100"
                            aria-label="Delete trip"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-ink/10 bg-paper px-6 py-12 text-center">
      <Companion mood="sleep" size={56} />
      <p className="text-sm font-semibold text-ink">Nothing here yet</p>
      <p className="max-w-[16rem] text-xs text-ink-faint">{text}</p>
    </div>
  );
}
