import { Link, useLocation } from "react-router-dom";
import { Home, FileSearch, Wrench, ShieldCheck, Trophy } from "lucide-react";
import { cn } from "./ui/utils";
import { Button } from "./ui/button";
import { useTheme } from "./theme-provider";
import { Moon, Sun } from "lucide-react";

const navItems = [
  {
    label: "Dashboard",
    path: "/dashboard",
    icon: Home,
  },
  {
    label: "Findings",
    path: "/findings",
    icon: FileSearch,
  },
  {
    label: "Fixes",
    path: "/fix",
    icon: Wrench,
  },
  {
    label: "Verify",
    path: "/verify",
    icon: ShieldCheck,
  },
  {
    label: "Leaderboard",
    path: "/leaderboard",
    icon: Trophy,
  },
];

function ThemeSwitch() {
  const { theme, toggleTheme } = useTheme();

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      className="rounded-full"
    >
      {theme === "light" ? (
        <Moon className="h-5 w-5" />
      ) : (
        <Sun className="h-5 w-5" />
      )}
    </Button>
  );
}

export function AppNavbar() {
  const location = useLocation();

  return (
    <nav className="sticky top-16 z-20 border-b border-border bg-background/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 items-center justify-between px-6">

        {/* Left */}
        <div className="font-semibold text-sm tracking-wide">
          Navigation
        </div>

        {/* Center */}
        <div className="hidden md:flex items-center gap-2">
          {navItems.map((item) => {
            const Icon = item.icon;

            const active =
              item.path === "/dashboard"
                ? location.pathname === "/dashboard"
                : location.pathname.startsWith(item.path);

            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  "flex items-center gap-2 rounded-md px-4 py-2 text-sm transition-colors",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </div>

        {/* Right */}
        <ThemeSwitch />
      </div>
    </nav>
  );
}