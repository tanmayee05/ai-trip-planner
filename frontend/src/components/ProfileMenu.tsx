import { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { LogOut, ChevronDown } from "lucide-react";
import toast from "react-hot-toast";

import { useAuth } from "@/context/AuthContext";
import { useClickOutside } from "@/hooks/useClickOutside";
import { cn } from "@/lib/cn";

function initials(name: string) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

export function ProfileMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);

  if (!user) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex items-center gap-2 rounded-full py-1 pl-1 pr-2.5 transition",
          "ring-1 ring-ink/10 hover:ring-ink/20 hover:shadow-soft",
          open && "ring-brand-300 shadow-glow",
        )}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="grid h-8 w-8 place-items-center rounded-full bg-brand-gradient text-xs font-bold text-white">
          {initials(user.name) || "?"}
        </span>
        <span className="hidden text-sm font-semibold text-ink sm:block">
          {user.name.split(/\s+/)[0]}
        </span>
        <ChevronDown
          className={cn("h-4 w-4 text-ink-faint transition-transform", open && "rotate-180")}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, scale: 0.95, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -6 }}
            transition={{ type: "spring", stiffness: 420, damping: 30 }}
            className="absolute right-0 z-50 mt-2 w-60 origin-top-right overflow-hidden rounded-2xl bg-paper shadow-lift ring-1 ring-ink/10"
          >
            <div className="border-b border-ink/5 bg-cream/60 px-4 py-3">
              <p className="truncate text-sm font-semibold text-ink">{user.name}</p>
              <p className="truncate text-xs text-ink-faint">{user.email}</p>
            </div>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                signOut();
                toast("Signed out");
              }}
              className="flex w-full items-center gap-2.5 px-4 py-3 text-sm font-medium text-ink-soft transition hover:bg-brand-50 hover:text-brand-700"
            >
              <LogOut className="h-4 w-4" />
              Log out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
