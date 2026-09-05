import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Eye, EyeOff, Loader2, Mail, Lock, User as UserIcon } from "lucide-react";
import toast from "react-hot-toast";

import { login as loginReq, signup as signupReq } from "@/api/auth";
import { apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/cn";

type Mode = "signin" | "signup";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function AuthForm() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = (location.state as { from?: string } | null)?.from ?? "/app";

  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);

  const isSignup = mode === "signup";

  function validate(): string | null {
    if (!EMAIL_RE.test(email.trim())) return "Enter a valid email address.";
    if (isSignup && name.trim().length < 1) return "Tell us your name.";
    if (password.length < 6) return "Password needs at least 6 characters.";
    return null;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const err = validate();
    setFieldError(err);
    if (err) return;

    setBusy(true);
    try {
      const res = isSignup
        ? await signupReq({ email: email.trim(), name: name.trim(), password })
        : await loginReq({ email: email.trim(), password });
      signIn(res.token, res.user);
      toast.success(isSignup ? `Welcome aboard, ${res.user.name}!` : `Welcome back, ${res.user.name}!`);
      navigate(redirectTo, { replace: true });
    } catch (err2) {
      const msg = apiErrorMessage(err2, "Could not sign you in.");
      setFieldError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setFieldError(null);
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="card w-full max-w-sm p-7 sm:p-8"
    >
      {/* mode toggle */}
      <div className="mb-6 grid grid-cols-2 gap-1 rounded-2xl border-2 border-ink/10 bg-cream p-1">
        {(["signin", "signup"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => switchMode(m)}
            className={cn(
              "relative rounded-lg px-3 py-2 text-sm font-semibold transition-colors",
              mode === m ? "text-white" : "text-ink-soft hover:text-ink",
            )}
          >
            {mode === m && (
              <motion.span
                layoutId="auth-toggle-pill"
                className="absolute inset-0 rounded-xl bg-brand-500 shadow-chunky-sm"
                transition={{ type: "spring", stiffness: 400, damping: 32 }}
              />
            )}
            <span className="relative z-10">{m === "signin" ? "Sign in" : "Create account"}</span>
          </button>
        ))}
      </div>

      <h2 className="font-display text-2xl font-bold">
        {isSignup ? "Start planning" : "Welcome back"}
      </h2>
      <p className="mt-1 text-sm text-ink-soft">
        {isSignup ? "Your trips and history live in your account." : "Sign in to see your plans and history."}
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
        <Field icon={<Mail className="h-4 w-4" />} >
          <input
            className="input pl-10"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
          />
        </Field>

        <AnimatePresence initial={false}>
          {isSignup && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.25 }}
              className="overflow-hidden"
            >
              <Field icon={<UserIcon className="h-4 w-4" />}>
                <input
                  className="input pl-10"
                  type="text"
                  autoComplete="name"
                  placeholder="Your name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={busy}
                />
              </Field>
            </motion.div>
          )}
        </AnimatePresence>

        <Field icon={<Lock className="h-4 w-4" />}>
          <input
            className="input pl-10 pr-10"
            type={showPw ? "text" : "password"}
            autoComplete={isSignup ? "new-password" : "current-password"}
            placeholder={isSignup ? "Create a password" : "Your password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
          <button
            type="button"
            onClick={() => setShowPw((s) => !s)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink"
            tabIndex={-1}
            aria-label={showPw ? "Hide password" : "Show password"}
          >
            {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </Field>

        {fieldError && (
          <motion.p
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-lg bg-brand-50 px-3 py-2 text-xs font-medium text-brand-700"
          >
            {fieldError}
          </motion.p>
        )}

        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          {isSignup ? "Create account" : "Sign in"}
        </button>
      </form>

      <p className="mt-5 text-center text-xs text-ink-faint">
        {isSignup ? "Already have an account? " : "New here? "}
        <button
          type="button"
          className="font-semibold text-brand-600 hover:underline"
          onClick={() => switchMode(isSignup ? "signin" : "signup")}
        >
          {isSignup ? "Sign in" : "Create one"}
        </button>
      </p>
    </motion.div>
  );
}

function Field({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
        {icon}
      </span>
      {children}
    </div>
  );
}
