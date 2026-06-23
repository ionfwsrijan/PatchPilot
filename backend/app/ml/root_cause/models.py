from __future__ import annotations

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from ..models import Finding

class RootCauseFinding(BaseModel):
    """A simplified representation of a finding used for clustering."""
    id: str
    title: str
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class RootCauseGroup(BaseModel):
    """Represents a root‑cause cluster of findings.

    Attributes
    ----------
    id: str
        Unique identifier for the group.
    job_id: str
        The scan job this group belongs to.
    root_cause: str
        Human‑readable description of the inferred root cause.
    confidence: float
        Confidence score (0‑1) based on average pairwise cosine similarity.
    findings_count: int
        Number of findings in this group.
    findings: List[RootCauseFinding]
        The findings that belong to the group.
    """
    id: str
    job_id: str
    root_cause: str
    confidence: float
    findings_count: int
    findings: List[RootCauseFinding]

class RootCauseResponse(BaseModel):
    """API response wrapper for root‑cause groups of a job."""
    job_id: str
    groups: List[RootCauseGroup]
