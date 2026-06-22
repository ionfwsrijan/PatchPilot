from __future__ import annotations

import json
from typing import List

from ..db import get_db
from .models import RootCauseFinding, RootCauseGroup, RootCauseResponse
from .clustering import cluster_findings


async def analyze_root_cause(job_id: str) -> dict:
    """Analyze findings for a job and return root‑cause groups.

    Returns a dictionary with ``job_id`` and a list of group dictionaries
    compatible with :class:`RootCauseResponse`.
    """
    # Load findings from the database
    db = await get_db()
    try:
        cur = await db.execute(
            """
                SELECT id, rule_id, severity, category, file_path, line_number, message, metadata
                FROM findings
                WHERE job_id = ?
            """,
            (job_id,),
        )
        rows = await cur.fetchall()
    finally:
        await db.close()

    # Convert rows to RootCauseFinding objects
    findings: List[RootCauseFinding] = []
    for row in rows:
        fid, rule_id, severity, category, file_path, line_number, message, metadata_json = row
        metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else {}
        location = None
        if file_path:
            from ..models import Location
            location = Location(path=file_path, start_line=line_number)
        findings.append(
            RootCauseFinding(
                id=fid,
                title=rule_id or "",
                description=message or "",
                metadata=metadata,
            )
        )

    # Perform clustering
    groups: List[RootCauseGroup] = cluster_findings(findings)

    # Serialize groups for JSON output
    return {"job_id": job_id, "groups": [g.dict() for g in groups]}
