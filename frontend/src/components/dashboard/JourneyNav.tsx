import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useScroll, useSpring } from "framer-motion";
import { ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";

export interface JourneySection {
  id: string;
  label: string;
  icon: LucideIcon;
}

/** px of sticky chrome above the content — keep in sync with --nav-offset. */
const NAV_OFFSET = 132;

/**
 * The journey rail: a sticky, scroll-spying tab bar that lets you hop
 * straight to any part of a plan instead of hunting for it by scrolling.
 * Pills hug the left and size to their label — no stretching across the
 * full width — with arrows to step section-by-section and a thin
 * page-progress underline along the bottom edge.
 */
export function JourneyNav({ sections }: { sections: JourneySection[] }) {
  const [activeId, setActiveId] = useState(sections[0]?.id ?? "");
  const [showTop, setShowTop] = useState(false);
  const railRef = useRef<HTMLDivElement>(null);

  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, {
    stiffness: 140,
    damping: 28,
    restDelta: 0.001,
  });

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
      // bottomed out? whatever's last is what you're actually looking at
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

  // ---- keep the active pill in view without disturbing page scroll
  useEffect(() => {
    const rail = railRef.current;
    const pill = rail?.querySelector<HTMLElement>(`[data-pill="${activeId}"]`);
    if (!rail || !pill) return;
    pill.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
  }, [activeId]);

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

  return (
    <>
      <div className="sticky top-[4.25rem] z-30 mb-4">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="glass relative flex items-center gap-1 overflow-hidden rounded-2xl p-1.5"
        >
          {/* page-progress underline */}
          <motion.span
            aria-hidden
            className="absolute inset-x-0 bottom-0 h-[2px] origin-left rounded-full bg-sunset"
            style={{ scaleX: progress }}
          />

          <RailArrow
            label="Previous section"
            disabled={index === 0}
            onClick={() => go(ids[index - 1])}
          >
            <ChevronLeft className="h-4 w-4" />
          </RailArrow>

          <div
            ref={railRef}
            className="no-bar rail-mask flex flex-1 justify-center gap-1 overflow-x-auto scroll-smooth"
          >
            {sections.map((s) => {
              const on = s.id === activeId;
              const Icon = s.icon;
              return (
                <button
                  key={s.id}
                  data-pill={s.id}
                  onClick={() => go(s.id)}
                  aria-current={on ? "true" : undefined}
                  className={cn(
                    "relative shrink-0 rounded-xl px-3 py-2 text-xs font-bold transition-colors duration-200",
                    on ? "text-white" : "text-ink-soft hover:text-ink",
                  )}
                >
                  {on && (
                    <motion.span
                      layoutId="journey-pill"
                      className="absolute inset-0 rounded-xl bg-brand-gradient shadow-soft"
                      transition={{ type: "spring", stiffness: 420, damping: 36 }}
                    />
                  )}
                  <span className="relative z-10 flex items-center gap-1.5 whitespace-nowrap">
                    <Icon className="h-3.5 w-3.5" />
                    {s.label}
                  </span>
                </button>
              );
            })}
          </div>

          <RailArrow
            label="Next section"
            disabled={index === ids.length - 1}
            onClick={() => go(ids[index + 1])}
          >
            <ChevronRight className="h-4 w-4" />
          </RailArrow>
        </motion.div>
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
      className="grid h-8 w-8 shrink-0 place-items-center rounded-xl text-ink-soft transition hover:bg-ink/[0.05] hover:text-ink disabled:opacity-25 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  );
}
