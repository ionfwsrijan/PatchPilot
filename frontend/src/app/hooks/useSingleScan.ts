import { useState, useEffect, useCallback } from "react";
import { scanZip, scanRepoUrl, API_BASE, type SingleScanStatus } from "../lib/api";

export function useSingleScan(onScanSuccess: (scan: { job_id: string; project_name: string; findings?: any[] }) => void) {
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [activeSingleScanId, setActiveSingleScanId] = useState<string | null>(null);
  const [singleScanState, setSingleScanState] = useState<SingleScanStatus | null>(null);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);

  useEffect(() => {
    return () => {
      if (eventSource) eventSource.close();
    };
  }, [eventSource]);

  const watchSingleScan = useCallback((jobId: string, projectName: string) => {
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
      setSingleScanState(parsed as SingleScanStatus);

      if (parsed.status === "completed" || parsed.status === "failed") {
        sse.close();
        setTimeout(async () => {
          try {
            const res = await fetch(`${API_BASE}/jobs/${jobId}/findings`);
            const data = await res.json();
            setScanLoading(false);
            onScanSuccess({ job_id: jobId, project_name: projectName, findings: data.findings || [] });
            setActiveSingleScanId(null);
          } catch (err) {
            setScanLoading(false);
            onScanSuccess({ job_id: jobId, project_name: projectName, findings: [] });
            setActiveSingleScanId(null);
          }
        }, 1000);
      }
    };

    sse.onerror = () => {
      if (sse.readyState === EventSource.CLOSED) setScanLoading(false);
    };

    setEventSource(sse);
  }, [eventSource, onScanSuccess]);

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

  const handleImportFromUrl = async (url: string, ref: string, onSuccessCallback?: () => void) => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      setScanError("Please paste a GitHub repo URL.");
      return;
    }
    setScanError(null);
    setScanLoading(true);

    try {
      const initRes = await scanRepoUrl(trimmedUrl, ref || "main", "project");
      if (onSuccessCallback) onSuccessCallback();
      watchSingleScan(initRes.job_id, initRes.project_name);
    } catch (e: any) {
      setScanError(e?.message ?? "Import from URL failed");
      setScanLoading(false);
    }
  };

  return {
    scanLoading,
    scanError,
    activeSingleScanId,
    singleScanState,
    handleZipFile,
    handleImportFromUrl,
    setScanError
  };
}
