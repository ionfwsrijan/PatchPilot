import { useState, useEffect, useCallback } from "react";
import { scanOrganization, getOrgJobStatus, abortOrganizationScan, API_BASE, type OrgJobStatusResponse } from "../lib/api";
import { useNavigate } from "react-router-dom";

export function useOrganizationScan() {
  const navigate = useNavigate();
  const [orgScanLoading, setOrgScanLoading] = useState(false);
  const [orgScanError, setOrgScanError] = useState<string | null>(null);
  const [activeOrgJobId, setActiveOrgJobId] = useState<string | null>(null);
  const [orgStatusData, setOrgStatusData] = useState<OrgJobStatusResponse | null>(null);
  const [expectedRepoCount, setExpectedRepoCount] = useState<number>(0);
  const [isAborting, setIsAborting] = useState(false);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);

  useEffect(() => {
    return () => {
      if (eventSource) eventSource.close();
    };
  }, [eventSource]);

  const handleScanOrg = async (url: string, onSuccessCallback?: () => void) => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      setOrgScanError("Please enter a valid GitHub Organization URL.");
      return;
    }

    setOrgScanError(null);
    setOrgScanLoading(true);
    if (eventSource) {
      eventSource.close();
      setEventSource(null);
    }

    try {
      const data = await scanOrganization(trimmedUrl);
      setActiveOrgJobId(data.org_job_id);
      setExpectedRepoCount(data.repo_count);
      if (onSuccessCallback) onSuccessCallback();

      getOrgJobStatus(data.org_job_id).then(setOrgStatusData).catch(() => {});

      const sse = new EventSource(`${API_BASE}/api/scans/org/${data.org_job_id}/stream`);

      sse.onmessage = (event) => {
        const parsed = JSON.parse(event.data);
        if (parsed.error) {
          sse.close();
          setOrgScanLoading(false);
          return;
        }

        setOrgStatusData(parsed as OrgJobStatusResponse);
        const isFullyFinished =
          ["completed", "failed"].includes(parsed.status) ||
          (parsed.status === "aborted" && !parsed.repos.some((r: any) => r.status === "scanning" || r.status === "pending"));

        if (isFullyFinished) {
          sse.close();
          setOrgScanLoading(false);
        }
      };

      sse.onerror = () => {
        if (sse.readyState === EventSource.CLOSED) setOrgScanLoading(false);
      };

      setEventSource(sse);
    } catch (e: any) {
      setOrgScanError(e?.message ?? "Organization batch scan failed");
      setOrgScanLoading(false);
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
      setOrgScanLoading(false);
    } else {
      setIsAborting(true);
    }

    try {
      await abortOrganizationScan(activeOrgJobId, mode);
    } catch (err) {
      console.error("Failed to abort scan", err);
    } finally {
      if (mode !== "force") setIsAborting(false);
    }
  };

  const closeOrgScan = useCallback(() => {
    if (eventSource) eventSource.close();
    const finalJobId = activeOrgJobId;
    setActiveOrgJobId(null);
    setOrgStatusData(null);
    setOrgScanLoading(false);
    if (finalJobId) navigate(`/org-findings/${finalJobId}`);
  }, [eventSource, activeOrgJobId, navigate]);

  return {
    orgScanLoading,
    orgScanError,
    activeOrgJobId,
    orgStatusData,
    expectedRepoCount,
    isAborting,
    handleScanOrg,
    handleAbortScan,
    closeOrgScan,
    setOrgScanError
  };
}
