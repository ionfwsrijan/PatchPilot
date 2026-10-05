import { Loader2 } from "lucide-react";
import { cn } from "../ui/utils";

interface ActiveSingleScanModalProps {
  scanId: string | null;
  scanState: any;
}

export function ActiveSingleScanModal({ scanId, scanState }: ActiveSingleScanModalProps) {
  if (!scanId || !scanState) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md animate-in fade-in duration-300">
      <div className="w-full max-w-3xl rounded-xl bg-background border border-border/50 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
        <div className="p-6 border-b border-border/30 bg-muted/10 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-xl tracking-tight text-foreground">Security Scan Timeline</h2>
            <p className="text-xs text-muted-foreground font-mono mt-1.5 px-2 py-0.5 bg-muted/50 rounded inline-flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse"></span>
              {scanId}
            </p>
          </div>
          <Loader2 className={cn("h-6 w-6 text-primary", scanState.status === "running" && "animate-spin")} />
        </div>

        <div className="p-10 bg-gradient-to-b from-background to-muted/5">
          <div className="relative pl-8 border-l-2 border-border/30 space-y-12">
            
            <div className="relative animate-in fade-in slide-in-from-left-4 duration-500">
              <div className={cn("absolute -left-[41px] top-1 h-5 w-5 rounded-full border-4 bg-background", scanState.sast === "completed" ? "border-emerald-500" : scanState.sast === "in_progress" ? "border-primary shadow-[0_0_15px_rgba(59,130,246,0.5)]" : "border-border")} />
              <div className="flex flex-col bg-muted/5 p-4 rounded-lg border border-border/40 hover:border-primary/30 transition-colors">
                <div className="flex justify-between items-start mb-1">
                  <span className={cn("text-base font-semibold", scanState.sast === "upcoming" && "text-muted-foreground")}>Static Application Security Testing (SAST)</span>
                  <span className="text-xs font-mono px-2 py-1 bg-muted/50 rounded text-muted-foreground">Semgrep</span>
                </div>
                {scanState.sast === "in_progress" && <span className="text-sm text-primary mt-1 animate-pulse">Analyzing source code patterns...</span>}
                {scanState.sast === "completed" && <span className="text-sm text-emerald-500 mt-1 flex items-center gap-1.5">✓ Source analysis complete</span>}
                {scanState.sast === "upcoming" && <span className="text-sm text-muted-foreground mt-1">Pending initialization</span>}
              </div>
            </div>

            <div className={cn("relative transition-all duration-700", scanState.sast !== "completed" && "opacity-40 grayscale")}>
              <div className={cn("absolute -left-[41px] top-1 h-5 w-5 rounded-full border-4 bg-background", scanState.dependency === "completed" ? "border-emerald-500" : scanState.dependency === "in_progress" ? "border-primary shadow-[0_0_15px_rgba(59,130,246,0.5)]" : "border-border")} />
              <div className="flex flex-col bg-muted/5 p-4 rounded-lg border border-border/40 hover:border-primary/30 transition-colors">
                <div className="flex justify-between items-start mb-1">
                  <span className={cn("text-base font-semibold", scanState.dependency === "upcoming" && "text-muted-foreground")}>Dependency Vulnerability Scan</span>
                  <span className="text-xs font-mono px-2 py-1 bg-muted/50 rounded text-muted-foreground">OSV-Scanner</span>
                </div>
                {scanState.dependency === "in_progress" && <span className="text-sm text-primary mt-1 animate-pulse">Cross-referencing global CVE databases...</span>}
                {scanState.dependency === "completed" && <span className="text-sm text-emerald-500 mt-1 flex items-center gap-1.5">✓ Dependency check verified</span>}
                {scanState.dependency === "upcoming" && <span className="text-sm text-muted-foreground mt-1">Waiting for SAST completion</span>}
              </div>
            </div>

            <div className={cn("relative transition-all duration-700", scanState.dependency !== "completed" && "opacity-40 grayscale")}>
              <div className={cn("absolute -left-[41px] top-1 h-5 w-5 rounded-full border-4 bg-background", scanState.secrets === "completed" ? "border-emerald-500" : scanState.secrets === "in_progress" ? "border-primary shadow-[0_0_15px_rgba(59,130,246,0.5)]" : "border-border")} />
              <div className="flex flex-col bg-muted/5 p-4 rounded-lg border border-border/40 hover:border-primary/30 transition-colors">
                <div className="flex justify-between items-start mb-1">
                  <span className={cn("text-base font-semibold", scanState.secrets === "upcoming" && "text-muted-foreground")}>Secrets & Entropy Detection</span>
                  <div className="flex gap-2">
                    <span className="text-xs font-mono px-2 py-1 bg-muted/50 rounded text-muted-foreground">Gitleaks</span>
                    <span className="text-xs font-mono px-2 py-1 bg-muted/50 rounded text-muted-foreground">Entropy</span>
                  </div>
                </div>
                {scanState.secrets === "in_progress" && <span className="text-sm text-primary mt-1 animate-pulse">Scanning for exposed keys and high-entropy strings...</span>}
                {scanState.secrets === "completed" && <span className="text-sm text-emerald-500 mt-1 flex items-center gap-1.5">✓ Secrets scan complete</span>}
                {scanState.secrets === "upcoming" && <span className="text-sm text-muted-foreground mt-1">Waiting for dependency scan</span>}
              </div>
            </div>

          </div>
        </div>

        <div className="p-6 border-t border-border/30 bg-muted/10 flex justify-between items-center">
           <p className="text-sm text-muted-foreground">
            {scanState.status === "completed" ? "Finalizing report..." : "Background processes running. Do not close this window."}
           </p>
           <span className={cn("text-xs font-mono uppercase tracking-widest px-3 py-1.5 rounded-full border", scanState.status === "running" ? "bg-primary/10 text-primary border-primary/20" : "bg-emerald-500/10 text-emerald-500 border-emerald-500/20")}>
              {scanState.status}
           </span>
        </div>
      </div>
    </div>
  );
}