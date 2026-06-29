import { Link, useLocation } from "react-router";
import { Moon, Sun } from "lucide-react";
import { Button } from "./ui/button";
import { useTheme } from "./theme-provider";
import { cn } from "./ui/utils";
import { useOllamaStatus } from "../hooks/useOllamaStatus";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "./ui/tooltip";

function OllamaStatusIndicator() {
  const { status, loading } = useOllamaStatus();

  if (loading) return null;

  const isConnected = status?.available;
  const tooltipText = isConnected
    ? `Ollama connected (${status.models.length > 0 ? status.models[0] : "no models loaded"})`
    : "Ollama not running. Install Ollama and run: `ollama pull qwen2.5-coder:7b` to enable AI patches.";

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button className="flex items-center gap-2 rounded-full border border-border bg-muted/50 px-3 py-1.5 text-sm font-medium hover:bg-muted transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
            <div className="relative flex h-2.5 w-2.5 items-center justify-center">
              {isConnected ? (
                <>
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-20"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500"></span>
                </>
              ) : (
                <span className="relative inline-flex h-2 w-2 rounded-full bg-destructive"></span>
              )}
            </div>
            <span className={isConnected ? "text-foreground" : "text-muted-foreground"}>
              {isConnected ? "Ollama Connected" : "Ollama Offline"}
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent className="w-64 z-50">
          {tooltipText}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function Header() {
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();

  const isActive = (path: string) => location.pathname === path;

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/60">
      <div className="container mx-auto flex h-16 items-center px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-2">
          <Link to="/dashboard" className="flex items-center">
            <span className="text-xl font-semibold">PatchPilot</span>
          </Link>
        </div>

        <nav className="ml-8 hidden md:flex items-center gap-6">
          <Link
            to="/dashboard"
            className={cn(
              "text-sm font-medium transition-colors hover:text-primary",
              isActive("/dashboard") ? "text-foreground" : "text-muted-foreground",
            )}
          >
            Dashboard
          </Link>
          <Link
            to="/findings"
            className={cn(
              "text-sm font-medium transition-colors hover:text-primary",
              isActive("/findings")
                ? "text-foreground"
                : "text-muted-foreground",
            )}
          >
            Findings
          </Link>
          <Link
            to="/verify"
            className={cn(
              "text-sm font-medium transition-colors hover:text-primary",
              isActive("/verify") ? "text-foreground" : "text-muted-foreground",
            )}
          >
            Verify
          </Link>
          <Link
            to="/leaderboard"
            className={cn(
              "text-sm font-medium transition-colors hover:text-primary",
              isActive("/leaderboard") ? "text-foreground" : "text-muted-foreground",
            )}
          >
            Leaderboard
          </Link>
        </nav>

        <div className="ml-auto flex items-center gap-4">
          <OllamaStatusIndicator />
          
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleTheme}
            className="h-9 w-9 px-0"
          >
            {theme === "light" ? (
              <Moon className="h-4 w-4" />
            ) : (
              <Sun className="h-4 w-4" />
            )}
            <span className="sr-only">Toggle theme</span>
          </Button>

          <Link to="/dashboard">
            <Button size="sm">
              New Scan
            </Button>
          </Link>
        </div>
      </div>
    </header>
  );
}
