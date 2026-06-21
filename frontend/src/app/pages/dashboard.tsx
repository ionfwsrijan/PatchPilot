import { useRef, useState, useEffect } from "react";
import { Upload, Link as LinkIcon, Clock, Trash2, Download, Loader2, CheckCircle, AlertTriangle, Building2, Layers } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { scanRepoUrl, scanZip, downloadAuditReport, scanOrganization, getOrgJobStatus, abortOrganizationScan, API_BASE } from "../lib/api";
import { saveLastScan } from "../lib/scan-store";
import { Button } from "../components/ui/button";
import { TrendChart } from "../components/trend-chart";
import { CweChart } from "../components/cwe-chart"
import { DependencyDiff } from "../components/dependency-diff";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import { StatusPill } from "../components/status-pill";
import { Input } from "../components/ui/input";
import { cn } from "../components/ui/utils";
import { ProgressStepper } from "../components/progress-stepper";

type UiJobStatus = "completed" | "running" | "failed" | "pending";

type UiJob = {
  id: string;
  repoName: string;
  status: UiJobStatus;
  timestamp: string;
  duration?: string;
  findingsCount: number;
};

const RECENTS_KEY = "patchpilot:recentJobs";

function getLocalRecentJobs(): UiJob[] {
  const raw = localStorage.getItem(RECENTS_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as UiJob[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveLocalRecentJob(job: UiJob) {
  const jobs = getLocalRecentJobs();
  const next = [job, ...jobs.filter((j) => j.id !== job.id)].slice(0, 10);
  localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
}

function clearLocalRecentJobs() {
  localStorage.removeItem(RECENTS_KEY);
}

function ExportReportButton({ scanId }: { scanId: string }) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");

  const handleDownload = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    setIsGenerating(true);
    setStatus("idle");

    try {
      const { blob, filename } = await downloadAuditReport(scanId);
      
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      setStatus("success");
      setTimeout(() => setStatus("idle"), 4000);
    } catch (error) {
      setStatus("error");
      setTimeout(() => setStatus("idle"), 5000);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="relative inline-block text-left">
      <Button
        variant="outline"
        size="sm"
        onClick={handleDownload}
        disabled={isGenerating}
        className="flex items-center gap-2 text-xs h-8"
      >
        {isGenerating ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : (
          <Download className="w-3 h-3" />
        )}
        {isGenerating ? "Generating..." : "PDF"}
      </Button>

      {status === "success" && (
        <div className="absolute bottom-full right-0 mb-2 z-50 flex items-center gap-2 p-2 bg-slate-900 border border-emerald-800 text-slate-200 shadow-xl rounded min-w-[200px] animate-in fade-in slide-in-from-bottom-2">
          <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-slate-200">Report Downloaded</span>
          </div>
        </div>
      )}

      {status === "error" && (
        <div className="absolute bottom-full right-0 mb-2 z-50 flex items-center gap-2 p-2 bg-slate-900 border border-rose-800 text-slate-200 shadow-xl rounded min-w-[200px] animate-in fade-in slide-in-from-bottom-2">
          <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0" />
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-slate-200">Export Failed</span>
          </div>
        </div>
      )}
    </div>
  );
}

export function Dashboard() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [dragActive, setDragActive] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  const [recentJobs, setRecentJobs] = useState<UiJob[]>(() =>
    getLocalRecentJobs(),
  );

  const [urlDialogOpen, setUrlDialogOpen] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [repoRef, setRepoRef] = useState("main");

  const [orgDialogOpen, setOrgDialogOpen] = useState(false);
  const [orgUrl, setOrgUrl] = useState("");
  const [activeOrgJobId, setActiveOrgJobId] = useState<string | null>(null);
  const [orgStatusData, setOrgStatusData] = useState<any>(null);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);
  const [isAborting, setIsAborting] = useState(false);
  const [expectedRepoCount, setExpectedRepoCount] = useState<number>(0);

  useEffect(() => {
    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [eventSource]);

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  };

  const handleScanSuccess = (scan: {
    job_id: string;
    project_name: string;
    findings?: any[];
  }) => {
    saveLastScan(scan as any);

    const job: UiJob = {
      id: scan.job_id,
      repoName: scan.project_name,
      status: "completed",
      timestamp: new Date().toISOString(),
      duration: "-",
      findingsCount: scan.findings?.length ?? 0,
    };

    saveLocalRecentJob(job);
    setRecentJobs(getLocalRecentJobs());

    navigate("/findings");
  };

  const [activeSingleScanId, setActiveSingleScanId] = useState<string | null>(null);
  const [singleScanState, setSingleScanState] = useState<any>(null);

  const watchSingleScan = (jobId: string, projectName: string) => {
    setActiveSingleScanId(jobId);
    setSingleScanState({ sast: 'pending', dependency: 'pending', secrets: 'pending', status: 'running' });

    if (eventSource) eventSource.close();
    const sse = new EventSource(`${API_BASE}/api/scans/${jobId}/stream`);

    sse.onmessage = (event) => {
      const parsed = JSON.parse(event.data);
      if (parsed.error) {
        sse.close();
        setScanLoading(false);
        setScanError("Live scan tracking failed.");
        setActiveSingleScanId(null);
        return;
      }
      setSingleScanState(parsed);

if (parsed.status === "completed" || parsed.status === "failed") {
        sse.close();
        setTimeout(async () => {
          try {
            const res = await fetch(`${API_BASE}/jobs/${jobId}/findings`);
            const data = await res.json();
            setScanLoading(false);
            handleScanSuccess({ job_id: jobId, project_name: projectName, findings: data.findings || [] });
            setActiveSingleScanId(null);
          } catch (err) {
            setScanLoading(false);
            handleScanSuccess({ job_id: jobId, project_name: projectName, findings: [] });
            setActiveSingleScanId(null);
          }
        }, 1000);
      }
    };
    sse.onerror = () => {
      if (sse.readyState === EventSource.CLOSED) setScanLoading(false);
    };
    setEventSource(sse);
  };

  const handleZipFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setScanError("Please upload a .zip file.");
      return;
    }
    setScanError(null);
    setScanLoading(true);

    try {
      const initRes = await scanZip(file, file.name.replace(/\.zip$/i, ""));
      watchSingleScan(initRes.job_id, initRes.project_name);
    } catch (e: any) {
      setScanError(e?.message ?? "Scan failed");
      setScanLoading(false);
    }
  };

  const handleImportFromUrl = async () => {
    const url = repoUrl.trim();
    if (!url) {
      setScanError("Please paste a GitHub repo URL.");
      return;
    }
    setScanError(null);
    setScanLoading(true);

    try {
      const initRes = await scanRepoUrl(url, repoRef || "main", "project");
      setUrlDialogOpen(false);
      setRepoUrl("");
      setRepoRef("main");
      watchSingleScan(initRes.job_id, initRes.project_name);
    } catch (e: any) {
      setScanError(e?.message ?? "Import from URL failed");
      setScanLoading(false);
    }
  };

  const handleScanOrg = async () => {
    const url = orgUrl.trim();
    if (!url) {
      setScanError("Please enter a valid GitHub Organization URL.");
      return;
    }

    setScanError(null);
    setScanLoading(true);
    if (eventSource) {
      eventSource.close();
      setEventSource(null);
    }

    try {
      const data = await scanOrganization(url);
      setActiveOrgJobId(data.org_job_id);
      setExpectedRepoCount(data.repo_count);
      setOrgDialogOpen(false);

      getOrgJobStatus(data.org_job_id).then(setOrgStatusData).catch(() => {});

      const sse = new EventSource(`${API_BASE}/api/scans/org/${data.org_job_id}/stream`);
      
      sse.onmessage = (event) => {
        const parsed = JSON.parse(event.data);
        if (parsed.error) {
          sse.close();
          setScanLoading(false);
          return;
        }
        
        setOrgStatusData(parsed);
        const isFullyFinished = 
          ["completed", "failed"].includes(parsed.status) || 
          (parsed.status === "aborted" && !parsed.repos.some((r: any) => r.status === "scanning" || r.status === "pending"));

        if (isFullyFinished) {
          sse.close();
          setScanLoading(false);
        }
      };

      sse.onerror = () => {
        if (sse.readyState === EventSource.CLOSED) {
          setScanLoading(false);
        }
      };

      setEventSource(sse);
    } catch (e: any) {
      setScanError(e?.message ?? "Organization batch scan failed");
      setScanLoading(false);
    }
  };

