from __future__ import annotations

from typing import Dict

from .models import AttackPath, AttackStep

# Severity to numeric score (same as earlier prioritization)
_SEVERITY_SCORE: Dict[str, int] = {
    "CRITICAL": 100,
    "HIGH": 80,
    "MEDIUM": 50,
    "LOW": 20,
    "INFO": 5,
}

# Category weight – higher weight for more exploitable categories
_CATEGORY_WEIGHT: Dict[str, int] = {
    "secret": 35,
    "dependency": 25,
    "privilege_escalation": 30,
    "sast": 20,
}

def _step_score(step: AttackStep) -> int:
    """Calculate a base score for a single step.

    If the step is linked to a finding (has ``finding_id``) we look at its
    ``category`` and ``severity`` via the underlying ``AttackStep`` label – the
    label is typically the finding title, but we also store the original
    ``category`` in the step's metadata when available.  For intermediate nodes
    created by the correlation engine we fall back to the category weight only.
    """
    # For intermediate nodes the label comes from ``_CORRELATION_MAP`` – we can
    # infer a pseudo‑category based on the label.
    label = step.label.lower()
    # Attempt to map label back to a known category; this is heuristic but works
    # for the deterministic rules used.
    if "secret" in label:
        category = "secret"
    elif "dependency" in label or "cve" in label:
        category = "dependency"
    elif "privilege" in label:
        category = "privilege_escalation"
    else:
        category = "sast"

    cat_weight = _CATEGORY_WEIGHT.get(category, 10)
    # No severity for intermediate nodes – use a default medium value.
    sev_score = 50 if step.finding_id is None else _SEVERITY_SCORE.get(step.label.upper(), 30)
    return cat_weight + sev_score

def calculate_risk(path: AttackPath) -> float:
    """Calculate a risk score for an attack path.

    The risk is a weighted sum of step scores, adjusted by chain length.  The
    final value is capped to the 0‑100 range.
    """
    if not path.steps:
        return 0.0
    base = sum(_step_score(step) for step in path.steps)
    length_factor = len(path.steps) * 5  # each step adds up to 5 points
    raw_score = base + length_factor
    # Normalise to 0‑100 – the maximum plausible raw_score is roughly 250.
    normalized = min(100.0, (raw_score / 250.0) * 100.0)
    return round(normalized, 2)
