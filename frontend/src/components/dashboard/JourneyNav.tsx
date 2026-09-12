import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";

export interface JourneySection {
  id: string;
  label: string;
  icon: LucideIcon;
}

/** px of sticky chrome above the content - keep in sync with --nav-offset. */
const NAV_OFFSET = 142;

/**
 * The journey rail, drawn as the journey it describes: a track of stops, with
 * the one you are reading marked, the ones behind it filled in, and the ones
 * ahead still hollow.
 *
 * WHY A STEPPER AND NOT A ROW OF TABS
 * -----------------------------------
 * The tab version rendered every label at every width - nine pills came to
 * ~940px of content inside a 375px phone, so it degraded into a horizontal
 * scroller showing three items at a time. Worse, that row was BOTH
 * `justify-center` and `overflow-x-auto`: centring an overflowing flex row
 * leaves the leading items unreachable by scrolling in WebKit, so "Plan" was
 * simply unavailable on a phone.
 *
 * Nodes are small enough that nine fit any screen with room to spare (~250px
 * on mobile), so there is no scroller left to get wrong - the overflow problem
 * is removed rather than managed. Labels ride under every node from `sm` up;
 * on a phone only the active one is named, with a "3 of 9" to place you.
 *
 * Each dot is 10px, but its button is padded to a ~40px tap target - a 10px
 * touch target is not a target.
 */
export function JourneyNav({ sections }: { sections: JourneySection[] }) {
  const [activeId, setActiveId] = useState(sections[0]?.id ?? "");
  const [showTop, setShowTop] = useState(false);

  const ids = useMemo(() => sections.map((s) => s.id), [sections]);

  // ---- scroll spy: the last section whose top has slipped under the chrome
  useEffect(() => {
    if (ids.length === 0) return;
    let frame = 0;

    const measure = () => {
      frame = 0;
      let current = ids[0];
      for (const id of ids) {
        const el = document.getElementById(id);
        if (!el) continue;
        if (el.getBoundingClientRect().top - NAV_OFFSET <= 12) current = id;
      }
      // bottomed out? whatever is last is what you are actually looking at
      if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 6) {
        current = ids[ids.length - 1];
      }
      setActiveId(current);
      setShowTop(window.scrollY > 520);
    };

    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };

    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [ids]);

  const go = useCallback((id?: string) => {
    if (!id) return;
    const el = document.getElementById(id);
    if (!el) return;
    window.scrollTo({
      top: el.getBoundingClientRect().top + window.scrollY - NAV_OFFSET,
      behavior: "smooth",
    });
  }, []);

  const index = Math.max(0, ids.indexOf(activeId));
  if (sections.length < 2) return null;

  const active = sections[index];
  // How far along the track the filled line reaches. Nodes sit at the centres
  // of equal-width columns, so the first and last are inset by half a column -
  // the line spans between those two centres, not the full width.
  const half = 100 / sections.length / 2;
  const span = 100 - half * 2;
  const fillPct = sections.length > 1 ? (index / (sections.length - 1)) * span : 0;

  return (
    <>
      <div className="sticky top-[4.25rem] z-30 mb-4">
        <motion.nav
          aria-label="Jump to a part of your plan"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="glass relative flex items-start gap-1 rounded-2xl px-1.5 py-2 sm:px-2.5"
        >
          <RailArrow
            label="Previous section"
            disabled={index === 0}
            onClick={() => go(ids[index - 1])}
          >
            <ChevronLeft className="h-4 w-4" />
          </RailArrow>

          <div className="relative min-w-0 flex-1">
            {/* the track: a hairline all the way, filled up to where you are */}
            <span
              aria-hidden
              className="absolute top-[13px] h-[3px] -translate-y-1/2 rounded-full bg-ink/10"
              style={{ left: `${half}%`, width: `${span}%` }}
            />
            <motion.span
              aria-hidden
              className="absolute top-[13px] h-[3px] -translate-y-1/2 rounded-full bg-sunset"
              style={{ left: `${half}%` }}
              initial={false}
              animate={{ width: `${fillPct}%` }}
              transition={{ type: "spring", stiffness: 220, damping: 30 }}
            />

            <ol className="relative flex items-start">
              {sections.map((s, i) => {
                const on = s.id === activeId;
                const done = i < index;
                const Icon = s.icon;
                return (
                  <li key={s.id} className="flex min-w-0 flex-1 justify-center">
                    <button
                      onClick={() => go(s.id)}
                      aria-current={on ? "true" : undefined}
                      aria-label={s.label}
                      title={s.label}
                      className="group flex min-w-0 flex-col items-center px-0.5 pb-1 pt-[3px]"
                    >
                      {/* the node itself */}
                      <span className="grid h-5 w-5 shrink-0 place-items-center">
                        {on ? (
                          <motion.span
                            layoutId="journey-node"
                            className="grid h-5 w-5 place-items-center rounded-full bg-brand-gradient text-white shadow-soft ring-2 ring-paper"
                            transition={{ type: "spring", stiffness: 420, damping: 34 }}
                          >
                            <Icon className="h-2.5 w-2.5" />
                          </motion.span>
                        ) : (
                          <span
                            className={cn(
                              "h-2.5 w-2.5 rounded-full transition-all duration-200",
                              done
                                ? "bg-brand-400 group-hover:scale-125"
                                : "bg-paper ring-2 ring-inset ring-ink/20 group-hover:ring-brand-400",
                            )}
                          />
                        )}
                      </span>

                      {/* labels ride under the nodes from sm up; on a phone the
                          active one is named below the track instead */}
                      <span
                        className={cn(
                          "mt-1 hidden w-full truncate text-center text-[10px] font-bold leading-none transition-colors sm:block lg:text-[11px]",
                          on ? "text-brand-700" : "text-ink-faint group-hover:text-ink-soft",
                        )}
                      >
                        {s.label}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>

            {/* phone only: the dots carry no labels, so say where you are */}
            <p className="mt-1 flex items-center justify-center gap-1.5 text-[11px] font-bold leading-none sm:hidden">
              <span className="text-brand-700">{active?.label}</span>
              <span className="text-ink-faint">
                {index + 1} of {sections.length}
              </span>
            </p>
          </div>

          <RailArrow
            label="Next section"
            disabled={index === ids.length - 1}
            onClick={() => go(ids[index + 1])}
          >
            <ChevronRight className="h-4 w-4" />
          </RailArrow>
        </motion.nav>
      </div>

      {/* back to the top of the plan */}
      <AnimatePresence>
        {showTop && (
          <motion.button
            key="to-top"
            initial={{ opacity: 0, scale: 0.7, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.7, y: 12 }}
            transition={{ type: "spring", stiffness: 380, damping: 26 }}
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            aria-label="Back to top"
            className="glass fixed bottom-5 right-5 z-30 grid h-11 w-11 place-items-center rounded-2xl text-ink-soft transition hover:text-brand-600 hover:shadow-lift"
          >
            <ArrowUp className="h-4 w-4" />
          </motion.button>
        )}
      </AnimatePresence>
    </>
  );
}

function RailArrow({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-ink-soft transition hover:bg-ink/[0.05] hover:text-ink disabled:opacity-25 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  );
}
