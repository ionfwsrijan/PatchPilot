from __future__ import annotations

from typing import List, Dict, Any
from pydantic import BaseModel, Field

class NormalizedFinding(BaseModel):
    """A normalized representation of a finding from any scanner.

    Attributes
    ----------
    id: str
        Unique identifier of the finding.
    category: str
        Normalized category (e.g., "secret", "dependency", "sast").
    severity: str
        Original severity string.
    title: str
        Short title or rule identifier.
    description: str
        Detailed description.
    metadata: Dict[str, Any]
        Raw metadata from the original finding.
    """

    id: str
    category: str
    severity: str
    title: str
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AttackStep(BaseModel):
    """A single step in an attack path.

    label: str – human readable label for the step (e.g., "AWS Secret").
    finding_id: str | None – optional reference to the underlying finding.
    """
    label: str
    finding_id: str | None = None

class AttackPath(BaseModel):
    """A complete attack path consisting of ordered steps and a risk score."""
    id: str
    steps: List[AttackStep]
    risk_score: float
