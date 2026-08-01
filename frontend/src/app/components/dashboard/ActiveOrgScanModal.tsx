import { useState, useEffect } from "react";
import { Loader2, Layers, CheckCircle, AlertTriangle } from "lucide-react";
import { Button } from "../ui/button";
import { cn } from "../ui/utils";
import { getOrgJobStatus, abortOrganizationScan, API_BASE } from "../../lib/api";
import { useNavigate } from "react-router-dom";

interface ActiveOrgScanModalProps {
  orgJobId: string | null;
  expectedRepoCount: number;
  onClose: () => void;
  onCancel: () => void;
}

export function ActiveOrgScanModal({ orgJobId, expectedRepoCount, onClose, onCancel }: ActiveOrgScanModalProps) {
  const navigate = useNavigate();
  const [statusData, setStatusData] = useState<any>(null);
  const [isAborting, setIsAborting] = useState(false);
  const [sseConnection, setSseConnection] = useState<EventSource | null>(null);

  useEffect(() => {
    if (!orgJobId) {
      setStatusData(null);
      return;
    }

    getOrgJobStatus(orgJobId).then(setStatusData).catch(() => {});

    const sse = new EventSource(`${API_BASE}/api/scans/org/${orgJobId}/stream`);
    setSseConnection(sse);

    sse.onmessage = (event) => {
      const parsed = JSON.parse(event.data);
      if (parsed.error) {
        sse.close();
        return;
      }
      
      setStatusData(parsed);
      const isFullyFinished = 
        ["completed", "failed"].includes(parsed.status) || 
        (parsed.status === "aborted" && !parsed.repos.some((r: any) => r.status === "scanning" || r.status === "pending"));

      if (isFullyFinished) {
        sse.close();
      }
    };

    sse.onerror = () => {
      // Optional SSE error handling
    };

    return () => {
      sse.close();
    };
  }, [orgJobId]);

  const handleAbortScan = async (mode: "pending" | "force") => {
    if (!orgJobId) return;
    
    if (mode === "force") {
      if (sseConnection) {
        sseConnection.close();
      }
      onCancel();
    } else {
      setIsAborting(true);
    }
    
    try {
      await abortOrganizationScan(orgJobId, mode);
    } catch (err) {
      console.error("Failed to abort scan", err);
    } finally {
      if (mode !== "force") setIsAborting(false);
    }
  };

  const handleClose = () => {
    if (sseConnection) {
      sseConnection.close();
    }
    onClose();
    if (orgJobId) {
      navigate(`/org-findings/${orgJobId}`);
    }
  };

  if (!statusData) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-lg bg-background border border-border shadow-2xl flex flex-col max-h-[85vh] animate-in fade-in zoom-in-95 duration-200">
        
        <div className="p-6 border-b flex items-center justify-between bg-muted/30 rounded-t-lg">
          <div className="flex items-center gap-4">
            <div className="p-2.5 bg-primary/10 rounded-lg border border-primary/20">
              <Layers className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h2 className="font-semibold text-lg leading-tight mb-1">Batch Cluster Engine Tracking</h2>
              <p className="text-sm text-muted-foreground">Scanning organization repositories concurrently</p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className={cn(
              "text-xs uppercase px-3 py-1 rounded font-mono font-bold border",
              statusData.status === "completed" 
                ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" 
                : statusData.status === "aborted"
                ? "bg-rose-500/10 text-rose-500 border-rose-500/20"
                : "bg-primary/10 text-primary border-primary/20"
            )}>
              {statusData.status}
            </div>
          </div>
        </div>

        <div className="p-6 overflow-y-auto flex-1 min-h-[200px]">
          {!statusData.repos || statusData.repos.length < expectedRepoCount ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground space-y-4 py-12">
              <Loader2 className="w-10 h-10 animate-spin text-primary/60 mb-2" />
              <p className="text-base font-medium text-foreground/80">Please wait...</p>
              <p className="text-sm">Initializing cluster tools and mounting repository directories</p>
            </div>
          ) : (
            <div className="border rounded-md divide-y bg-muted/10 shadow-inner">
              {statusData.repos.map((repo: any) => (
                <div key={repo.job_id} className="flex items-center justify-between p-4 text-sm hover:bg-muted/30 transition-colors">
                  <span className="font-medium text-foreground/90">{repo.project_name}</span>
                  <div className="flex items-center gap-3">
                    {repo.status === "scanning" && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
                    {repo.status === "completed" && <CheckCircle className="w-4 h-4 text-emerald-500" />}
                    {repo.status === "aborted" && <AlertTriangle className="w-4 h-4 text-rose-500" />}
                    <span className={cn(
                      "text-xs font-mono capitalize bg-background px-2.5 py-1 rounded border shadow-sm w-24 text-center",
                      repo.status === "aborted" ? "text-rose-500 border-rose-500/20" : "text-muted-foreground"
                    )}>
                      {repo.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="p-6 border-t bg-muted/10 rounded-b-lg flex justify-end gap-3">
          {(statusData.status === "scanning" || statusData.status === "pending") && (
            <>
              <Button 
                variant="outline" 
                onClick={() => handleAbortScan("pending")}
                disabled={isAborting}
                className="transition-all cursor-pointer hover:bg-muted hover:shadow-sm"
              >
                {isAborting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
                Cancel Pending Scans
              </Button>
              
              <Button 
                variant="destructive" 
                onClick={() => handleAbortScan("force")}
                disabled={isAborting}
                className="transition-all cursor-pointer hover:bg-red-600 hover:shadow-lg hover:-translate-y-0.5 active:translate-y-0 active:scale-95"
              >
                {isAborting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
                Force Cancel Scan
              </Button>
            </>
          )}

          {["completed", "failed", "aborted"].includes(statusData.status) && (
            <Button size="lg" className="cursor-pointer" onClick={handleClose}>
              View Collected Analytics
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}