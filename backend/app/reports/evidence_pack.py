from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..utils.exec import run_cmd


async def build_evidence_pack(
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

    # ==== Attack Path Files ====
    # Generate attack path data for the job and include in the evidence pack
    from ..attack_paths.engine import generate_attack_paths
    import json
    attack_paths = await generate_attack_paths(job_id)
    # Serialize full paths list
    attack_paths_json = [
        {
            "id": p.id,
            "risk_score": p.risk_score,
            "steps": [step.label for step in p.steps]
        }
        for p in attack_paths
    ]
    (pack_root / "attack-paths.json").write_text(json.dumps(attack_paths_json, indent=2), encoding="utf-8")
    # Graph adjacency list for debugging
    import networkx as nx
    from ..attack_paths.graph_builder import build_graph
    # Re‑build graph to capture adjacency (using same normalized findings)
    from ..db import get_db
    async def _load_findings(job_id: str):
        db = await get_db()
        try:
            cur = await db.execute("""
                SELECT id, rule_id, severity, category, file_path, line_number, message, metadata
                FROM findings
                WHERE job_id = ?
            """, (job_id,))
            rows = await cur.fetchall()
        finally:
            await db.close()
        return rows
    findings_rows = await _load_findings(job_id)
    from ..models import Finding, Location
    raw_findings = []
    for row in findings_rows:
        fid, rule_id, severity, category, file_path, line_number, message, metadata_json = row
        metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else {}
        location = None
        if file_path:
            location = Location(path=file_path, start_line=line_number)
        raw_findings.append(Finding(id=fid, category=category, severity=severity, title=rule_id or "", description=message or "", location=location, metadata=metadata))
    # Normalize and build graph
    from ..attack_paths.models import NormalizedFinding
    normalized = [NormalizedFinding(id=f.id, category=f.category.lower(), severity=f.severity, title=f.title, description=f.description, metadata=f.metadata) for f in raw_findings]
    graph = build_graph(normalized)
    # Convert adjacency to dict
    adjacency = {node: list(graph.successors(node)) for node in graph.nodes}
    (pack_root / "attack-graph-report.json").write_text(json.dumps(adjacency, indent=2), encoding="utf-8")
    # Summary of highest risk path
    if attack_paths:
        top_path = max(attack_paths, key=lambda p: p.risk_score)
        summary_lines = [
            f"Top Attack Path ID: {top_path.id}",
            f"Risk Score: {top_path.risk_score}",
            "Steps:",
        ] + [f" - {step.label}" for step in top_path.steps]
        (pack_root / "attack-path-summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")
    else:
        (pack_root / "attack-path-summary.txt").write_text("No attack paths generated.", encoding="utf-8")

    # Root Cause Analysis
    from ..ml.root_cause.engine import analyze_root_cause
    rca_results = await analyze_root_cause(job_id)
    (pack_root / "rca.json").write_text(json.dumps(rca_results, indent=2), encoding="utf-8")

    report_md = _render_report(project_name=project_name, job_id=job_id)
    (pack_root / "REPORT.md").write_text(report_md, encoding="utf-8")

    zip_path = out_dir / f"{pack_root.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in pack_root.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(p.relative_to(pack_root)))

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
