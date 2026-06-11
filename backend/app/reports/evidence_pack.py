from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..utils.exec import run_cmd


def build_evidence_pack(
    repo_dir: Path, out_dir: Path, project_name: str, job_id: str
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pack_root = out_dir / f"patchpilot_evidence_{project_name}_{job_id}_{ts}"
    pack_root.mkdir(parents=True, exist_ok=True)

    # Collect tool outputs (best effort)
    semgrep = run_cmd(
        ["semgrep", "--config", "p/ci", "--json", "--quiet"],
        cwd=repo_dir,
        timeout_s=600,
    )
    osv = run_cmd(
        ["osv-scanner", "--json", "--recursive", "."], cwd=repo_dir, timeout_s=600
    )
    gitleaks = run_cmd(
        ["gitleaks", "detect", "--no-git", "--redact", "--report-format", "json"],
        cwd=repo_dir,
        timeout_s=600,
    )

    (pack_root / "raw").mkdir(parents=True, exist_ok=True)
    (pack_root / "raw" / "semgrep.json").write_text(
        semgrep.get("stdout", ""), encoding="utf-8"
    )
    (pack_root / "raw" / "osv.json").write_text(osv.get("stdout", ""), encoding="utf-8")
    (pack_root / "raw" / "gitleaks.json").write_text(
        gitleaks.get("stdout", ""), encoding="utf-8"
    )

    report_md = _render_report(project_name=project_name, job_id=job_id)
    (pack_root / "REPORT.md").write_text(report_md, encoding="utf-8")

    zip_path = out_dir / f"{pack_root.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in pack_root.rglob("*"):
            if p.is_file():
                z.write(p, arcname=p.relative_to(pack_root).as_posix())

    return zip_path


def _render_report(project_name: str, job_id: str) -> str:
    return f"""# PatchPilot Evidence Pack

**Project:** {project_name}  
**Job ID:** {job_id}  
**Generated:** {datetime.now(timezone.utc).isoformat()}

## What this pack contains
- `raw/semgrep.json` — SAST scan results (Semgrep)
- `raw/osv.json` — Dependency vulnerability results (OSV-Scanner)
- `raw/gitleaks.json` — Secret detection results (Gitleaks)
- This `REPORT.md` summary

## Methodology (high-level)
1. Scan codebase for vulnerabilities (SAST, dependency CVEs, secrets).
2. Prioritize findings by severity and likely impact.
3. Apply or suggest minimal remediation steps.
4. Provide verification artifacts and re-scan outputs.

## Notes
- This MVP focuses on **verifiable evidence** and a clean audit trail.
- For production, integrate CI gating (GitHub Actions) and curated fix templates per language/framework.
"""
