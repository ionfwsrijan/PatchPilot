import { useState, useCallback, useRef, useEffect } from "react";
import { scanZip, scanRepoUrl, API_BASE } from "../lib/api";

export function useSingleScan() {
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [activeSingleScanId, setActiveSingleScanId] = useState<string | null>(null);
  const [activeProjectName, setActiveProjectName] = useState<string>("");

  const closeSingleScan = useCallback(() => {
    setActiveSingleScanId(null);
    setActiveProjectName("");
    setScanLoading(false);
  }, []);

  const handleZipFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setScanError("Please upload a .zip file.");
      return;
    }
    setScanError(null);
    setScanLoading(true);

    try {
      const initRes = await scanZip(file, file.name.replace(/\.zip$/i, ""));
      setActiveSingleScanId(initRes.job_id);
      setActiveProjectName(initRes.project_name);
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
      setActiveSingleScanId(initRes.job_id);
      setActiveProjectName(initRes.project_name);
    } catch (e: any) {
      setScanError(e?.message ?? "Import from URL failed");
      setScanLoading(false);
    }
  };

  return {
    scanLoading,
    scanError,
    activeSingleScanId,
    activeProjectName,
    handleZipFile,
    handleImportFromUrl,
    setScanError,
    closeSingleScan,
  };
}

export function useSingleScanProgress({
  scanId,
  projectName,
  onScanSuccess,
  onScanError,
  onClose,
}: {
  scanId: string | null;
  projectName?: string;
  onScanSuccess?: (scan: { job_id: string; project_name: string; findings?: any[] }) => void;
  onScanError?: (error: string) => void;
  onClose?: () => void;
}) {
  const [singleScanState, setSingleScanState] = useState<any>(null);
  const onScanSuccessRef = useRef(onScanSuccess);
  const onScanErrorRef = useRef(onScanError);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onScanSuccessRef.current = onScanSuccess;
    onScanErrorRef.current = onScanError;
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!scanId) {
      setSingleScanState(null);
      return;
    }

    setSingleScanState({ sast: 'pending', dependency: 'pending', secrets: 'pending', status: 'running' });

    const sse = new EventSource(`${API_BASE}/api/scans/${scanId}/stream`);
    let timeoutId: any = null;

    sse.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.error) {
          sse.close();
          onScanErrorRef.current?.("Live scan tracking failed.");
          onCloseRef.current?.();
          return;
        }
        setSingleScanState(parsed);

        if (parsed.status === "completed" || parsed.status === "failed") {
          sse.close();
          timeoutId = setTimeout(async () => {
            try {
              const res = await fetch(`${API_BASE}/jobs/${scanId}/findings`);
              const data = await res.json();
              onScanSuccessRef.current?.({ job_id: scanId, project_name: projectName || "project", findings: data.findings || [] });
            } catch (err) {
              onScanSuccessRef.current?.({ job_id: scanId, project_name: projectName || "project", findings: [] });
            } finally {
              onCloseRef.current?.();
            }
          }, 1000);
        }
      } catch (err) {
        console.error("Error parsing scan stream event", err);
      }
    };

    sse.onerror = () => {
      if (sse.readyState === EventSource.CLOSED) {
        // SSE closed
      }
    };

    return () => {
      sse.close();
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [scanId, projectName]);

  return { singleScanState, setSingleScanState };
}