import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { FullPageLoader } from "@/components/FullPageLoader";

/** Gate for /app/*. Sends anonymous visitors to the auth screen and
 *  remembers where they were headed. */
export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <FullPageLoader label="Checking your session…" />;
  if (status === "anonymous") {
    return <Navigate to="/welcome" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
