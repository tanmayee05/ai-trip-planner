import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { SendHorizonal, Sparkles, Loader2, ArrowRight, RefreshCw } from "lucide-react";
import toast from "react-hot-toast";

import { sendChat, getChatHistory } from "@/api/chat";
import type { TripDraft } from "@/components/dashboard/TripRequestPanel";
import type { TravelMode } from "@/api/plan";
import type { TripSlots } from "@/types/api";
import { apiErrorMessage } from "@/lib/api";
import { todayISO } from "@/lib/format";
import { cn } from "@/lib/cn";

const CHAT_SESSION_KEY = "wayfarer.chat_session";

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
  onNext: () => void;
  canNext: boolean;
  busy?: boolean;
}

interface Msg {
  role: "assistant" | "user";
  text: string;
}

export function TripChat({ draft, patch, onNext, canNext, busy = false }: Props) {
  // opening line adapts to whatever the Form tab may already hold
  const greeting = useMemo<Msg>(() => {
    if (draft.source && draft.destination) {
      return {
        role: "assistant",
        text: `Looks like you're going from ${draft.source} to ${draft.destination}. Tell me anything else — dates, how many days, how you're travelling — or just hit Next.`,
      };
    }
    if (draft.destination) {
      return {
        role: "assistant",
        text: `Heading to ${draft.destination}? Tell me where you're starting from and roughly when.`,
      };
    }
    return {
      role: "assistant",
      text: "Hey there! 👋 Where are we headed? Just tell me your starting point, your destination, and roughly when you'd like to travel — a single sentence is all I need.",
    };
    // greeting is fixed for the life of the component; draft changes shouldn't rewrite it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // `turns` = the persisted transcript from the backend; the greeting is a
  // client-only prefix that is always shown on top.
  const [turns, setTurns] = useState<Msg[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(CHAT_SESSION_KEY);
    } catch {
      return null;
    }
  });
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const messages = useMemo<Msg[]>(() => [greeting, ...turns], [greeting, turns]);

  // on mount, if we have a stored session, pull its transcript from the backend
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    getChatHistory(sessionId)
      .then((res) => {
        if (cancelled) return;
        setTurns(res.messages);
        const p = slotsToDraftPatch(res.slots);
        if (Object.keys(p).length) patch(p);
      })
      .catch(() => {
        try {
          localStorage.removeItem(CHAT_SESSION_KEY);
        } catch {
          /* ignore */
        }
        setSessionId(null);
      });
    return () => {
      cancelled = true;
    };
    // once, on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function newChat() {
    try {
      localStorage.removeItem(CHAT_SESSION_KEY);
    } catch {
      /* ignore */
    }
    setSessionId(null);
    setTurns([]);
  }

  useLayoutEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  useLayoutEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }, [input]);

  async function send() {
    const text = input.trim();
    if (!text || sending || busy) return;

    setTurns((t) => [...t, { role: "user", text }]); // optimistic
    setInput("");
    setSending(true);
    try {
      const res = await sendChat({ session_id: sessionId, message: text });
      setSessionId(res.session_id);
      try {
        localStorage.setItem(CHAT_SESSION_KEY, res.session_id);
      } catch {
        /* ignore */
      }
      setTurns(res.messages); // authoritative transcript from the backend

      const p = slotsToDraftPatch(res.slots);
      if (Object.keys(p).length) patch(p);
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

  const ready = !!(draft.source && draft.destination);

  return (
    <div className="flex h-[26rem] flex-col">
      {turns.length > 0 && (
        <div className="mb-2 flex justify-end">
          <button
            onClick={newChat}
            disabled={busy || sending}
            className="flex items-center gap-1 text-[11px] font-medium text-ink-faint hover:text-ink"
          >
            <RefreshCw className="h-3 w-3" /> New chat
          </button>
        </div>
      )}
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

      {/* shared-draft summary + Next */}
      <AnimatePresence>
        {ready && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-2 overflow-hidden"
          >
            <div className="rounded-2xl bg-teal-100/70 p-3 ring-1 ring-inset ring-teal-500/20">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-teal-700">
                <Sparkles className="h-3.5 w-3.5" /> {draft.source} → {draft.destination}
              </p>
              <div className="mt-2 flex items-end gap-2">
                <label className="flex-1">
                  <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-teal-700/80">
                    Travel date
                  </span>
                  <input
                    type="date"
                    className="input !bg-paper !py-2"
                    value={draft.travel_date || todayISO()}
                    min={todayISO()}
                    onChange={(e) => patch({ travel_date: e.target.value })}
                    disabled={busy}
                  />
                </label>
                <button className="btn-primary !py-2" disabled={busy || !canNext} onClick={onNext}>
                  Next <ArrowRight className="h-4 w-4" />
                </button>
              </div>
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
        <button
          onClick={send}
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
