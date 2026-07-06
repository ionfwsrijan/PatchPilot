import { useMemo, useState, useEffect } from "react";
import { CheckCircle2, XCircle, Clock, Download, FileText } from "lucide-react";
import { Link } from "react-router";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { cn } from "../components/ui/utils";

import { downloadEvidencePack, verify } from "../lib/api";
import { loadLastScan } from "../lib/scan-store";

interface VerificationCheck {
  id: string;
  name: string;
  status: "pass" | "fail" | "skip" | "running";
  duration?: string;
  output?: string;
}

interface TimelineEvent {
  id: string;
  timestamp: string;
  event: string;
  status: "completed" | "current";
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function Verify() {
  const scan = loadLastScan();

  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isVerified, setIsVerified] = useState<boolean | null>(null);

  const [verificationChecks, setVerificationChecks] = useState<VerificationCheck[]>([
    { id: "init", name: "Sandbox Environment", status: "running", output: "Waking up backend sandbox..." }
  ]);

  const [timeline, setTimeline] = useState<TimelineEvent[]>([
    { id: "1", timestamp: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'}), event: `Scan context loaded for ${scan?.project_name ?? "project"}`, status: "completed" },
    { id: "2", timestamp: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'}), event: "Running dynamic verification checks...", status: "current" }
  ]);

  useEffect(() => {
    if (!scan?.job_id) {
      setVerificationChecks([{ id: "err", name: "Status Error", status: "fail", output: "No active Job ID found." }]);
      setIsVerified(false);
      return;
    }

    verify(scan.job_id)
      .then((res: any) => {
        const passed = res?.ok ?? res?.passed ?? false;
        setIsVerified(passed);
        
        // If backend returns an array of specific checks, map them. Otherwise, provide a generic result.
        if (res?.checks && Array.isArray(res.checks)) {
          setVerificationChecks(res.checks);
        } else {
          setVerificationChecks([
            {
              id: "sandbox",
              name: "Sandbox Verification Result",
              status: passed ? "pass" : "fail",
              duration: res?.duration ? `${res.duration}s` : undefined,
              output: passed ? "No new issues introduced. Environment stable." : "Verification failed. New issues detected."
            }
          ]);
        }

        setTimeline(prev => {
          if (prev.some(t => t.event === "Verification complete")) return prev;
          return [
            ...prev.map(t => ({ ...t, status: "completed" as const })),
            { id: crypto.randomUUID(), timestamp: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'}), event: "Verification complete", status: "completed" }
          ];
        });
      })
      .catch((err) => {
        console.error("Verification error:", err);
        setIsVerified(false);
        setVerificationChecks([{ id: "err", name: "Sandbox Request", status: "fail", output: err?.message || "Failed to reach sandbox environment." }]);
        setTimeline(prev => {
          if (prev.some(t => t.event === "Verification encountered an error")) return prev;
          return [
            ...prev.map(t => ({ ...t, status: "completed" as const })),
            { id: crypto.randomUUID(), timestamp: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'}), event: "Verification encountered an error", status: "completed" }
          ];
        });
      });
  }, [scan?.job_id]);

  const evidenceItems = [
    { name: "Findings selected", value: "From scan results", included: true },
    {
      name: "Diff patches",
      value: "Included (if fixes were applied)",
      included: true,
    },
    { name: "Verification output", value: "Included", included: true },
    { name: "Tool versions", value: "Included", included: true },
    {
      name: "Scan metadata",
      value: "Job ID, timestamps, duration",
      included: true,
    },
  ];

  const evidencePackName = useMemo(() => {
    if (!scan?.job_id) return "evidence-pack.zip";
    return `evidence-pack-${scan.job_id}.zip`;
  }, [scan?.job_id]);

  const onDownloadEvidencePack = async () => {
    if (!scan?.job_id) {
      setDownloadError(
        "No scan job found. Please run a scan first (Dashboard → upload ZIP).",
      );
      return;
    }

    setDownloadError(null);
    setDownloading(true);
    try {
      const { blob, filename } = await downloadEvidencePack(
        scan.job_id,
        scan.project_name ?? "project",
      );
      saveBlob(blob, filename);
    } catch (e: any) {
      setDownloadError(e?.message ?? "Failed to download evidence pack");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-7xl pb-20 md:pb-8">
      <div className="mb-6">
        <h1 className="mb-2">Verify & Evidence</h1>
        <p className="text-muted-foreground">
          Validation results and evidence pack for{" "}
          {scan?.project_name ?? "your project"}
        </p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Verification Checks</CardTitle>
              <CardDescription>
                {isVerified === null ? "Running checks in sandbox..." : (isVerified ? "All checks passed successfully" : "Verification checks failed")}
              </CardDescription>
            </div>
            <div className={cn("flex items-center gap-2", isVerified === null ? "text-status-pending" : (isVerified ? "text-status-success" : "text-status-error"))}>
              {isVerified === null ? <Clock className="h-5 w-5 animate-spin" /> : (isVerified ? <CheckCircle2 className="h-5 w-5" /> : <XCircle className="h-5 w-5" />)}
              <span className="font-medium">
                {isVerified === null ? "Running" : (isVerified ? "Passed" : "Failed")}
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {verificationChecks.map((check) => (
              <div
                key={check.id}
                className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-full",
                      check.status === "pass" &&
                        "bg-status-success-bg dark:bg-status-success-bg",
                      check.status === "fail" &&
                        "bg-status-error-bg dark:bg-status-error-bg",
                      check.status === "skip" &&
                        "bg-status-pending-bg dark:bg-status-pending-bg",
                      check.status === "running" &&
                        "bg-status-pending-bg dark:bg-status-pending-bg",
                    )}
                  >
                    {check.status === "pass" && (
                      <CheckCircle2 className="h-4 w-4 text-status-success dark:text-status-success" />
                    )}
                    {check.status === "fail" && (
                      <XCircle className="h-4 w-4 text-status-error dark:text-status-error" />
                    )}
                    {check.status === "skip" && (
                      <Clock className="h-4 w-4 text-status-pending dark:text-status-pending" />
                    )}
                    {check.status === "running" && (
                      <Clock className="h-4 w-4 text-status-pending dark:text-status-pending animate-spin" />
                    )}
                  </div>
                  <div>
                    <div className="font-medium">{check.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {check.output}
                    </div>
                  </div>
                </div>
                {check.duration && (
                  <div className="text-sm text-muted-foreground">
                    {check.duration}
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Evidence Pack</CardTitle>
          <CardDescription>
            Complete audit trail for compliance and review
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {evidenceItems.map((item, index) => (
                <div
                  key={index}
                  className="flex items-start gap-3 p-3 rounded-lg bg-muted/50"
                >
                  <CheckCircle2 className="h-4 w-4 text-status-success mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium mb-1">{item.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {item.value}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {downloadError && (
              <div className="text-sm text-destructive">{downloadError}</div>
            )}

            <div className="flex items-center justify-between p-4 rounded-lg border-2 border-dashed border-border">
              <div className="flex items-center gap-3">
                <div className="rounded-full bg-primary/10 p-3">
                  <FileText className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <div className="font-medium">{evidencePackName}</div>
                  <div className="text-sm text-muted-foreground">
                    Generated on demand from backend
                  </div>
                </div>
              </div>

              <Button
                onClick={onDownloadEvidencePack}
                disabled={downloading || !scan?.job_id}
              >
                <Download className="h-4 w-4 mr-2" />
                {downloading ? "Downloading..." : "Download"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Audit Timeline</CardTitle>
          <CardDescription>
            Complete timeline of all scan activities
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative">
            <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-border" />
            <div className="space-y-4">
              {timeline.map((event) => (
                <div
                  key={event.id}
                  className="relative flex items-start gap-4 pl-10"
                >
                  <div
                    className={cn(
                      "absolute left-0 flex h-8 w-8 items-center justify-center rounded-full border-2",
                      event.status === "completed"
                        ? "border-primary bg-primary"
                        : "border-border bg-background",
                    )}
                  >
                    {event.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 text-primary-foreground" />
                    ) : (
                      <div className="h-2 w-2 rounded-full bg-primary" />
                    )}
                  </div>
                  <div className="flex-1 pb-4">
                    <div className="flex items-start justify-between mb-1">
                      <div className="font-medium">{event.event}</div>
                      <div className="text-xs text-muted-foreground font-mono">
                        {event.timestamp}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-end">
        <Link to="/findings">
          <Button variant="outline">View All Findings</Button>
        </Link>
        <Link to="/dashboard">
          <Button>Start New Scan</Button>
        </Link>
      </div>
    </div>
  );
}
