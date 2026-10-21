import { useState, useCallback, useRef, useEffect } from "react";
import { scanOrganization, getOrgJobStatus, abortOrganizationScan, API_BASE } from "../lib/api";
import { useNavigate } from "react-router-dom";

export function useOrganizationScan() {
  const navigate = useNavigate();
  const [orgScanLoading, setOrgScanLoading] = useState(false);
  const [orgScanError, setOrgScanError] = useState<string | null>(null);
  const [activeOrgJobId, setActiveOrgJobId] = useState<string | null>(null);
  const [expectedRepoCount, setExpectedRepoCount] = useState<number>(0);

  const handleScanOrg = async (url: string, onSuccessCallback?: () => void) => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      setOrgScanError("Please enter a valid GitHub Organization URL.");
      return;
    }

    setOrgScanError(null);
    setOrgScanLoading(true);

    try {
      const data = await scanOrganization(trimmedUrl);
      setActiveOrgJobId(data.org_job_id);
      setExpectedRepoCount(data.repo_count);
      if (onSuccessCallback) onSuccessCallback();
    } catch (e: any) {
      setOrgScanError(e?.message ?? "Organization batch scan failed");
      setOrgScanLoading(false);
    }
  };

  const closeOrgScan = useCallback((finalJobId?: string) => {
    const jobIdToNavigate = finalJobId || activeOrgJobId;
    setActiveOrgJobId(null);
    setOrgScanLoading(false);
    if (jobIdToNavigate) navigate(`/org-findings/${jobIdToNavigate}`);
  }, [activeOrgJobId, navigate]);

  return {
    orgScanLoading,
    orgScanError,
    activeOrgJobId,
    expectedRepoCount,
    handleScanOrg,
    closeOrgScan,
    setOrgScanError,
  };
}

export function useOrgScanProgress({
  orgJobId,
  onClose,
}: {
  orgJobId: string | null;
  onClose?: (jobId?: string) => void;
}) {
  const [orgStatusData, setOrgStatusData] = useState<any>(null);
  const [isAborting, setIsAborting] = useState(false);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!orgJobId) {
      setOrgStatusData(null);
      return;
    }

    getOrgJobStatus(orgJobId).then(setOrgStatusData).catch(() => {});

    const sse = new EventSource(`${API_BASE}/api/scans/org/${orgJobId}/stream`);

    sse.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.error) {
          sse.close();
          return;
        }

        setOrgStatusData(parsed);
        const isFullyFinished = 
          ["completed", "failed"].includes(parsed.status) || 
          (parsed.status === "aborted" && !parsed.repos.some((r: any) => r.status === "scanning" || r.status === "pending"));

        if (isFullyFinished) {
          sse.close();
        }
      } catch (err) {
        console.error("Error parsing org scan stream event", err);
      }
    };

    sse.onerror = () => {
      if (sse.readyState === EventSource.CLOSED) {
        // SSE closed
      }
    };

    return () => {
      sse.close();
    };
  }, [orgJobId]);

  const handleAbortScan = async (mode: "pending" | "force") => {
    if (!orgJobId) return;

    if (mode === "force") {
      setOrgStatusData(null);
      try {
        await abortOrganizationScan(orgJobId, mode);
      } catch (err) {
        console.error("Failed to abort scan", err);
      }
      onCloseRef.current?.(orgJobId);
      return;
    }

    setIsAborting(true);
    try {
      await abortOrganizationScan(orgJobId, mode);
    } catch (err) {
      console.error("Failed to abort scan", err);
    } finally {
      setIsAborting(false);
    }
  };

  return {
    orgStatusData,
    setOrgStatusData,
    isAborting,
    handleAbortScan,
  };
}