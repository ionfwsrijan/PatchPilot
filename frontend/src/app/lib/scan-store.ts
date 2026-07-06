import type { ScanResponse } from "./api";

const KEY = "patchpilot:lastScan";

export function saveLastScan(scan: ScanResponse) {
  const { findings, ...lightweightScan } = scan;
  const storageData = { 
    ...lightweightScan, 
    finding_count: findings?.length || 0 
  };
  
  localStorage.setItem(KEY, JSON.stringify(storageData));
}

export function loadLastScan(): ScanResponse | null {
  const raw = localStorage.getItem(KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return {
      ...parsed,
      findings: []
    } as ScanResponse;
  } catch {
    return null;
  }
}