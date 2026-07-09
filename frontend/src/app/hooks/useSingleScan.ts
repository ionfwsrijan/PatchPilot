import { useState, useCallback } from "react";
import { scanZip, scanRepoUrl } from "../lib/api";

export function useSingleScan() {
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [activeSingleScanId, setActiveSingleScanId] = useState<string | null>(null);
  const [activeProjectName, setActiveProjectName] = useState<string | null>(null);

  const watchSingleScan = useCallback((jobId: string, projectName: string) => {
    setActiveSingleScanId(jobId);
    setActiveProjectName(projectName);
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

  const resetSingleScan = useCallback(() => {
    setActiveSingleScanId(null);
    setActiveProjectName(null);
    setScanLoading(false);
  }, []);

  return {
    scanLoading,
    scanError,
    activeSingleScanId,
    activeProjectName,
    handleZipFile,
    handleImportFromUrl,
    setScanError,
    resetSingleScan
  };
}