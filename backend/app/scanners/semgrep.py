from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ..models import Finding, Location
from ..utils.categories import normalize_category
from ..utils.exec import run_cmd
from ..utils.ml_features import extract_features

SEMGREP_CONFIGS = ["p/ci", "p/dockerfile", "p/terraform", "p/github-actions"]


def run_semgrep(repo_dir: Path, raw_out: Path = None) -> List[Finding]:
    cmd = ["semgrep"]
    for conf in SEMGREP_CONFIGS:
        cmd.extend(["--config", conf])
    cmd.extend(["--json", "--quiet"])
    r = run_cmd(cmd, cwd=repo_dir, timeout_s=600)

    # Persist raw output before any parsing so the evidence pack can read it
    if raw_out is not None:
        raw_out.parent.mkdir(parents=True, exist_ok=True)
        raw_out.write_text(r.get("stdout", ""), encoding="utf-8")

    if r["returncode"] not in (0, 1):
        return [
            Finding(
                id="semgrep:error",
                category=normalize_category("sast"),
                severity="INFO",
                title="Semgrep failed to run",
                description=r["stderr"][:5000],
            )
        ]

    try:
        data = json.loads(r["stdout"] or "{}")
    except Exception:
        return []

    out: List[Finding] = []
    for res in data.get("results", []) or []:
        check_id = res.get("check_id", "semgrep:unknown")
        path = res.get("path")
        start = (res.get("start") or {}).get("line")
        end = (res.get("end") or {}).get("line")

        extra = res.get("extra") or {}
        msg = extra.get("message", "")
        raw_severity = (extra.get("severity") or "INFO").upper()

        if raw_severity == "ERROR":
            severity = "HIGH"
        elif raw_severity == "WARNING":
            severity = "MEDIUM"
        elif raw_severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            severity = raw_severity
        else:
            severity = "INFO"
        finding_id = f"semgrep:{check_id}:{path}:{start}"

        cwe_data = (extra.get("metadata") or {}).get("cwe", "unknown")
        cwe_category = (
            str(cwe_data[0])
            if isinstance(cwe_data, list) and cwe_data
            else str(cwe_data)
        )

        raw_data_for_extractor = {
            "id": check_id,
            "severity": severity,
            "location": {"path": path},
            "metadata": {"cwe_category": cwe_category},
        }

        ml_features = extract_features(raw_data_for_extractor, scanner_name="semgrep")

        out.append(
            Finding(
                id=finding_id,
                category=normalize_category("sast"),
                severity=severity,
                title=check_id,
                description=msg,
                location=Location(path=path, start_line=start, end_line=end),
                metadata={"check_id": check_id, "engine": "semgrep"},
                features=ml_features,
            )
        )
    return out
