export const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

export type HealthResponse = {
  ok: boolean;
  status: "healthy" | "degraded";
  scanners: Record<string, boolean>;
};

export async function getHealth() {
  const res = await fetch(`${API_BASE}/health`);

  if (!res.ok) {
    throw new Error(await res.text());
  }

  return (await res.json()) as HealthResponse;
}

export type ScanResponse = {
  job_id: string;
  project_name: string;
  repo_path: string;
  scanners: Record<string, { ok: boolean; count: number }>;
  findings: BackendFinding[];
};

export type BackendFinding = {
  id: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
  category: string;
  title: string;
  description?: string;

  location?: {
    path?: string;
    start_line?: number;
    end_line?: number;
  };

  metadata?: {
    engine?: string;
    [key: string]: unknown;
  };

  reachability?: {
  reachable?: boolean;
  reason?: string;
};

features?: Record<string, unknown>;
  confidence?: number;
  code?: string;
  suggested_fix?: string;
  references?: string[];
  ml_score?: number;
  false_positive?: boolean | number | null;
  version?: number;
};

export type ScanInitResponse = {
  job_id: string;
  project_name: string;
  status: string;
};

export async function scanZip(file: File, projectName = "project") {
  const form = new FormData();
  form.append("project", file);
  form.append("project_name", projectName);

  const res = await fetch(`${API_BASE}/scan`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as ScanInitResponse;
}

export async function scanRepoUrl(
  repoUrl: string,
  ref = "main",
  projectName = "project",
) {
  const form = new FormData();
  form.append("repo_url", repoUrl);
  form.append("ref", ref);
  form.append("project_name", projectName);

  const res = await fetch(`${API_BASE}/scan-url`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail ?? "Import from URL failed");
  }

  return (await res.json()) as ScanInitResponse;
}
export async function getJobFindings(jobId: string): Promise<BackendFinding[]> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/findings`);
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as BackendFinding[];
}

export async function labelFinding(
  findingId: string,
  falsePositive: boolean,
  expectedVersion: number,
  signal?: AbortSignal,
) {
  const res = await fetch(`${API_BASE}/findings/${findingId}/label`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ false_positive: falsePositive, expected_version: expectedVersion }),
    signal,
  });
  if (!res.ok) {
    const errText = await res.text();
    const error = new Error(errText);
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

export async function updateFindingStatus(findingId: string, status: "open" | "accepted" | "ignored") {
  const res = await fetch(`${API_BASE}/findings/${findingId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fix(jobId: string, findingIds: string[]) {
  const res = await fetch(`${API_BASE}/fix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, finding_ids: findingIds }),
  });

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function verify(jobId: string) {
  const form = new FormData();
  form.append("job_id", jobId);

  const res = await fetch(`${API_BASE}/verify`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * POST /evidence-pack -> returns a ZIP (FileResponse)
 * This fetches it as a Blob and tries to infer a filename from Content-Disposition.
 */
export async function downloadEvidencePack(
  jobId: string,
  projectName = "project",
) {
  const form = new FormData();
  form.append("job_id", jobId);
  form.append("project_name", projectName);

  const res = await fetch(`${API_BASE}/evidence-pack`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }

  const blob = await res.blob();

  const cd = res.headers.get("content-disposition") || "";
  const match = cd.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] || `evidence-pack-${jobId}.zip`;

  return { blob, filename };
}

export type TrendData = {
  date: string;
  findings: number;
};

export async function getTrends(limit = 6) {
  const res = await fetch(`${API_BASE}/trends?limit=${limit}`);
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as TrendData[];
}

export type CweData = {
  name: string;
  value: number;
};

export async function getCweDistribution() {
  const res = await fetch(`${API_BASE}/cwe-distribution`);
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as CweData[];
}

export interface DepFinding {
  id: string;
  rule_id: string;
  severity: string;
  message: string;
  package_name: string;
  package_version: string;
}

export interface DependencyDiffResult {
  introduced: DepFinding[];
  resolved: DepFinding[];
  persistent: DepFinding[];
}

export const getDependencyDiff = async (): Promise<DependencyDiffResult> => {
  const response = await fetch(`${API_BASE}/dependency-diff`);
  if (!response.ok) {
    throw new Error("Failed to fetch dependency diff");
  }
  return response.json();
};

export interface ContributorStat {
  github_username: string;
  findings_closed: number;
  fixes_passed: number;
  prs_merged: number;
  last_updated: string;
  total_score: number;
}

export interface LeaderboardUpdateRequest {
  github_username: string;
  pr_description?: string;
  fixes_passed?: number;
  is_pr_merged?: boolean;
}

export async function getLeaderboard(): Promise<ContributorStat[]> {
  const res = await fetch(`${API_BASE}/leaderboard`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateLeaderboard(data: LeaderboardUpdateRequest) {
  const res = await fetch(`${API_BASE}/leaderboard/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function downloadAuditReport(jobId: string) {
  const res = await fetch(`${API_BASE}/api/scans/${jobId}/report/pdf`);
  
  if (!res.ok) {
    throw new Error(await res.text());
  }

  const blob = await res.blob();
  return { blob, filename: `PatchPilot-Audit-${jobId}.pdf` };
}

export type RepoStatus = {
  job_id: string;
  project_name: string;
  status: "pending" | "scanning" | "completed" | "failed" | "aborted";
};

export type OrgJobStatusResponse = {
  org_job_id: string;
  status: "pending" | "scanning" | "completed" | "failed" | "aborted";
  repos: RepoStatus[];
};

export async function scanOrganization(orgUrl: string) {
  const res = await fetch(`${API_BASE}/api/scans/org`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ org_url: orgUrl }),
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }

  return (await res.json()) as { org_job_id: string; org_name: string; repo_count: number };
}

export async function getOrgJobStatus(orgJobId: string) {
  const res = await fetch(`${API_BASE}/api/scans/org/${orgJobId}/status`);

  if (!res.ok) {
    throw new Error(await res.text());
  }

  return (await res.json()) as OrgJobStatusResponse;
}

export const abortOrganizationScan = async (orgJobId: string, mode: "pending" | "force" = "pending") => {
  const response = await fetch(`${API_BASE}/api/scans/org/${orgJobId}/abort?mode=${mode}`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Failed to abort scan");
  return response.json();
};

export async function getOrgSummary(orgJobId: string) {
  const res = await fetch(`${API_BASE}/api/scans/org/${orgJobId}/summary`);
  if (!res.ok) throw new Error("Failed to fetch organization summary");
  return res.json();
}

export async function getOrgFindings(orgJobId: string) {
  const res = await fetch(`${API_BASE}/api/scans/org/${orgJobId}/findings`);
  if (!res.ok) throw new Error("Failed to fetch organization findings");
  return res.json();
}

export async function downloadOrgAuditReport(orgJobId: string) {
  const res = await fetch(`${API_BASE}/api/scans/org/${orgJobId}/report/pdf`);
  
  if (!res.ok) {
    throw new Error(await res.text());
  }

  const blob = await res.blob();
  
  const cd = res.headers.get("content-disposition") || "";
  const match = cd.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] || `PatchPilot-Org-Audit-${orgJobId}.pdf`;

  return { blob, filename };
}

export const getOrgBlastRadius = async (orgJobId: string) => {
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const response = await fetch(`${baseUrl}/api/scans/org/${orgJobId}/blast-radius`);
  
  if (!response.ok) {
    throw new Error('Failed to fetch blast radius data');
  }
  return response.json();
};

export interface OllamaHealthResponse {
  available: boolean;
  models: string[];
  base_url: string;
}

export async function getOllamaHealth(): Promise<OllamaHealthResponse> {
  const res = await fetch(`${API_BASE}/api/health/ollama`);
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}