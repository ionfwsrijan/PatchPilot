from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

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

    raw_outputs = {
        "semgrep": semgrep.get("stdout", ""),
        "osv": osv.get("stdout", ""),
        "gitleaks": gitleaks.get("stdout", ""),
    }

    deduped_findings, raw_total, actual_count, source = _load_deduped_findings(
        job_id=job_id, raw_outputs=raw_outputs
    )

    (pack_root / "deduplicated-findings.json").write_text(
        json.dumps(deduped_findings, indent=2), encoding="utf-8"
    )

    report_md = _render_report(
        project_name=project_name,
        job_id=job_id,
        raw_total=raw_total,
        deduped_count=actual_count,
        source=source,
    )
    (pack_root / "REPORT.md").write_text(report_md, encoding="utf-8")

    zip_path = out_dir / f"{pack_root.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in pack_root.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(p.relative_to(pack_root)))

    return zip_path


def _render_report(
    project_name: str,
    job_id: str,
    raw_total: int,
    deduped_count: int,
    source: str,
) -> str:
    return f"""# PatchPilot Evidence Pack

**Project:** {project_name}  
**Job ID:** {job_id}  
**Generated:** {datetime.now(timezone.utc).isoformat()}

## Findings summary
- **Findings after deduplication:** {deduped_count} (from {raw_total} raw)
- **Deduplication source:** {source}
- `deduplicated-findings.json` — normalized findings with `related_files`

## What this pack contains
- `raw/semgrep.json` — SAST scan results (Semgrep)
- `raw/osv.json` — Dependency vulnerability results (OSV-Scanner)
- `raw/gitleaks.json` — Secret detection results (Gitleaks)
- `deduplicated-findings.json` — deduplicated findings grouped for audit
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


def _load_deduped_findings(
    job_id: str, raw_outputs: Dict[str, str]
) -> Tuple[List[Dict[str, Any]], int, int, str]:
    raw_rows = _parse_raw_findings(raw_outputs)
    raw_total = len(raw_rows)

    db_rows = _load_findings_from_db(job_id)
    if db_rows:
        dedup_source = "database"
        rows = db_rows
    else:
        dedup_source = "in-memory raw scan results"
        rows = raw_rows

    deduped_findings = _deduplicate_findings(rows)
    return deduped_findings, raw_total, len(deduped_findings), dedup_source


def _load_findings_from_db(job_id: str) -> List[Dict[str, Any]]:
    db_path = Path(__file__).resolve().parents[1] / "patchpilot.db"
    if not db_path.exists():
        return []

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT id, rule_id, severity, category, file_path, line_number,
                       scanner, message, package_name, package_version
                FROM findings
                WHERE job_id = ?
                ORDER BY created_at
                """,
                (job_id,),
            )
            return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error:
        return []


def _parse_raw_findings(raw_outputs: Dict[str, str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    findings.extend(_parse_semgrep(raw_outputs.get("semgrep", "")))
    findings.extend(_parse_osv(raw_outputs.get("osv", "")))
    findings.extend(_parse_gitleaks(raw_outputs.get("gitleaks", "")))
    return findings


def _parse_semgrep(stdout: str) -> List[Dict[str, Any]]:
    if not stdout:
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    results = data.get("results") if isinstance(data, dict) else data
    if results is None:
        return []

    parsed: List[Dict[str, Any]] = []
    for item in results:
        rule_id = item.get("check_id") or item.get("id") or item.get("rule_id")
        path = item.get("path") or item.get("extra", {}).get("metadata", {}).get("filepath")
        start = item.get("start", {}) or {}
        line_number = start.get("line") or start.get("line_number")
        message = item.get("extra", {}).get("message") or item.get("message") or ""

        parsed.append(
            {
                "id": item.get("id") or f"semgrep:{rule_id}:{path}:{line_number}",
                "rule_id": rule_id,
                "severity": item.get("extra", {}).get("metadata", {}).get("severity", "UNKNOWN"),
                "category": "sast",
                "file_path": path,
                "line_number": line_number,
                "scanner": "semgrep",
                "message": message,
                "package_name": None,
                "package_version": None,
            }
        )
    return parsed


def _parse_osv(stdout: str) -> List[Dict[str, Any]]:
    if not stdout:
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    results = data.get("results") if isinstance(data, dict) else data
    if results is None:
        return []

    parsed: List[Dict[str, Any]] = []
    for item in results:
        package = item.get("package", {}) or {}
        parsed.append(
            {
                "id": item.get("id") or f"osv:{package.get('name')}",
                "rule_id": item.get("id"),
                "severity": item.get("severity", "UNKNOWN"),
                "category": "dependency",
                "file_path": None,
                "line_number": None,
                "scanner": "osv",
                "message": item.get("details") or item.get("summary") or "",
                "package_name": package.get("name"),
                "package_version": package.get("version"),
            }
        )
    return parsed


def _parse_gitleaks(stdout: str) -> List[Dict[str, Any]]:
    if not stdout:
        return []

    try:
        results = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    if not isinstance(results, list):
        return []

    parsed: List[Dict[str, Any]] = []
    for item in results:
        path = item.get("File") or item.get("path") or item.get("Path")
        line_number = item.get("StartLine") or item.get("start_line") or item.get("line")
        parsed.append(
            {
                "id": item.get("Rule") or f"gitleaks:{path}:{line_number}",
                "rule_id": item.get("Rule"),
                "severity": item.get("Severity", "UNKNOWN"),
                "category": "secret",
                "file_path": path,
                "line_number": line_number,
                "scanner": "gitleaks",
                "message": item.get("Description") or item.get("Matches") or "",
                "package_name": None,
                "package_version": None,
            }
        )
    return parsed


def _deduplicate_findings(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, ...], Dict[str, Any]] = {}

    for row in rows:
        key = _dedup_key(row)
        group = groups.setdefault(
            key,
            {
                "id": row.get("id") or "",
                "rule_id": row.get("rule_id"),
                "severity": row.get("severity") or "UNKNOWN",
                "category": row.get("category") or "unknown",
                "scanner": row.get("scanner") or "unknown",
                "title": row.get("rule_id") or row.get("id") or "Unknown",
                "description": row.get("message") or "",
                "location": _location_dict(row),
                "package_name": row.get("package_name"),
                "package_version": row.get("package_version"),
                "related_files": [],
                "row_count": 0,
            },
        )

        file_path = row.get("file_path")
        if file_path and file_path not in group["related_files"]:
            group["related_files"].append(file_path)
        group["row_count"] += 1

        if not group["location"] and row.get("file_path"):
            group["location"] = _location_dict(row)

    deduped: List[Dict[str, Any]] = []
    for group in groups.values():
        group["related_files"] = sorted(group["related_files"])
        deduped.append(group)

    return deduped


def _dedup_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    scanner = (row.get("scanner") or "").lower()
    rule_id = row.get("rule_id") or row.get("id") or ""
    category = (row.get("category") or "").lower()

    if category == "dependency" or scanner == "osv" or row.get("package_name"):
        return (
            "dependency",
            scanner,
            rule_id,
            row.get("package_name"),
            row.get("package_version"),
        )

    return ("issue", scanner, category, rule_id)


def _location_dict(row: Dict[str, Any]) -> Dict[str, Any] | None:
    path = row.get("file_path")
    if not path:
        return None

    location: Dict[str, Any] = {"path": path}
    if row.get("line_number") is not None:
        location["start_line"] = row.get("line_number")
    return location
