import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { saveLastScan } from "../lib/scan-store";

export type UiJobStatus = "completed" | "running" | "failed" | "pending";

export type UiJob = {
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

export function useRecentJobs() {
  const navigate = useNavigate();
  const [recentJobs, setRecentJobs] = useState<UiJob[]>(getLocalRecentJobs);

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

    const currentJobs = getLocalRecentJobs();
    const next = [job, ...currentJobs.filter((j) => j.id !== job.id)].slice(0, 10);
    localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
    
    setRecentJobs(next);
    navigate("/findings");
  }, [navigate]);

  const onClearRecents = useCallback(() => {
    localStorage.removeItem(RECENTS_KEY);
    setRecentJobs([]);
  }, []);

  return {
    recentJobs,
    handleScanSuccess,
    onClearRecents
  };
}