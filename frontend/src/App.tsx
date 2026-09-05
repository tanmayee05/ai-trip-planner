import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { FullPageLoader } from "@/components/FullPageLoader";
import { WelcomePage } from "@/pages/WelcomePage";
import { DashboardPage } from "@/pages/DashboardPage";

export default function App() {
  const { status } = useAuth();

  if (status === "loading") return <FullPageLoader label="Starting Wayfarer…" />;

  return (
    <Routes>
      <Route
        path="/welcome"
        element={status === "authenticated" ? <Navigate to="/app" replace /> : <WelcomePage />}
      />

      <Route element={<ProtectedRoute />}>
        <Route path="/app" element={<DashboardPage />} />
      </Route>

      <Route
        path="*"
        element={<Navigate to={status === "authenticated" ? "/app" : "/welcome"} replace />}
      />
    </Routes>
  );
}
