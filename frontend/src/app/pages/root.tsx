import { Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "../lib/api";
import { AppSidebar, AppTopBar } from "../components/app-sidebar";

export function Root() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(console.error);
  }, []);
  const unavailableScanners =
    health?.scanners
      ? Object.entries(health.scanners)
          .filter(([, available]) => !available)
          .map(([name]) => name)
      : [];

  return (
    <div className="min-h-screen bg-background">
      <AppSidebar
        mobileOpen={mobileSidebarOpen}
        onMobileOpenChange={setMobileSidebarOpen}
      />

      <div className="min-h-screen md:pl-20">
        <AppTopBar onMenuClick={() => setMobileSidebarOpen(true)} />

        {health?.status === "degraded" && (
          <div className="border-b border-yellow-300 bg-yellow-100 px-4 py-3 text-yellow-900">
            <p className="font-semibold">System is running in degraded mode.</p>
            <p>
              One or more scanners are unavailable. Scan results may be
              incomplete.
            </p>
            {unavailableScanners.length > 0 && (
              <p>Unavailable scanners: {unavailableScanners.join(", ")}</p>
            )}
          </div>
        )}

        <main className="min-h-[calc(100vh-4rem)]">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
