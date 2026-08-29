from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Location(BaseModel):
    path: str = Field(
        ...,
        description="Relative file path where the finding or vulnerability was detected.",
        examples=["src/auth/jwt.py"],
    )
    start_line: Optional[int] = Field(
        default=None,
        ge=1,
        description="Starting line number in the source file (1-indexed).",
        examples=[42],
    )
    end_line: Optional[int] = Field(
        default=None,
        ge=1,
        description="Ending line number in the source file (1-indexed).",
        examples=[48],
    )


class Reachability(BaseModel):
    reachable: bool = Field(
        ...,
        description="Indicates whether the vulnerable code path is execution-reachable.",
        examples=[True],
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Contextual trace or proof showing how the vulnerable path can be reached.",
        examples=["User input flows into unauthenticated exec() call at src/auth/jwt.py:42"],
    )


class FindingStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        description="The new status assigned to the finding: 'open', 'accepted', or 'ignored'.",
        examples=["accepted"],
    )


class Finding(BaseModel):
    id: str = Field(
        ...,
        description="Unique identifier for the finding.",
        examples=["FINDING-1024"],
    )
    category: str = Field(
        ...,
        description="Security weakness category or classification.",
        examples=["Hardcoded Secret"],
    )
    severity: str = Field(
        ...,
        description="Assigned severity rating for the finding.",
        examples=["high"],
    )
    title: str = Field(
        ...,
        description="Short, human-readable summary of the detected finding.",
        examples=["Hardcoded API Secret in Authentication Middleware"],
    )
    description: str = Field(
        default="",
        description="Detailed explanation of the issue and potential security risk.",
        examples=["An API key is embedded directly in source code, exposing it to potential leakage."],
    )
    location: Optional[Location] = Field(
        default=None,
        description="Source code location details associated with the finding.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Scanner-specific metadata and raw property key-value pairs.",
        examples=[{"rule_id": "python-hardcoded-secret", "cwe": "CWE-798"}],
    )
    reachability: Optional[Reachability] = Field(
        default=None,
        description="Reachability analysis result indicating whether code is exploitable.",
    )
    features: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Extracted feature vectors or contextual properties used for ML scoring.",
        examples=[{"is_public_api": True, "has_sanitizer": False}],
    )
    ml_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score (between 0.0 and 1.0) calculated by machine learning triage models.",
        examples=[0.89],
    )


class ScanResponse(BaseModel):
    job_id: str = Field(
        ...,
        description="Unique job identifier for the executed code scan.",
        examples=["job-98765"],
    )
    project_name: str = Field(
        ...,
        description="Name of the repository or project that was scanned.",
        examples=["backend-service"],
    )
    repo_path: str = Field(
        ...,
        description="File path or URL of the analyzed repository.",
        examples=["/repos/backend-service"],
    )
    findings: List[Finding] = Field(
        ...,
        description="List of security findings detected during the scan.",
    )
    scanners: Dict[str, Any] = Field(
        ...,
        description="Summary and execution details of the underlying security scanners.",
        examples=[{"semgrep": {"status": "completed", "duration_seconds": 1.2}}],
    )


class Fix(BaseModel):
    finding_id: str = Field(
        ...,
        description="Identifier of the target finding addressed by this fix.",
        examples=["FINDING-1024"],
    )
    status: str = Field(
        ...,
        description="Generation status of the patch fix (e.g., 'applied', 'failed', 'pending').",
        examples=["applied"],
    )
    summary: str = Field(
        ...,
        description="Overview of the changes introduced by the patch.",
        examples=["Extracted hardcoded key to environment variable loader."],
    )
    files_changed: List[str] = Field(
        default_factory=list,
        description="List of file paths modified by the generated patch.",
        examples=[["src/auth/jwt.py", "config/settings.py"]],
    )
    diff: Optional[str] = Field(
        default=None,
        description="Unified git diff string representing the precise code patch.",
        examples=["--- a/src/auth/jwt.py\n+++ b/src/auth/jwt.py\n@@ -42,1 +42,1 @@\n-SECRET = '12345'\n+SECRET = os.getenv('JWT_SECRET')"],
    )
    notes: List[str] = Field(
        default_factory=list,
        description="Additional operational or review notes for developers regarding the fix.",
        examples=[["Ensure JWT_SECRET environment variable is set in production deployment."]],
    )
    fix_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score (between 0.0 and 1.0) estimating fix correctness.",
        examples=[0.95],
    )


class FixRequest(BaseModel):
    job_id: str = Field(
        ...,
        description="Unique scan job identifier containing the target findings.",
        examples=["job-98765"],
    )
    finding_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of finding IDs to generate fixes for.",
        examples=[["FINDING-1024"]],
    )


class FixResponse(BaseModel):
    job_id: str = Field(
        ...,
        description="Unique scan job identifier for which fixes were generated.",
        examples=["job-98765"],
    )
    fixes: List[Fix] = Field(
        ...,
        description="List of generated fixes corresponding to the requested findings.",
    )


class VerifyResponse(BaseModel):
    ok: bool = Field(
        ...,
        description="Indicates whether all automated verification checks passed.",
        examples=[True],
    )
    checks: Dict[str, Any] = Field(
        ...,
        description="Detailed breakdown of individual verification test results (e.g., unit tests, linting).",
        examples=[{"unit_tests": "passed", "linter": "passed"}],
    )


class OrgScanRequest(BaseModel):
    org_url: str = Field(
        ...,
        description="URL of the GitHub organization or target workspace to scan.",
        examples=["https://github.com/my-org"],
    )


class RepoStatus(BaseModel):
    job_id: str = Field(
        ...,
        description="Scan job ID associated with this repository.",
        examples=["job-98765"],
    )
    project_name: str = Field(
        ...,
        description="Repository name within the organization.",
        examples=["my-org/auth-service"],
    )
    status: str = Field(
        ...,
        description="Current scan execution state (e.g., 'queued', 'running', 'completed', 'failed').",
        examples=["completed"],
    )


class OrgJobStatusResponse(BaseModel):
    org_job_id: str = Field(
        ...,
        description="Unique job identifier tracking the entire organization batch scan.",
        examples=["org-job-4321"],
    )
    status: str = Field(
        ...,
        description="Overall execution status of the organization scan.",
        examples=["in_progress"],
    )
    repos: List[RepoStatus] = Field(
        ...,
        description="Status breakdown for individual repositories in the organization batch.",
    )
    