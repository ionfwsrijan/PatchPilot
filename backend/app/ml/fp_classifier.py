"""Deterministic false-positive heuristics.

classify() returns an estimated probability in [0.0, 1.0] that a finding is a
false positive, from a weighted sum of simple signals. No model is involved.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import PurePosixPath
from typing import Any

import yaml

RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fp_rules.yaml")

LIKELY_FP_THRESHOLD = 0.7

TEST_PATH_DIRS = {
    "tests",
    "test",
    "__tests__",
    "spec",
    "fixtures",
    "examples",
    "sample",
    "demo",
    "mock",
}

WEIGHT_TEST_PATH = 0.35
WEIGHT_LOW_SEVERITY = 0.20
WEIGHT_MISSING_CVE = 0.15
WEIGHT_NOISY_RULE = 0.30

# Base bias by scanner; secrets and dependency advisories are rarely noise.
SCANNER_BIAS = {
    "semgrep": 0.10,
    "entropy": 0.10,
    "gitleaks": 0.0,
    "osv": 0.0,
}
LOW_SEVERITY_MAX = 3


@lru_cache(maxsize=4)
def load_noisy_rules(path: str = RULES_PATH) -> dict[str, tuple[str, ...]]:
    """Load noisy rule IDs per scanner from the YAML config."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except OSError:
        return {}
    return {
        str(scanner).lower(): tuple(str(r) for r in (rules or []))
        for scanner, rules in data.items()
    }


def _is_test_path(file_path: str) -> bool:
    parts = PurePosixPath(file_path.replace("\\", "/").lower()).parts
    return any(part in TEST_PATH_DIRS for part in parts[:-1])


def _is_noisy_rule(scanner: str, rule_id: str, rules_path: str) -> bool:
    if not rule_id:
        return False
    for entry in load_noisy_rules(rules_path).get(scanner, ()):
        if rule_id == entry or rule_id.endswith("." + entry):
            return True
    return False


def _has_vuln_identifier(finding: dict[str, Any]) -> bool:
    metadata = finding.get("metadata") or {}
    return bool(
        finding.get("cwe")
        or finding.get("cve")
        or finding.get("advisory")
        or metadata.get("cve")
        or metadata.get("osv_id")
        or metadata.get("advisory")
    )


def classify(finding: dict[str, Any], rules_path: str = RULES_PATH) -> float:
    """Return the probability that a finding is a false positive."""
    scanner = str(finding.get("scanner") or "").lower()
    score = SCANNER_BIAS.get(scanner, 0.05)

    if _is_test_path(str(finding.get("file_path") or "")):
        score += WEIGHT_TEST_PATH

    severity_score = finding.get("severity_score")
    if severity_score is not None and severity_score <= LOW_SEVERITY_MAX:
        score += WEIGHT_LOW_SEVERITY

    # Secrets and dependency advisories carry their own identity, so a missing
    # CVE only counts against code-analysis findings.
    if scanner not in ("gitleaks", "osv") and not _has_vuln_identifier(finding):
        score += WEIGHT_MISSING_CVE

    if _is_noisy_rule(scanner, str(finding.get("rule_id") or ""), rules_path):
        score += WEIGHT_NOISY_RULE

    return round(min(1.0, max(0.0, score)), 3)


def is_likely_false_positive(score: float) -> bool:
    return score > LIKELY_FP_THRESHOLD
