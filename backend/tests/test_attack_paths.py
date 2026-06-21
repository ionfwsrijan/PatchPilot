import asyncio
import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.attack_paths.engine import generate_attack_paths
from backend.app.attack_paths.models import NormalizedFinding
from backend.app.attack_paths.graph_builder import build_graph, extract_paths

# Helper to create in-memory findings
@pytest.fixture
def sample_findings():
    return [
        NormalizedFinding(
            id="f1",
            category="secret",
            severity="high",
            title="Hardcoded AWS key",
            description="AWS access key in code",
            metadata={"tool": "gitleaks"},
        ),
        NormalizedFinding(
            id="f2",
            category="cloud-access",
            severity="medium",
            title="AWS IAM role",
            description="IAM role allowing S3 access",
            metadata={"tool": "none"},
        ),
        NormalizedFinding(
            id="f3",
            category="vulnerability",
            severity="critical",
            title="Log4j RCE",
            description="CVE-2021-44228",
            metadata={"tool": "osv"},
        ),
    ]

def test_build_graph(sample_findings):
    graph = build_graph(sample_findings)
    # Expect edges according to correlation map (secret->cloud-access, vulnerability->rce)
    assert graph.has_edge("f1", "f2")
    # Vulnerability should link to a synthetic "Remote Code Execution" node (generated inside builder)
    # Find node with label "Remote Code Execution"
    rce_nodes = [n for n, data in graph.nodes(data=True) if data.get("label") == "Remote Code Execution"]
    assert len(rce_nodes) == 1
    assert graph.has_edge("f3", rce_nodes[0])

def test_extract_paths(sample_findings):
    graph = build_graph(sample_findings)
    paths = extract_paths(graph)
    # Should have at least one path containing secret->cloud-access
    found = any([p.steps[0].label == "Hardcoded AWS key" and p.steps[1].label == "AWS IAM role" for p in paths])
    assert found

@pytest.mark.asyncio
async def test_api_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Assume there is a job_id with no findings, should return 404
        response = await ac.get("/attack-paths/nonexistent")
        assert response.status_code == 404
        # Create a temporary job with findings using the DB directly
        from backend.app.db import get_db
        db = await get_db()
        await db.execute(
            "INSERT INTO scans (job_id, repo, commit, status) VALUES (?, ?, ?, ?)",
            ("testjob", "repo", "abc123", "finished"),
        )
        # Insert mock findings
        for f in [
            ("f1", "testjob", "gitleaks", "high", "secret", "file1", 1, "msg1", json.dumps({"tool": "gitleaks"})),
            ("f2", "testjob", "gitleaks", "medium", "cloud-access", "file2", 2, "msg2", json.dumps({})),
            ("f3", "testjob", "osv", "critical", "vulnerability", "file3", 3, "msg3", json.dumps({"tool": "osv"})),
        ]:
            await db.execute(
                "INSERT INTO findings (id, job_id, rule_id, severity, category, file_path, line_number, message, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                f,
            )
        await db.commit()
        await db.close()

        resp = await ac.get("/attack-paths/testjob")
        assert resp.status_code == 200
        data = resp.json()
        assert "all_paths" in data
        assert isinstance(data["all_paths"], list)
        # Clean up
        db = await get_db()
        await db.execute("DELETE FROM findings WHERE job_id = ?", ("testjob",))
        await db.execute("DELETE FROM scans WHERE job_id = ?", ("testjob",))
        await db.commit()
        await db.close()
