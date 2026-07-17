import { useRef, useState } from "react";
import { Upload, Link as LinkIcon, Clock, Trash2 } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { scanRepoUrl, scanZip } from "../lib/api";
import { saveLastScan } from "../lib/scan-store";
import { Button } from "../components/ui/button";
import { TrendChart } from "../components/trend-chart";
import { CweChart } from "../components/cwe-chart"
import { DependencyDiff } from "../components/dependency-diff";
import { toast } from "sonner";
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

export function Dashboard() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [dragActive, setDragActive] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);

  const [recentJobs, setRecentJobs] = useState<UiJob[]>(() =>
    getLocalRecentJobs(),
  );

  const [urlDialogOpen, setUrlDialogOpen] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [repoRef, setRepoRef] = useState("main");

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
    toast.success("Scan completed successfully!");
    navigate("/findings");
  };

  const handleZipFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      toast.error("Please upload a .zip file.");
      return;
    }
    setScanLoading(true);

    try {
      const scan = await scanZip(file, file.name.replace(/\.zip$/i, ""));
      handleScanSuccess(scan);
    } catch (e: any) {
      toast.error(e?.message ?? "Scan failed");
    } finally {
      setScanLoading(false);
    }
  };

  const handleImportFromUrl = async () => {
    const url = repoUrl.trim();
    if (!url) {
      toast.error(
        "Please paste a GitHub repo URL (example: https://github.com/owner/repo).",
      );
      return;
    }
    setScanLoading(true);

    try {
      const scan = await scanRepoUrl(url, repoRef || "main", "project");
      handleScanSuccess(scan);

      setUrlDialogOpen(false);
      setRepoUrl("");
      setRepoRef("main");
    } catch (e: any) {
      toast.error(e?.message ?? "Import from URL failed");
    } finally {
      setScanLoading(false);
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
                        <TableCell>
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
                          {job.status === "completed" && (
                            <span className="font-medium text-foreground">
                              {job.findingsCount} findings
                            </span>
                          )}
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
