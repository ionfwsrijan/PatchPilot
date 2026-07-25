from __future__ import annotations

from pathlib import Path
from typing import List

from ..models import Fix
from .templates import dependency_upgrade_note, secret_remediation_note


def propose_fixes(repo_dir: Path, finding_ids: List[str]) -> List[Fix]:
    fixes: List[Fix] = []

    for fid in finding_ids:
        if fid.startswith("gitleaks:"):
            fixes.append(
                Fix(
                    finding_id=fid,
                    status="suggested",
                    summary="Secrets require rotation; PatchPilot provides safe remediation steps.",
                    files_changed=[],
                    diff=None,
                    fix_confidence=None,
                    notes=secret_remediation_note(),
                )
            )
            continue

        if fid.startswith("osv:"):
            fixes.append(
                Fix(
                    finding_id=fid,
                    status="suggested",
                    summary="Dependency vulnerabilities vary by ecosystem; PatchPilot suggests upgrade workflow.",
                    files_changed=[],
                    diff=None,
                    fix_confidence=0.65,
                    notes=dependency_upgrade_note(),
                )
            )
            continue

        if fid.startswith("semgrep:"):
            fixes.append(
                Fix(
                    finding_id=fid,
                    status="suggested",
                    summary="SAST finding detected; suggested remediation depends on code context.",
                    notes=[
                        "For hackathon MVP, PatchPilot focuses on verified scanning + evidence generation.",
                        "Next step: add ecosystem-specific fix templates (SQL injection, SSRF, command injection).",
                    ],
                    fix_confidence=0.82,
                )
            )
            continue

        fixes.append(
            Fix(
                finding_id=fid,
                status="skipped",
                summary="Unsupported finding type.",
                fix_confidence=0.25,
            )
        )

    return fixes
