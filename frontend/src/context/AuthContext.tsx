import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { fetchMe } from "@/api/auth";
import { setUnauthorizedHandler, tokenStore } from "@/lib/api";
import type { User } from "@/types/api";

interface AuthContextValue {
  user: User | null;
  status: "loading" | "authenticated" | "anonymous";
  /** Call after a successful signup/login response. */
  signIn: (token: string, user: User) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");
  const bootstrapped = useRef(false);

  const signIn = useCallback((token: string, nextUser: User) => {
    tokenStore.set(token);
    setUser(nextUser);
    setStatus("authenticated");
  }, []);

  const signOut = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setStatus("anonymous");
  }, []);

  // If a 401 slips through anywhere, drop back to the login screen.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setStatus("anonymous");
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  // On first load: if we have a stored token, verify it with /auth/me.
  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    const token = tokenStore.get();
    if (!token) {
      setStatus("anonymous");
      return;
    }
    fetchMe()
      .then((me) => {
        setUser(me);
        setStatus("authenticated");
      })
      .catch(() => {
        tokenStore.clear();
        setStatus("anonymous");
      });
  }, []);

  const value = useMemo(
    () => ({ user, status, signIn, signOut }),
    [user, status, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