const handleAbortScan = async (mode: "pending" | "force") => {
    if (!activeOrgJobId) return;
    if (mode === "force") {
      if (eventSource) {
        eventSource.close();
        setEventSource(null);
      }
      setActiveOrgJobId(null);
      setOrgStatusData(null);
      setOrgUrl("");
      setScanLoading(false);
    } else {
      setIsAborting(true);
    }
    
    try {
      await abortOrganizationScan(activeOrgJobId, mode);
    } catch (err) {
      console.error("Failed to abort scan", err);
    } finally {
      if (mode !== "force") {
        setIsAborting(false);
      }
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (scanLoading) return;

    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (scanLoading) return;

    setDragActive(false);

    const file = e.dataTransfer.files?.[0];
    if (!file) return;

    await handleZipFile(file);
  };

  const onClearRecents = () => {
    clearLocalRecentJobs();
    setRecentJobs([]);
  };

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-7xl pb-20 md:pb-8">
      <div className="mb-8">
        <h1 className="mb-2">Dashboard</h1>
        <p className="text-muted-foreground">
          Upload your codebase and start scanning for vulnerabilities
        </p>
      </div>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Start New Scan</CardTitle>
          <CardDescription>
            Upload a ZIP archive or import from a repository URL
          </CardDescription>
        </CardHeader>
        <CardContent>
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              await handleZipFile(file);
              if (e.currentTarget) e.currentTarget.value = "";
            }}
          />

          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={cn(
              "relative rounded-lg border-2 border-dashed p-12 transition-colors",
              dragActive
                ? "border-primary bg-accent"
                : "border-border hover:border-muted-foreground",
              scanLoading && "opacity-60 pointer-events-none",
            )}
          >
            <div className="flex flex-col items-center text-center">
              <div className="rounded-full bg-muted p-4 mb-4">
                <Upload className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="mb-2">Drag & drop your ZIP file here</h3>
              <p className="text-sm text-muted-foreground mb-4 max-w-sm">
                Supported formats: .zip (max 500MB)
              </p>

              {scanError && (
                <p className="text-sm text-destructive mb-4">{scanError}</p>
              )}

              <div className="flex gap-3">
                <Button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={scanLoading}
                >
                  {scanLoading ? "Scanning..." : "Browse Files"}
                </Button>

                <Button
                  variant="outline"
                  disabled={scanLoading}
                  onClick={() => setUrlDialogOpen(true)}
                >
                  <LinkIcon className="h-4 w-4 mr-2" />
                  Import from URL
                </Button>

                <Button
                  variant="outline"
                  disabled={scanLoading}
                  onClick={() => setOrgDialogOpen(true)}
                >
                  <Building2 className="h-4 w-4 mr-2" />
                  Scan Organization
                </Button>
              </div>
            </div>
          </div>

          {urlDialogOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
              <div className="w-full max-w-lg rounded-lg bg-background border border-border p-4 shadow-lg">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-lg font-semibold">Import from URL</div>
                    <div className="text-sm text-muted-foreground">
                      GitHub repos supported (example:
                      https://github.com/owner/repo)
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={() => setUrlDialogOpen(false)}
                    disabled={scanLoading}
                  >
                    Close
                  </Button>
                </div>

                <div className="mt-4 space-y-2">
                  <Input
                    placeholder="https://github.com/owner/repo"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    disabled={scanLoading}
                  />
                  <Input
                    placeholder="Branch/ref (default: main)"
                    value={repoRef}
                    onChange={(e) => setRepoRef(e.target.value)}
                    disabled={scanLoading}
                  />
                </div>

                <div className="mt-4 flex justify-end gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setUrlDialogOpen(false)}
                    disabled={scanLoading}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleImportFromUrl}
                    disabled={scanLoading || !repoUrl.trim()}
                  >
                    {scanLoading ? "Importing..." : "Import & Scan"}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {orgDialogOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
              <div className="w-full max-w-lg rounded-lg bg-background border border-border p-4 shadow-lg">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-lg font-semibold">Scan Organization</div>
                    <div className="text-sm text-muted-foreground">
                      Fetch and execute vulnerability tests across all repositories
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={() => setOrgDialogOpen(false)}
                    disabled={scanLoading}
                  >
                    Close
                  </Button>
                </div>

                <div className="mt-4 space-y-2">
                  <Input
                    placeholder="https://github.com/your-org"
                    value={orgUrl}
                    onChange={(e) => setOrgUrl(e.target.value)}
                    disabled={scanLoading}
                  />
                </div>

                <div className="mt-4 flex justify-end gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setOrgDialogOpen(false)}
                    disabled={scanLoading}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleScanOrg}
                    disabled={scanLoading || !orgUrl.trim()}
                  >
                    {scanLoading ? "Initializing..." : "Run Batch Scan"}
                  </Button>
                </div>
              </div>
            </div>
          )}

        {activeSingleScanId && singleScanState && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md animate-in fade-in duration-300">
            <div className="w-full max-w-3xl rounded-xl bg-background border border-border/50 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
              <div className="p-6 border-b border-border/30 bg-muted/10 flex items-center justify-between">
                <div>
                  <h2 className="font-semibold text-xl tracking-tight text-foreground">Security Scan Timeline</h2>
                  <p className="text-xs text-muted-foreground font-mono mt-1.5 px-2 py-0.5 bg-muted/50 rounded inline-flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse"></span>
                    {activeSingleScanId}
                  </p>
                </div>
                <Loader2 className={cn("h-6 w-6 text-primary", singleScanState.status === "running" && "animate-spin")} />
              </div>

              <div className="p-10 bg-gradient-to-b from-background to-muted/5">
                <div className="relative pl-8 border-l-2 border-border/30 space-y-12">
                  
                  <div className="relative animate-in fade-in slide-in-from-left-4 duration-500">
                    <div className={cn("absolute -left-[41px] top-1 h-5 w-5 rounded-full border-4 bg-background", singleScanState.sast === "completed" ? "border-emerald-500" : singleScanState.sast === "in_progress" ? "border-primary shadow-[0_0_15px_rgba(59,130,246,0.5)]" : "border-border")} />
                    <div className="flex flex-col bg-muted/5 p-4 rounded-lg border border-border/40 hover:border-primary/30 transition-colors">
                      <div className="flex justify-between items-start mb-1">
                        <span className={cn("text-base font-semibold", singleScanState.sast === "upcoming" && "text-muted-foreground")}>Static Application Security Testing (SAST)</span>
                        <span className="text-xs font-mono px-2 py-1 bg-muted/50 rounded text-muted-foreground">Semgrep</span>
                      </div>
                      {singleScanState.sast === "in_progress" && <span className="text-sm text-primary mt-1 animate-pulse">Analyzing source code patterns...</span>}
                      {singleScanState.sast === "completed" && <span className="text-sm text-emerald-500 mt-1 flex items-center gap-1.5">✓ Source analysis complete</span>}
                      {singleScanState.sast === "upcoming" && <span className="text-sm text-muted-foreground mt-1">Pending initialization</span>}
                    </div>
                  </div>

                  <div className={cn("relative transition-all duration-700", singleScanState.sast !== "completed" && "opacity-40 grayscale")}>
                    <div className={cn("absolute -left-[41px] top-1 h-5 w-5 rounded-full border-4 bg-background", singleScanState.dependency === "completed" ? "border-emerald-500" : singleScanState.dependency === "in_progress" ? "border-primary shadow-[0_0_15px_rgba(59,130,246,0.5)]" : "border-border")} />
                    <div className="flex flex-col bg-muted/5 p-4 rounded-lg border border-border/40 hover:border-primary/30 transition-colors">
                      <div className="flex justify-between items-start mb-1">
                        <span className={cn("text-base font-semibold", singleScanState.dependency === "upcoming" && "text-muted-foreground")}>Dependency Vulnerability Scan</span>
                        <span className="text-xs font-mono px-2 py-1 bg-muted/50 rounded text-muted-foreground">OSV-Scanner</span>
                      </div>
                      {singleScanState.dependency === "in_progress" && <span className="text-sm text-primary mt-1 animate-pulse">Cross-referencing global CVE databases...</span>}
                      {singleScanState.dependency === "completed" && <span className="text-sm text-emerald-500 mt-1 flex items-center gap-1.5">✓ Dependency check verified</span>}
                      {singleScanState.dependency === "upcoming" && <span className="text-sm text-muted-foreground mt-1">Waiting for SAST completion</span>}
                    </div>
                  </div>

                  <div className={cn("relative transition-all duration-700", singleScanState.dependency !== "completed" && "opacity-40 grayscale")}>
                    <div className={cn("absolute -left-[41px] top-1 h-5 w-5 rounded-full border-4 bg-background", singleScanState.secrets === "completed" ? "border-emerald-500" : singleScanState.secrets === "in_progress" ? "border-primary shadow-[0_0_15px_rgba(59,130,246,0.5)]" : "border-border")} />
                    <div className="flex flex-col bg-muted/5 p-4 rounded-lg border border-border/40 hover:border-primary/30 transition-colors">
                      <div className="flex justify-between items-start mb-1">
                        <span className={cn("text-base font-semibold", singleScanState.secrets === "upcoming" && "text-muted-foreground")}>Secrets & Entropy Detection</span>
                        <div className="flex gap-2">
                          <span className="text-xs font-mono px-2 py-1 bg-muted/50 rounded text-muted-foreground">Gitleaks</span>
                          <span className="text-xs font-mono px-2 py-1 bg-muted/50 rounded text-muted-foreground">Entropy</span>
                        </div>
                      </div>
                      {singleScanState.secrets === "in_progress" && <span className="text-sm text-primary mt-1 animate-pulse">Scanning for exposed keys and high-entropy strings...</span>}
                      {singleScanState.secrets === "completed" && <span className="text-sm text-emerald-500 mt-1 flex items-center gap-1.5">✓ Secrets scan complete</span>}
                      {singleScanState.secrets === "upcoming" && <span className="text-sm text-muted-foreground mt-1">Waiting for dependency scan</span>}
                    </div>
                  </div>

                </div>
              </div>

              <div className="p-6 border-t border-border/30 bg-muted/10 flex justify-between items-center">
                 <p className="text-sm text-muted-foreground">
                  {singleScanState.status === "completed" ? "Finalizing report..." : "Background processes running. Do not close this window."}
                 </p>
                 <span className={cn("text-xs font-mono uppercase tracking-widest px-3 py-1.5 rounded-full border", singleScanState.status === "running" ? "bg-primary/10 text-primary border-primary/20" : "bg-emerald-500/10 text-emerald-500 border-emerald-500/20")}>
                    {singleScanState.status}
                 </span>
              </div>
            </div>
          </div>
        )}

        {activeOrgJobId && orgStatusData && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
              <div className="w-full max-w-2xl rounded-lg bg-background border border-border shadow-2xl flex flex-col max-h-[85vh] animate-in fade-in zoom-in-95 duration-200">
                
                {/* Modal Header */}
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
                      orgStatusData.status === "completed" 
                        ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" 
                        : orgStatusData.status === "aborted"
                        ? "bg-rose-500/10 text-rose-500 border-rose-500/20"
                        : "bg-primary/10 text-primary border-primary/20"
                    )}>
                      {orgStatusData.status}
                    </div>
                  </div>
                </div>

                {/* Modal Body / Scrollable List */}
                <div className="p-6 overflow-y-auto flex-1 min-h-[200px]">
                  {!orgStatusData.repos || orgStatusData.repos.length < expectedRepoCount ? (
                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground space-y-4 py-12">
                      <Loader2 className="w-10 h-10 animate-spin text-primary/60 mb-2" />
                      <p className="text-base font-medium text-foreground/80">Please wait...</p>
                      <p className="text-sm">Initializing cluster tools and mounting repository directories</p>
                    </div>
                  ) : (
                    <div className="border rounded-md divide-y bg-muted/10 shadow-inner">
                      {orgStatusData.repos.map((repo: any) => (
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

                {/* Modal Footer */}
                <div className="p-6 border-t bg-muted/10 rounded-b-lg flex justify-end gap-3">
                  {(orgStatusData.status === "scanning" || orgStatusData.status === "pending") && (
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

                  {["completed", "failed", "aborted"].includes(orgStatusData.status) && (
                    <Button 
                      size="lg"
                      className="cursor-pointer"
                      onClick={() => {
                        if (eventSource) eventSource.close();
                        setActiveOrgJobId(null);
                        setOrgStatusData(null);
                        setOrgUrl("");
                        navigate(`/org-findings/${activeOrgJobId}`);
                      }}
                    >
                      View Collected Analytics
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
              <div className="rounded-full bg-primary/10 p-2">
                <Clock className="h-4 w-4 text-primary" />
              </div>
              <div>
                <div className="text-sm font-medium mb-1">Fast Scanning</div>
                <div className="text-xs text-muted-foreground">
                  Typical scans complete in 2-5 minutes
                </div>
              </div>
            </div>
            <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
              <div className="rounded-full bg-primary/10 p-2">
                <Clock className="h-4 w-4 text-primary" />
              </div>
              <div>
                <div className="text-sm font-medium mb-1">Multiple Tools</div>
                <div className="text-xs text-muted-foreground">
                  Semgrep, OSV Scanner, and Gitleaks
                </div>
              </div>
            </div>
            <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
              <div className="rounded-full bg-primary/10 p-2">
                <Clock className="h-4 w-4 text-primary" />
              </div>
              <div>
                <div className="text-sm font-medium mb-1">Evidence Pack</div>
                <div className="text-xs text-muted-foreground">
                  Complete audit trail included
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <TrendChart />
          <CweChart />
        </div>
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Supply Chain Delta</CardTitle>
            <CardDescription>
              Vulnerabilities introduced or resolved in your dependencies between the last two scans.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DependencyDiff />
          </CardContent>
        </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Recent Scans</CardTitle>
            <CardDescription>
              Your latest vulnerability scan jobs
            </CardDescription>
          </div>

          {recentJobs.length > 0 && (
            <Button variant="outline" size="sm" onClick={onClearRecents}>
              <Trash2 className="h-4 w-4 mr-2" />
              Clear
            </Button>
          )}
        </CardHeader>

        <CardContent>
          {recentJobs.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No scans yet. Upload a ZIP above to start your first scan.
            </div>
          ) : (
            <>
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Job ID</TableHead>
                      <TableHead>Repository</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Timestamp</TableHead>
                      <TableHead>Duration</TableHead>
                      <TableHead className="text-right">Findings</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {recentJobs.map((job) => (
                      <TableRow
                        key={job.id}
                        className="cursor-pointer hover:bg-muted/50"
                      >
                        <TableCell className="font-mono text-xs">
                          {job.id}
                        </TableCell>
                        <TableCell className="font-medium">
                          {job.repoName}
                        </TableCell>
                        <TableCell>
                          <StatusPill status={job.status} />
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm">
                          {formatTimestamp(job.timestamp)}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm">
                          {job.duration || "-"}
                        </TableCell>
                        <TableCell className="text-right">
                          {job.status === "completed" && (
                            <span className="font-medium">
                              {job.findingsCount}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-right flex justify-end gap-2">
                          {job.status === "completed" && (
                            <ExportReportButton scanId={job.id} />
                          )}
                          <Link
                            to={job.status === "completed" ? "/findings" : "/"}
                          >
                            <Button variant="ghost" size="sm">
                              View
                            </Button>
                          </Link>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              <div className="md:hidden space-y-3">
                {recentJobs.map((job) => (
                  <Link
                    key={job.id}
                    to={job.status === "completed" ? "/findings" : "/"}
                    className="block"
                  >
                    <Card className="hover:bg-muted/50 transition-colors">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex-1 min-w-0">
                            <div className="font-medium truncate">
                              {job.repoName}
                            </div>
                            <div className="text-xs text-muted-foreground font-mono mt-1">
                              {job.id}
                            </div>
                          </div>
                          <StatusPill status={job.status} />
                        </div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>{formatTimestamp(job.timestamp)}</span>
                          <div className="flex items-center gap-3">
                            {job.status === "completed" && (
                              <ExportReportButton scanId={job.id} />
                            )}
                            {job.status === "completed" && (
                              <span className="font-medium text-foreground">
                                {job.findingsCount} findings
                              </span>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
