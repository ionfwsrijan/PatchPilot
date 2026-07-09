import { useState, useCallback } from "react";
import { scanOrganization } from "../lib/api";

export function useOrganizationScan() {
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

  const resetOrgScan = useCallback(() => {
    setActiveOrgJobId(null);
    setOrgScanLoading(false);
  }, []);

  return {
    orgScanLoading,
    orgScanError,
    activeOrgJobId,
    expectedRepoCount,
    handleScanOrg,
    resetOrgScan,
    setOrgScanError
  };
}