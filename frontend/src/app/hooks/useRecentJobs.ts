import { useState, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { saveLastScan } from "../lib/scan-store";
import { listJobs } from "../lib/api";

export type UiJobStatus = "completed" | "running" | "failed" | "pending";

export type UiJob = {
  id: string;
  repoName: string;
  status: UiJobStatus;
  timestamp: string;
  duration?: string;
  findingsCount: number;
};

const CLEARED_KEY = "patchpilot:clearedJobs";

function getClearedJobIds(): string[] {
  const raw = localStorage.getItem(CLEARED_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function useRecentJobs() {
  const navigate = useNavigate();
  const [recentJobs, setRecentJobs] = useState<UiJob[]>([]);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await listJobs(10, 0);
      const clearedIds = getClearedJobIds();
      const filtered = res.jobs
        .filter((j) => !clearedIds.includes(j.job_id))
        .map((j) => ({
          id: j.job_id,
          repoName: j.project_name,
          status: j.status as UiJobStatus,
          timestamp: j.created_at,
          duration: "-",
          findingsCount: j.finding_count ?? 0,
        }));
      setRecentJobs(filtered);
    } catch (err) {
      console.error("Failed to fetch recent jobs:", err);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const handleScanSuccess = useCallback((scan: { job_id: string; project_name: string; findings?: any[] }) => {
    saveLastScan(scan as any);

    const job: UiJob = {
      id: scan.job_id,
      repoName: scan.project_name,
      status: "completed",
      timestamp: new Date().toISOString(),
      duration: "-",
      findingsCount: scan.findings?.length ?? 0,
    };

    setRecentJobs((prev) => [job, ...prev.filter((j) => j.id !== job.id)].slice(0, 10));
    navigate(`/findings?job_id=${scan.job_id}`);
  }, [navigate]);

  const onClearRecents = useCallback(() => {
    const jobIds = recentJobs.map((j) => j.id);
    const clearedIds = getClearedJobIds();
    const next = Array.from(new Set([...clearedIds, ...jobIds]));
    localStorage.setItem(CLEARED_KEY, JSON.stringify(next));
    setRecentJobs([]);
  }, [recentJobs]);

  return {
    recentJobs,
    handleScanSuccess,
    onClearRecents
  };
}