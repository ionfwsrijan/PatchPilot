
from __future__ import annotations

import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _normalise_finding(finding: Any) -> dict:
    """Convert a finding dictionary or model into JSON-ready data."""
    if isinstance(finding, dict):
        record = dict(finding)
    elif hasattr(finding, "model_dump"):
        record = finding.model_dump(mode="json")
    elif hasattr(finding, "dict"):
        record = finding.dict()
    else:
        record = {"value": str(finding)}

    features = record.get("features") or {}

    if isinstance(features, str):
        try:
            features = json.loads(features)
        except (json.JSONDecodeError, TypeError):
            features = {}

    if not isinstance(features, dict):
        features = {}

    record["related_files"] = record.get("related_files") or features.get(
        "related_files", []
    )
    record["duplicate_count"] = record.get("duplicate_count") or features.get(
        "duplicate_count", 1
    )

    if "location" not in record and (
        record.get("file_path") is not None
        or record.get("line_number") is not None
    ):
        record["location"] = {
            "path": record.get("file_path"),
            "start_line": record.get("line_number"),
        }

    return record


def build_evidence_pack(
    repo_dir: Path,
    out_dir: Path,
    project_name: str,
    job_id: str,
    job_dir: Path | None = None,
    findings: list[Any] | None = None,
    raw_finding_count: int | None = None,
    finding_count: int | None = None,
) -> Path:
    """Build a ZIP containing raw scanner artifacts and deduplicated findings."""
    del repo_dir  # Kept in the signature for compatibility with existing callers.

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pack_root = out_dir / f"patchpilot_evidence_{project_name}_{job_id}_{ts}"
    pack_root.mkdir(parents=True, exist_ok=True)

    raw_dir = job_dir / "raw" if job_dir is not None else out_dir.parent / "raw"

    def _read_raw(name: str) -> str:
        path = raw_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8")

        logger.warning("Raw scan artifact '%s' not found at %s", name, path)
        return ""

    raw_files = {
        "semgrep.json": _read_raw("semgrep.json"),
        "osv.json": _read_raw("osv.json"),
        "gitleaks.json": _read_raw("gitleaks.json"),
    }

    raw_output_dir = pack_root / "raw"
    raw_output_dir.mkdir(parents=True, exist_ok=True)

    for name, content in raw_files.items():
        (raw_output_dir / name).write_text(content, encoding="utf-8")

    has_verify = False
    if job_dir is not None:
        raw_verify_dir = job_dir / "raw_verify"

        if raw_verify_dir.exists():
            has_verify = True
            verify_output_dir = pack_root / "raw_verify"
            verify_output_dir.mkdir(parents=True, exist_ok=True)

            for name in (
                "semgrep.json",
                "osv.json",
                "gitleaks.json",
                "verification-report.json",
            ):
                source = raw_verify_dir / name
                if source.exists():
                    (verify_output_dir / name).write_text(
                        source.read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )

    normalised_findings = [
        _normalise_finding(finding) for finding in (findings or [])
    ]

    findings_path = pack_root / "findings.json"
    findings_path.write_text(
        json.dumps(normalised_findings, indent=2, default=str),
        encoding="utf-8",
    )

    raw_count = (
        raw_finding_count
        if raw_finding_count is not None
        else len(normalised_findings)
    )
    deduplicated_count = (
        finding_count
        if finding_count is not None
        else len(normalised_findings)
    )

    report_md = _render_report(
        project_name=project_name,
        job_id=job_id,
        has_verify=has_verify,
        raw_finding_count=raw_count,
        finding_count=deduplicated_count,
    )
    (pack_root / "REPORT.md").write_text(report_md, encoding="utf-8")

    zip_path = out_dir / f"{pack_root.name}.zip"

    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for path in pack_root.rglob("*"):
            if path.is_file():
                archive.write(path, arcname=str(path.relative_to(pack_root)))

    return zip_path


def _render_report(
    project_name: str,
    job_id: str,
    has_verify: bool = False,
    raw_finding_count: int = 0,
    finding_count: int = 0,
) -> str:
    verify_section = ""

    if has_verify:
        verify_section = """
### Post-Patch Verification Artifacts

- `raw_verify/semgrep.json` — Post-verification SAST results
- `raw_verify/osv.json` — Post-verification dependency results
- `raw_verify/gitleaks.json` — Post-verification secret detection results
- `raw_verify/verification-report.json` — Verification outcome and comparison
"""

    return f"""# PatchPilot Evidence Pack

**Project:** {project_name}
**Job ID:** {job_id}
**Generated:** {datetime.now(timezone.utc).isoformat()}

## Finding Summary

- Findings after deduplication: {finding_count} (from {raw_finding_count} raw)
- Exported deduplicated findings: `findings.json`

## What this pack contains

- `raw/semgrep.json` — Baseline SAST scan results
- `raw/osv.json` — Baseline dependency vulnerability results
- `raw/gitleaks.json` — Baseline secret detection results
- `findings.json` — Deduplicated findings with related-file metadata
- `REPORT.md` — This summary report
{verify_section}
## Methodology

1. Scan the codebase for vulnerabilities, dependency issues, and secrets.
2. Deduplicate similar findings when deduplication is available.
3. Preserve finding details and related-file metadata in the export.
4. Include raw scanner artifacts for audit and verification.

## Notes

- Raw scanner outputs are included for traceability.
- The counts above reflect the values supplied by the scan job.
"""
