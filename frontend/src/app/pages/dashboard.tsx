import { useRef, useState, useEffect } from "react";
import { Upload, Link as LinkIcon, Clock, Trash2, Download, Loader2, CheckCircle, AlertTriangle, Building2, Layers } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import {
  scanRepoUrl,
  scanZip,
  downloadAuditReport,
  scanOrganization,
  getOrgJobStatus,
  abortOrganizationScan,
  API_BASE,
  compareSecurityRegression,
} from "../lib/api";
import { saveLastScan } from "../lib/scan-store";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { TrendChart } from "../components/trend-chart";
import { CweChart } from "../components/cwe-chart";
import { DependencyDiff } from "../components/dependency-diff";
import { cn } from "../components/ui/utils";

import { useRecentJobs } from "../hooks/useRecentJobs";
import { useSingleScan } from "../hooks/useSingleScan";
import { useOrganizationScan } from "../hooks/useOrganizationScan";
import { useDragAndDrop } from "../hooks/useDragAndDrop";

import { UrlImportDialog } from "../components/dashboard/UrlImportDialog";
import { OrganizationScanDialog } from "../components/dashboard/OrganizationScanDialog";
import { ActiveSingleScanModal } from "../components/dashboard/ActiveSingleScanModal";
import { ActiveOrgScanModal } from "../components/dashboard/ActiveOrgScanModal";
import { RecentScans } from "../components/dashboard/RecentScans";

export function Dashboard() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [dragActive, setDragActive] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  const [recentJobs, setRecentJobs] = useState<UiJob[]>(() =>
    getLocalRecentJobs(),
  );
  const [regressionData, setRegressionData] = useState<any>(null);
  const [regressionError, setRegressionError] = useState("");
  const [urlDialogOpen, setUrlDialogOpen] = useState(false);
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

  const handleScanSuccess = async (scan: {
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

  const updatedJobs = getLocalRecentJobs();
  setRecentJobs(updatedJobs);

  if (updatedJobs.length > 1) {
   try {
    const result = await compareSecurityRegression(
      updatedJobs[1].id,   // previous scan
      updatedJobs[0].id,   // current scan
    );

    setRegressionData(result);
    setRegressionError("");
   } catch {
     setRegressionError("Unable to compare security regression.");
   }
  }
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

  const { recentJobs, handleScanSuccess, onClearRecents } = useRecentJobs();
  
  const { 
    scanLoading, scanError, activeSingleScanId, singleScanState, 
    handleZipFile, handleImportFromUrl, setScanError 
  } = useSingleScan(handleScanSuccess);
  
  const { 
    orgScanLoading, orgScanError, activeOrgJobId, orgStatusData, 
    expectedRepoCount, isAborting, handleScanOrg, handleAbortScan, closeOrgScan 
  } = useOrganizationScan();

  const isAnyLoading = scanLoading || orgScanLoading;
  const anyError = scanError || orgScanError;

  const { dragActive, handleDrag, handleDrop } = useDragAndDrop(handleZipFile, isAnyLoading);

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-7xl pb-20 md:pb-8">
      <div className="mb-8">
        <h1 className="mb-2">Dashboard</h1>
        <p className="text-muted-foreground">Upload your codebase and start scanning for vulnerabilities</p>
      </div>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Start New Scan</CardTitle>
          <CardDescription>Upload a ZIP archive or import from a repository URL</CardDescription>
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
              dragActive ? "border-primary bg-accent" : "border-border hover:border-muted-foreground",
              isAnyLoading && "opacity-60 pointer-events-none",
            )}
          >
            <div className="flex flex-col items-center text-center">
              <div className="rounded-full bg-muted p-4 mb-4">
                <Upload className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="mb-2">Drag & drop your ZIP file here</h3>
              <p className="text-sm text-muted-foreground mb-4 max-w-sm">Supported formats: .zip (max 500MB)</p>

              {anyError && <p className="text-sm text-destructive mb-4">{anyError}</p>}

              <div className="flex gap-3">
                <Button onClick={() => fileInputRef.current?.click()} disabled={isAnyLoading}>
                  {isAnyLoading ? "Scanning..." : "Browse Files"}
                </Button>

                <Button variant="outline" disabled={isAnyLoading} onClick={() => { setScanError(null); setUrlDialogOpen(true); }}>
                  <LinkIcon className="h-4 w-4 mr-2" />
                  Import from URL
                </Button>

                <Button variant="outline" disabled={isAnyLoading} onClick={() => { setScanError(null); setOrgDialogOpen(true); }}>
                  <Building2 className="h-4 w-4 mr-2" />
                  Scan Organization
                </Button>
              </div>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
              <div className="rounded-full bg-primary/10 p-2">
                <Clock className="h-4 w-4 text-primary" />
              </div>
              <div>
                <div className="text-sm font-medium mb-1">Fast Scanning</div>
                <div className="text-xs text-muted-foreground">Typical scans complete in 2-5 minutes</div>
              </div>
            </div>
            <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
              <div className="rounded-full bg-primary/10 p-2">
                <Clock className="h-4 w-4 text-primary" />
              </div>
              <div>
                <div className="text-sm font-medium mb-1">Multiple Tools</div>
                <div className="text-xs text-muted-foreground">Semgrep, OSV Scanner, and Gitleaks</div>
              </div>
            </div>
            <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
              <div className="rounded-full bg-primary/10 p-2">
                <Clock className="h-4 w-4 text-primary" />
              </div>
              <div>
                <div className="text-sm font-medium mb-1">Evidence Pack</div>
                <div className="text-xs text-muted-foreground">Complete audit trail included</div>
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
          <CardDescription>Vulnerabilities introduced or resolved in your dependencies between the last two scans.</CardDescription>
        </CardHeader>
        <CardContent>
          <DependencyDiff />
        </CardContent>
      </Card>

      <RecentScans recentJobs={recentJobs} onClearRecents={onClearRecents} />

      {/* Render Modals */}
      <UrlImportDialog 
        isOpen={urlDialogOpen} 
        onClose={() => setUrlDialogOpen(false)} 
        onImport={(url, ref) => handleImportFromUrl(url, ref, () => setUrlDialogOpen(false))} 
        isLoading={scanLoading} 
      />

      <OrganizationScanDialog 
        isOpen={orgDialogOpen} 
        onClose={() => setOrgDialogOpen(false)} 
        onScan={(url) => handleScanOrg(url, () => setOrgDialogOpen(false))} 
        isLoading={orgScanLoading} 
      />

      <ActiveSingleScanModal scanId={activeSingleScanId} scanState={singleScanState} />

      <ActiveOrgScanModal 
        statusData={orgStatusData} 
        expectedRepoCount={expectedRepoCount} 
        isAborting={isAborting} 
        onAbort={handleAbortScan} 
        onClose={closeOrgScan} 
      />
    </div>
  );

  }

