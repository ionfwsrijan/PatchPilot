from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Location(BaseModel):
    path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None


class Reachability(BaseModel):
    reachable: bool
    evidence: Optional[str] = None


class FindingStatusUpdate(BaseModel):
    status: str = Field(
        ..., description="The new status: 'open', 'accepted', or 'ignored'"
    )


class Finding(BaseModel):
    id: str
    category: str
    severity: str
    title: str
    description: str = ""
    location: Optional[Location] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    reachability: Optional[Reachability] = None
    features: Optional[Dict[str, Any]] = Field(default_factory=dict)
    ml_score: Optional[float] = None


class ScanResponse(BaseModel):
    job_id: str
    project_name: str
    repo_path: str
    findings: List[Finding]
    scanners: Dict[str, Any]


class Fix(BaseModel):
    finding_id: str
    status: str
    summary: str
    files_changed: List[str] = Field(default_factory=list)
    diff: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class FixRequest(BaseModel):
    job_id: str
    finding_ids: List[str]


class FixResponse(BaseModel):
    job_id: str
    fixes: List[Fix]


class VerifyResponse(BaseModel):
    ok: bool
    checks: Dict[str, Any]


class OrgScanRequest(BaseModel):
    org_url: str


class RepoStatus(BaseModel):
    job_id: str
    project_name: str
    status: str


class OrgJobStatusResponse(BaseModel):
    org_job_id: str
    status: str
    repos: List[RepoStatus]
