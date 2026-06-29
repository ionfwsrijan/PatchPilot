import { createBrowserRouter } from "react-router";
import { Root } from "./pages/root";
import { Landing } from "./pages/landing";
import { Dashboard } from "./pages/dashboard";
import { Findings } from "./pages/findings";
import { Fix } from "./pages/fix";
import { Verify } from "./pages/verify";
import { Leaderboard } from "./pages/leaderboard";
import { OrgFindings } from "./pages/org-findings";

export const router = createBrowserRouter([
  { path: "/", Component: Landing },
  {
    Component: Root,
    children: [
      { path: "/dashboard", Component: Dashboard },
      { path: "findings", Component: Findings },
      { path: "fix", Component: Fix },
      { path: "verify", Component: Verify },
      { path: "leaderboard", Component: Leaderboard },
      { path: "org-findings/:orgJobId", Component: OrgFindings },
    ],
  },
]);
