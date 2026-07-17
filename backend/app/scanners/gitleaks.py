from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ..models import Finding, Location
from ..utils.categories import normalize_category
from ..utils.exec import run_cmd
from ..utils.ml_features import extract_features


def run_gitleaks(repo_dir: Path, raw_out: Path = None) -> List[Finding]:
    cmd = [
        "gitleaks",
        "detect",
        "--no-git",
        "--redact",
        "--report-format",
        "json",
        "--report-path",
        "gitleaks.json",
    ]
    r = run_cmd(cmd, cwd=repo_dir, timeout_s=600)

    report = repo_dir / "gitleaks.json"
    if not report.exists():
        if r["returncode"] != 0 and r["stderr"]:
            return [
                Finding(
                    id="gitleaks:error",
                    category=normalize_category("secret"),
                    severity="INFO",
                    title="Gitleaks failed to run",
                    description=r["stderr"][:5000],
                )
            ]
        return []

    # Persist raw output before any parsing so the evidence pack can read it
    if raw_out is not None:
        raw_out.parent.mkdir(parents=True, exist_ok=True)
        raw_out.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")

    try:
        data = json.loads(report.read_text(encoding="utf-8") or "[]")
    except Exception:
        return []

    out: List[Finding] = []
    for item in data:
        rule = item.get("RuleID", "secret")
        path = item.get("File", "")
        start = item.get("StartLine")
        end = item.get("EndLine")
        desc = item.get("Description", "") or item.get("Match", "")

        finding_id = f"gitleaks:{rule}:{path}:{start}"
        severity = "CRITICAL"

        raw_data_for_extractor = {
            "id": finding_id,
            "severity": severity,
            "location": {"path": path},
            "metadata": {"cwe_category": "CWE-798"},
        }

        ml_features = extract_features(raw_data_for_extractor, scanner_name="gitleaks")

        out.append(
            Finding(
                id=finding_id,
                category=normalize_category("secret"),
                severity=severity,
                title=f"Secret detected: {rule}",
                description=str(desc)[:1000],
                location=Location(path=path, start_line=start, end_line=end),
                metadata={"engine": "gitleaks", "rule": rule},
                features=ml_features,  # <--- INJECTED HERE
            )
        )
    return out
