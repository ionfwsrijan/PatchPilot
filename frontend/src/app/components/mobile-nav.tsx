import { Link, useLocation } from "react-router";
import { Home, FileSearch, ShieldCheck } from "lucide-react";
import { cn } from "./ui/utils";

export function MobileNav() {
  const location = useLocation();

  const isActive = (path: string) => location.pathname === path;

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-card">
      <div className="grid grid-cols-3 h-16">
        <Link
          to="/dashboard"
          className={cn(
            "flex flex-col items-center justify-center gap-1 transition-colors",
            isActive("/dashboard")
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          <Home className="h-5 w-5" />
          <span className="text-xs font-medium">Dashboard</span>
        </Link>

        <Link
          to="/findings"
          className={cn(
            "flex flex-col items-center justify-center gap-1 transition-colors",
            isActive("/findings")
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          <FileSearch className="h-5 w-5" />
          <span className="text-xs font-medium">Findings</span>
        </Link>

        <Link
          to="/verify"
          className={cn(
            "flex flex-col items-center justify-center gap-1 transition-colors",
            isActive("/verify")
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          <ShieldCheck className="h-5 w-5" />
          <span className="text-xs font-medium">Verify</span>
        </Link>
      </div>
    </nav>
  );
}
