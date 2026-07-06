import { Link, useLocation } from "react-router-dom";
import {
  BarChart3,
  FileSearch,
  Home,
  Menu,
  Moon,
  ShieldCheck,
  Sun,
  Trophy,
  Wrench,
  X,
} from "lucide-react";
import { Button } from "./ui/button";
import { cn } from "./ui/utils";
import { useTheme } from "./theme-provider";
import { useOllamaStatus } from "../hooks/useOllamaStatus";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: Home },
  { to: "/findings", label: "Findings", icon: FileSearch },
  { to: "/fix", label: "Fixes", icon: Wrench },
  { to: "/verify", label: "Verify", icon: ShieldCheck },
  { to: "/leaderboard", label: "Leaderboard", icon: Trophy },
];

function OllamaStatusIndicator({ compact = false }: { compact?: boolean }) {
  const { status, loading } = useOllamaStatus();

  if (loading) return null;

  const isConnected = status?.available;
  const label = isConnected ? "Ollama Connected" : "Ollama Offline";
  const tooltipText = isConnected
    ? `Ollama connected (${status.models.length > 0 ? status.models[0] : "no models loaded"})`
    : "Ollama is not running. Install Ollama and pull qwen2.5-coder:7b to enable AI patches.";

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button className="flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
            <span
              className={cn(
                "h-2.5 w-2.5 shrink-0 rounded-full",
                isConnected ? "bg-status-success" : "bg-destructive",
              )}
            />
            {!compact && <span className="truncate">{label}</span>}
          </button>
        </TooltipTrigger>
        <TooltipContent side="right" className="max-w-64">
          {tooltipText}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function ThemeSwitch({ compact = false }: { compact?: boolean }) {
  const { theme, toggleTheme } = useTheme();
  const Icon = theme === "light" ? Moon : Sun;

  return (
    <Button
      variant="outline"
      onClick={toggleTheme}
      className="h-10 w-full justify-start px-3"
    >
      <Icon className="h-4 w-4" />
      {!compact && <span>{theme === "light" ? "Dark mode" : "Light mode"}</span>}
      <span className="sr-only">Toggle theme</span>
    </Button>
  );
}

function SidebarContent({
  compact = false,
  onNavigate,
}: {
  compact?: boolean;
  onNavigate?: () => void;
}) {
  const location = useLocation();

  const isActive = (path: string) =>
    path === "/dashboard"
      ? location.pathname === "/dashboard"
      : location.pathname.startsWith(path);

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center px-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
          <BarChart3 className="h-5 w-5" />
        </div>
        {!compact && (
          <span className="ml-3 text-sm font-semibold text-muted-foreground">
            Workspace
          </span>
        )}
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-3 py-4">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.to}
              to={item.to}
              onClick={onNavigate}
              className={cn(
                "group/link flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
                isActive(item.to)
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
              title={compact ? item.label : undefined}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!compact && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="space-y-2 border-t border-border p-3">
        <OllamaStatusIndicator compact={compact} />
        <ThemeSwitch compact={compact} />
      </div>
    </div>
  );
}

export function AppSidebar({
  mobileOpen,
  onMobileOpenChange,
}: {
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
}) {
  return (
    <>
      <aside className="group/sidebar fixed inset-y-0 left-0 z-40 hidden w-20 overflow-hidden border-r border-border bg-card transition-[width] duration-300 ease-out hover:w-64 md:block">
        <div className="w-64">
          <SidebarContent compact />
        </div>
        <div className="absolute inset-0 w-64 opacity-0 transition-opacity duration-200 group-hover/sidebar:opacity-100">
          <SidebarContent />
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            aria-label="Close sidebar"
            className="absolute inset-0 bg-black/60"
            onClick={() => onMobileOpenChange(false)}
          />
          <aside className="relative h-full w-72 border-r border-border bg-card shadow-xl">
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-3 top-3"
              onClick={() => onMobileOpenChange(false)}
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Close sidebar</span>
            </Button>
            <SidebarContent onNavigate={() => onMobileOpenChange(false)} />
          </aside>
        </div>
      )}
    </>
  );
}

export function AppTopBar({
  onMenuClick,
}: {
  onMenuClick: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 h-16 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="relative flex h-full items-center justify-center px-4">
        <Button
          variant="ghost"
          size="icon"
          className="absolute left-4 md:hidden"
          onClick={onMenuClick}
        >
          <Menu className="h-5 w-5" />
          <span className="sr-only">Open sidebar</span>
        </Button>
        <div className="text-xl font-semibold tracking-tight">PatchPilot</div>
      </div>
    </header>
  );
}
