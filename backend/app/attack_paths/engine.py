from __future__ import annotations

import uuid
from typing import List
from pydantic import BaseModel

from ..models import Finding
from .models import NormalizedFinding, AttackPath, AttackStep
from .graph_builder import build_graph, extract_paths
from .scorer import calculate_risk
from ..utils.fs import ensure_dir
from ..db import get_db
import json

async def generate_attack_paths(job_id: str) -> List[AttackPath]:
    """Generate attack paths for a given scan job.

    Steps:
    1. Load raw findings from the database.
    2. Normalize them to a common schema.
    3. Build a directed graph linking related findings.
    4. Extract all possible paths.
    5. Score each path.
    """
    # --- 1. Load findings ---
    db = await get_db()
    try:
        cur = await db.execute(
            """
            SELECT id, rule_id, severity, category, file_path, line_number, message, metadata
            FROM findings
            WHERE job_id = ?
            """,
            (job_id,)
        )
        rows = await cur.fetchall()
    finally:
        await db.close()

    raw_findings: List[Finding] = []
    for row in rows:
        fid, rule_id, severity, category, file_path, line_number, message, metadata_json = row
        metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else {}
        location = None
        if file_path:
            from ..models import Location
            location = Location(path=file_path, start_line=line_number)
        finding = Finding(
            id=fid,
            category=category,
            severity=severity,
            title=rule_id or "",
            description=message or "",
            location=location,
            metadata=metadata,
        )
        raw_findings.append(finding)

    # --- 2. Normalize ---
    normalized: List[NormalizedFinding] = []
    for f in raw_findings:
        norm = NormalizedFinding(
            id=f.id,
            category=f.category.lower(),
            severity=f.severity,
            title=f.title,
            description=f.description,
            metadata=f.metadata,
        )
        normalized.append(norm)

    # --- 3. Build graph ---
    graph = build_graph(normalized)
    # --- 4. Extract paths ---
    paths = extract_paths(graph)

    # --- 5. Score paths ---
    scored_paths: List[AttackPath] = []
    for p in paths:
        risk = calculate_risk(p)
        scored = AttackPath(id=str(uuid.uuid4()), steps=p.steps, risk_score=risk)
        scored_paths.append(scored)

    return scored_paths
