import { createBrowserRouter } from "react-router";
import { Root } from "./pages/root";
import { Dashboard } from "./pages/dashboard";
import { Findings } from "./pages/findings";
import { Fix } from "./pages/fix";
import { Verify } from "./pages/verify";
import { Leaderboard } from "./pages/leaderboard";
import { AttackPathsPage } from "./pages/attack-paths";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Root,
    children: [
      { index: true, Component: Dashboard },
      { path: "findings", Component: Findings },
      { path: "fix", Component: Fix },
      { path: "verify", Component: Verify },
      { path: "leaderboard", Component: Leaderboard },
      { path: "org-findings/:orgJobId", Component: OrgFindings },
    ],
  },
]);
