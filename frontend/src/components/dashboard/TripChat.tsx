import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { SendHorizonal, Sparkles, Loader2, Check, CircleDashed } from "lucide-react";
import toast from "react-hot-toast";

import { sendChat, getChatHistory } from "@/api/chat";
import type { TripDraft } from "@/components/dashboard/TripRequestPanel";
import type { TravelMode } from "@/api/plan";
import type {
  ChatResponse, ItineraryStayFood, ItineraryStop, PendingAction, TripSlots,
} from "@/types/api";
import { apiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/cn";

/* The chat session id deliberately lives in React state up in DashboardPage,
 * NOT in localStorage. That gives the conversation exactly the same lifetime
 * as the form draft: it survives switching tabs and picking stops, and it is
 * gone on "New" or a page reload — so a new chat never opens with the
 * previous trip's questions still in it. */

/** The inverse of slotsToDraftPatch — hand the backend what we already have
 *  so next_question() skips it. */
export function draftToKnown(d: TripDraft) {
  const days = parseInt(d.num_days, 10);
  const people = parseInt(d.num_people, 10);
  return {
    source: d.source.trim() || null,
    destination: d.destination.trim() || null,
    num_days: Number.isFinite(days) && days > 0 ? days : null,
    num_people: Number.isFinite(people) && people > 0 ? people : null,
    start_date: d.travel_date || null,
    travel_mode: d.travel_mode || null,
  };
}

function slotsToDraftPatch(s: Partial<TripSlots>): Partial<TripDraft> {
  const p: Partial<TripDraft> = {};
  if (s.source) p.source = s.source;
  if (s.destination) p.destination = s.destination;
  if (s.start_date) p.travel_date = s.start_date;
  if (s.num_days) p.num_days = String(s.num_days);
  if (s.num_people) p.num_people = String(s.num_people);
  if (s.travel_mode) p.travel_mode = s.travel_mode as TravelMode;
  return p;
}

interface Props {
  draft: TripDraft;
  patch: (p: Partial<TripDraft>) => void;
  /** Move the whole flow on to fetching places. Takes the patch the chat just
   *  applied, because the `draft` prop is still the pre-patch one on the tick
   *  a reply lands — the panel merges it before building the planner input. */
  onNext: (override?: Partial<TripDraft>) => void;
  busy?: boolean;
  sessionId: string | null;
  onSessionId: (id: string | null) => void;
  /** a plan is already on screen: the chat stops driving itself forward, so
   *  asking a question here can't restart the flow under the traveller.
   *  Re-planning is the form's job. */
  planned?: boolean;
  /** the plan on screen — sent with each turn so the assistant can offer to
   *  change it (e.g. "recommend premium stays") instead of only talking about it */
  itinerary?: ItineraryStop[];
  itineraryStays?: ItineraryStayFood[];
  /** the traveller agreed to a stay change — hand the replacement to the page */
  onStaysPatch?: (stays: ItineraryStayFood[]) => void;
  /** where the trip starts, so a re-planned itinerary can be ordered from it */
  sourceGeo?: { lat: number; lon: number };
  /** the traveller added or removed a place — hand back the re-planned days */
  onItineraryPatch?: (patch: NonNullable<ChatResponse["itinerary_patch"]>) => void;
}

/** Only the fields whose value genuinely differs from the shared draft. The
 *  backend echoes every known slot back on each turn, so without this every
 *  reply would look like a change and keep re-triggering the next step. */
function changedFields(d: TripDraft, p: Partial<TripDraft>): Partial<TripDraft> {
  const out: Partial<TripDraft> = {};
  for (const k of Object.keys(p) as (keyof TripDraft)[]) {
    if (p[k] !== undefined && p[k] !== d[k]) out[k] = p[k] as never;
  }
  return out;
}

interface Msg {
  role: "assistant" | "user";
  text: string;
}

export function TripChat({
  draft, patch, onNext, busy = false, sessionId, onSessionId, planned = false,
  itinerary = [], itineraryStays = [], onStaysPatch, sourceGeo, onItineraryPatch,
}: Props) {
  // opening line adapts to whatever the Form tab may already hold
  const greeting = useMemo<Msg>(() => {
    if (planned) {
      return {
        role: "assistant",
        text: "Your plan is ready 🎉 Want anything changed — more days, a different date, another way of travelling? Tell me and I'll redo it.",
      };
    }
    if (draft.source && draft.destination) {
      return {
        role: "assistant",
        text: `Looks like you're going from ${draft.source} to ${draft.destination}. Tell me anything that's still missing — days, people, when you're going — and I'll take it from there.`,
      };
    }
    if (draft.destination) {
      return {
        role: "assistant",
        text: `Heading to ${draft.destination}? Tell me where you're starting from, when, for how many days and how many of you.`,
      };
    }
    return {
      role: "assistant",
      text: "Hey there! 👋 Where are we headed? Tell me your starting point, your destination, when you'd like to travel, how many days and how many people — a single sentence is all I need, and I'll ask about anything you leave out.",
    };
    // greeting is fixed for the life of the component; draft changes shouldn't rewrite it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // `turns` = the persisted transcript from the backend; the greeting is a
  // client-only prefix that is always shown on top.
  const [turns, setTurns] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  /** the backend's own verdict on whether every slot the planner needs is
   *  filled — the chat keeps asking until this flips true */
  const [ready, setReady] = useState(false);

  /** the assistant is waiting on an answer before it changes anything */
  const [pending, setPending] = useState<PendingAction | null>(null);
  /** day options ticked so far, for a question that accepts several */
  const [pickedDays, setPickedDays] = useState<string[]>([]);

  /** has this conversation already pushed the flow on to fetching places?
   *  Starts true when a plan is already on screen, so re-opening the chat to
   *  ask a question doesn't yank the user back into the stop picker. */
  const advanced = useRef(planned);

  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const messages = useMemo<Msg[]>(() => [greeting, ...turns], [greeting, turns]);

  // coming back to the Chat tab? pull the existing transcript from the backend
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    getChatHistory(sessionId)
      .then((res) => {
        if (cancelled) return;
        setTurns(res.messages);
        setReady(res.ready_to_plan);
        const p = changedFields(draft, slotsToDraftPatch(res.slots));
        if (Object.keys(p).length) patch(p);
      })
      .catch(() => onSessionId(null));
    return () => {
      cancelled = true;
    };
    // once, on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useLayoutEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  useLayoutEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }, [input]);

  async function send(override?: string) {
    const text = (override ?? input).trim();
    if (!text || sending || busy) return;

    setTurns((t) => [...t, { role: "user", text }]); // optimistic
    if (!override) setInput("");
    setSending(true);
    try {
      const res = await sendChat({
        session_id: sessionId,
        message: text,
        known: draftToKnown(draft),
        // only meaningful once a plan exists; the backend ignores it otherwise
        itinerary,
        itinerary_stays: itineraryStays,
        source_geo: sourceGeo,
      });
      onSessionId(res.session_id);
      setTurns(res.messages); // authoritative transcript from the backend
      setReady(res.ready_to_plan);

      // The assistant is waiting on a decision before it touches the plan.
      setPending(res.pending_action ?? null);
      setPickedDays([]);   // a fresh question starts with nothing ticked
      // ...and these are the changes the traveller asked for.
      if (res.stays_patch) onStaysPatch?.(res.stays_patch);
      if (res.itinerary_patch) onItineraryPatch?.(res.itinerary_patch);

      const p = changedFields(draft, slotsToDraftPatch(res.slots));
      if (Object.keys(p).length) patch(p);

      // The chat runs the same flow the form does: once it has every answer
      // it moves straight on to fetching places, instead of leaving the user
      // looking for a button. It re-fires only when something actually
      // changed — otherwise a follow-up question would restart the step.
      if (res.ready_to_plan && !planned && (!advanced.current || Object.keys(p).length > 0)) {
        advanced.current = true;
        onNext(p); // `draft` is still pre-patch here — hand the new values over
      }
    } catch (err) {
      const msg = apiErrorMessage(err, "The assistant didn't respond.");
      toast.error(msg);
      setTurns((t) => [...t, { role: "assistant", text: `⚠️ ${msg}` }]);
    } finally {
      setSending(false);
      taRef.current?.focus();
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const checklist = [
    { label: "From", value: draft.source || null },
    { label: "To", value: draft.destination || null },
    { label: "Date", value: draft.travel_date || null },
    { label: "Days", value: draft.num_days ? `${draft.num_days} days` : null },
    { label: "People", value: draft.num_people ? `${draft.num_people} people` : null },
    {
      label: "Travel by",
      value: draft.travel_mode === "own_vehicle" ? "Own vehicle" : "Public transport",
    },
  ];
  const anyKnown = checklist.some((c) => c.label !== "Travel by" && c.value);

  return (
    <div className="flex h-[26rem] flex-col">
      <div ref={scrollRef} className="flex-1 space-y-2.5 overflow-y-auto pr-1">
        {messages.map((m, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
          >
            <div
              className={cn(
                "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm",
                m.role === "user"
                  ? "rounded-br-md bg-brand-500 text-white"
                  : "rounded-bl-md bg-cream text-ink ring-1 ring-inset ring-ink/5",
              )}
            >
              {m.text}
            </div>
          </motion.div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-md bg-cream px-3.5 py-2.5 ring-1 ring-inset ring-ink/5">
              {[0, 1, 2].map((d) => (
                <motion.span
                  key={d}
                  className="h-1.5 w-1.5 rounded-full bg-ink-faint"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 1, repeat: Infinity, delay: d * 0.15 }}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* what the conversation has captured so far — the same shared draft the
          Form tab edits, so switching tabs shows the identical trip */}
      <AnimatePresence>
        {(anyKnown || ready) && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-2 overflow-hidden"
          >
            <div className="rounded-2xl bg-teal-100/70 p-3 ring-1 ring-inset ring-teal-500/20">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-teal-700">
                <Sparkles className="h-3.5 w-3.5" />
                {ready ? "Got everything I need" : "So far I have"}
              </p>

              <div className="mt-2 flex flex-wrap gap-1.5">
                {checklist.map((c) => (
                  <span
                    key={c.label}
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold",
                      c.value
                        ? "bg-paper text-ink-soft ring-1 ring-inset ring-ink/10"
                        : "bg-paper/60 text-ink-faint ring-1 ring-inset ring-dashed ring-ink/10",
                    )}
                  >
                    {c.value ? (
                      <Check className="h-3 w-3 text-teal-600" />
                    ) : (
                      <CircleDashed className="h-3 w-3" />
                    )}
                    {c.value ?? c.label}
                  </span>
                ))}
              </div>

              {/* No re-plan button here. Re-planning belongs to the form's
                  Next, which now decides for itself whether a change is
                  material (see lib/planDiff.ts) — a second, blunter trigger
                  sitting in the middle of a conversation about hotels was
                  just an invitation to redo the whole trip by accident. */}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* The assistant has asked how far to apply a change and is holding the
          plan until it hears back. One tap answers it — typing works just as
          well, but the options make the scope unmistakable, which matters
          when the alternative is rewriting the wrong night's hotel. */}
      <AnimatePresence>
        {pending && !sending && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-2 overflow-hidden"
          >
            {/* Per-day options are TICK-BOXES, not one-of buttons: wanting
                nights 1 and 2 is entirely normal, and single-select forced the
                traveller to ask again for each night. "The whole trip" and
                "No need" stay single-shot — they answer the question outright. */}
            <div className="flex flex-wrap items-center gap-1.5">
              {pending.options.map((opt) => {
                const isDay = /^day\s*\d+$/i.test(opt.trim());
                if (!isDay) {
                  return (
                    <button
                      key={opt}
                      disabled={busy || sending}
                      onClick={() => {
                        setPickedDays([]);
                        send(opt);
                      }}
                      className={cn(
                        "rounded-full border px-3 py-1.5 text-xs font-bold transition disabled:opacity-40",
                        opt.toLowerCase().startsWith("no")
                          ? "border-ink/10 text-ink-soft hover:border-ink/25 hover:text-ink"
                          : "border-brand-300 bg-brand-50 text-brand-700 hover:bg-brand-100",
                      )}
                    >
                      {opt}
                    </button>
                  );
                }
                const on = pickedDays.includes(opt);
                return (
                  <button
                    key={opt}
                    disabled={busy || sending}
                    aria-pressed={on}
                    onClick={() =>
                      setPickedDays((cur) =>
                        cur.includes(opt) ? cur.filter((d) => d !== opt) : [...cur, opt],
                      )
                    }
                    className={cn(
                      "flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-bold transition disabled:opacity-40",
                      on
                        ? "border-brand-500 bg-brand-500 text-white"
                        : "border-brand-300 bg-brand-50 text-brand-700 hover:bg-brand-100",
                    )}
                  >
                    {on && <Check className="h-3 w-3" />}
                    {opt}
                  </button>
                );
              })}

              {pickedDays.length > 0 && (
                <button
                  disabled={busy || sending}
                  onClick={() => {
                    const nums = pickedDays
                      .map((d) => d.replace(/\D+/g, ""))
                      .sort((a, b) => Number(a) - Number(b));
                    setPickedDays([]);
                    send(nums.length === 1 ? `day ${nums[0]}` : `days ${nums.join(", ")}`);
                  }}
                  className="rounded-full bg-brand-gradient px-3 py-1.5 text-xs font-extrabold text-white transition hover:shadow-soft disabled:opacity-40"
                >
                  Apply to {pickedDays.length} night{pickedDays.length === 1 ? "" : "s"}
                </button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-2 flex items-end gap-2 rounded-2xl bg-cream p-2 ring-1 ring-inset ring-ink/10 focus-within:ring-2 focus-within:ring-brand-400">
        <textarea
          ref={taRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Where from, where to, and when…"
          disabled={busy}
          className="max-h-[140px] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink outline-none placeholder:text-ink-faint"
        />
        {/* `() => send()`, not `send`: send() now takes an optional message,
            and React would otherwise hand it the click event as that argument */}
        <button
          onClick={() => send()}
          disabled={!input.trim() || sending || busy}
          className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-500 text-white transition hover:bg-brand-600 disabled:opacity-40"
          aria-label="Send"
        >
          {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizonal className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}
