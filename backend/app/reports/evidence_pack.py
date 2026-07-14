from __future__ import annotations

import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def build_evidence_pack(
    repo_dir: Path,
    out_dir: Path,
    project_name: str,
    job_id: str,
    job_dir: Path = None,
    regression_data: dict | None = None,
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pack_root = out_dir / f"patchpilot_evidence_{project_name}_{job_id}_{ts}"
    pack_root.mkdir(parents=True, exist_ok=True)

    if job_dir is not None:
        raw_dir = job_dir / "raw"
    else:
        logger.warning(
            "build_evidence_pack called without job_dir; falling back to "
            "repo_dir.parent / 'raw' (%s). Pass job_dir explicitly to avoid "
            "incorrect path resolution when _maybe_use_single_top_folder is applied.",
            repo_dir.parent / "raw",
        )
        raw_dir = repo_dir.parent / "raw"

    def _read_raw(name: str) -> str:
        path = raw_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8")
        logger.warning(
            "Raw scan artifact '%s' not found at %s — "
            "the evidence pack will contain an empty entry for this scanner.",
            name,
            path,
        )
        return ""

    semgrep_content = _read_raw("semgrep.json")
    osv_content = _read_raw("osv.json")
    gitleaks_content = _read_raw("gitleaks.json")

    (pack_root / "raw").mkdir(parents=True, exist_ok=True)
    (pack_root / "raw" / "semgrep.json").write_text(semgrep_content, encoding="utf-8")
    (pack_root / "raw" / "osv.json").write_text(osv_content, encoding="utf-8")
    (pack_root / "raw" / "gitleaks.json").write_text(gitleaks_content, encoding="utf-8")

    has_verify = False
    if job_dir is not None:
        raw_verify_dir = job_dir / "raw_verify"
        if raw_verify_dir.exists():
            has_verify = True
            (pack_root / "raw_verify").mkdir(parents=True, exist_ok=True)
            for f in [
                "semgrep.json",
                "osv.json",
                "gitleaks.json",
                "verification-report.json",
            ]:
                src = raw_verify_dir / f
                if src.exists():
                    (pack_root / "raw_verify" / f).write_text(
                        src.read_text(encoding="utf-8"), encoding="utf-8"
                    )

    report_md = _render_report(
        project_name=project_name, job_id=job_id, has_verify=has_verify
    )
    (pack_root / "REPORT.md").write_text(report_md, encoding="utf-8")
    write_security_regression_report(pack_root, regression_data)

    zip_path = out_dir / f"{pack_root.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in pack_root.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(p.relative_to(pack_root)))

    return zip_path

def write_security_regression_report(
    pack_root: Path,
    regression_data: dict | None = None,
):
    """
    Writes security regression artifacts into the evidence pack.
    """

    if regression_data is None:
        regression_data = {
            "baseline_scan": None,
            "current_scan": None,
            "introduced": [],
            "resolved": [],
            "persistent": [],
            "regressions": {},
            "improvements": {},
            "overall_trend": "Unknown",
        }

    report_path = pack_root / "security-regression-report.json"

    report_path.write_text(
        json.dumps(regression_data, indent=2),
        encoding="utf-8",
    )

    summary_path = pack_root / "security-trend-summary.txt"

    summary = f"""Security Regression Summary

Overall Trend:
{regression_data.get("overall_trend")}

Introduced Findings:
{len(regression_data.get("introduced", []))}

Resolved Findings:
{len(regression_data.get("resolved", []))}

Persistent Findings:
{len(regression_data.get("persistent", []))}
"""

    summary_path.write_text(
        summary,
        encoding="utf-8",
    )
    
def _render_report(project_name: str, job_id: str, has_verify: bool = False) -> str:
    verify_section = ""
    if has_verify:
        verify_section = """
### Post-Patch Verification Artifacts
This evidence pack contains artifacts from a verification re-scan:
- `raw_verify/semgrep.json` — Post-verify SAST scan results
- `raw_verify/osv.json` — Post-verify Dependency results
- `raw_verify/gitleaks.json` — Post-verify Secret detection results
- `raw_verify/verification-report.json` — Verification outcome, timestamps, and new issues comparison
"""
    return f"""# PatchPilot Evidence Pack

**Project:** {project_name}  
**Job ID:** {job_id}  
**Generated:** {datetime.now(timezone.utc).isoformat()}

## What this pack contains
- `raw/semgrep.json` — Baseline SAST scan results (Semgrep)
- `raw/osv.json` — Baseline Dependency vulnerability results (OSV-Scanner)
- `raw/gitleaks.json` — Baseline Secret detection results (Gitleaks)

- This `REPORT.md` summary
- `security-regression-report.json` — Security regression comparison report
- `security-trend-summary.txt` — Human-readable regression summary
{verify_section}
## Methodology (high-level)
1. Scan codebase for vulnerabilities (SAST, dependency CVEs, secrets).
2. Prioritize findings by severity and likely impact.
3. Apply or suggest minimal remediation steps.
4. Provide verification artifacts and re-scan outputs.

## Notes
- This MVP focuses on **verifiable evidence** and a clean audit trail.
- For production, integrate CI gating (GitHub Actions) and curated fix templates per language/framework.
"""
