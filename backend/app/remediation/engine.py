from __future__ import annotations

from pathlib import Path
from typing import List

from ..models import Fix
from .templates import secret_remediation_note, dependency_upgrade_note
from .patch_generator import PatchGenerator
from .osv_parser import OSVParser


def propose_fixes(repo_dir: Path, finding_ids: List[str]) -> List[Fix]:
    """Propose fixes for given finding IDs, including patch generation."""
    fixes: List[Fix] = []
    patch_gen = PatchGenerator(repo_dir)
    osv_parser = OSVParser(repo_dir)

    for fid in finding_ids:
        # Handle secret leaks (Gitleaks)
        if fid.startswith("gitleaks:"):
            fixes.append(
                Fix(
                    finding_id=fid,
                    status="suggested",
                    summary="Secrets require rotation; PatchPilot provides safe remediation steps.",
                    files_changed=[],
                    diff=None,
                    notes=secret_remediation_note(),
                )
            )
            continue

        # Handle dependency vulnerabilities (OSV) - WITH PATCH GENERATION
        if fid.startswith("osv:"):
            # Try to generate actual patch
            package_info = osv_parser.get_package_info(fid)
            diff = None
            files_changed = []

            if package_info:
                package_name, current_ver, fixed_ver = package_info
                diff = patch_gen.generate_dependency_patch(
                    package_name, current_ver, fixed_ver
                )
                if diff:
                    files_changed = [
                        (
                            "requirements.txt"
                            if "requirements" in str(diff)
                            else "package.json"
                        )
                    ]
                    summary = (
                        f"Upgrade {package_name} from {current_ver} to {fixed_ver}"
                    )
                else:
                    summary = f"Dependency vulnerability found in {package_name}"
            else:
                summary = "Dependency vulnerabilities vary by ecosystem; PatchPilot suggests upgrade workflow."

            fixes.append(
                Fix(
                    finding_id=fid,
                    status="suggested",
                    summary=summary,
                    files_changed=files_changed,
                    diff=diff,
                    notes=dependency_upgrade_note(),
                )
            )
            continue

        # Handle SAST findings (Semgrep)
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
                )
            )
            continue

        # Unknown finding type
        fixes.append(
            Fix(
                finding_id=fid,
                status="skipped",
                summary="Unsupported finding type.",
            )
        )

    return fixes
