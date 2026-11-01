import os
import tempfile
import uuid

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from app import db as app_db
from app.main import app as fastapi_app
from app.models import Finding, FindingStatusUpdate

client = TestClient(fastapi_app)


# =====================================================================
# 1. Pydantic Model Unit Tests
# =====================================================================


class TestFindingModelStatus:
    def test_default_status_is_open(self):
        f = Finding(
            id="f-1",
            category="sast",
            severity="HIGH",
            title="SQL Injection",
        )
        assert f.status == "open"

    def test_explicit_accepted_status(self):
        f = Finding(
            id="f-2",
            category="sast",
            severity="HIGH",
            title="SQL Injection",
            status="accepted",
        )
        assert f.status == "accepted"

    def test_explicit_ignored_status(self):
        f = Finding(
            id="f-3",
            category="sast",
            severity="LOW",
            title="Info Leak",
            status="ignored",
        )
        assert f.status == "ignored"

    def test_finding_status_update_schema(self):
        payload = FindingStatusUpdate(status="accepted")
        assert payload.status == "accepted"


# =====================================================================
# 2. Endpoint Unit & Error Handling Tests
# =====================================================================


class TestFindingStatusEndpoints:
    def test_patch_status_invalid_value_returns_400(self):
        res = client.patch(
            "/findings/test-finding-1/status", json={"status": "resolved"}
        )
        assert res.status_code == 400
        assert "Invalid status value" in res.json()["detail"]

    def test_patch_status_missing_field_returns_422(self):
        res = client.patch("/findings/test-finding-1/status", json={})
        assert res.status_code == 422

    def test_patch_status_not_found_returns_404(self, monkeypatch):
        async def _mock_get_finding(db, finding_id):
            return None

        import app.main

        monkeypatch.setattr(app.main, "get_finding", _mock_get_finding)
        monkeypatch.setattr(app_db, "get_finding", _mock_get_finding)
        res = client.patch(
            "/findings/nonexistent-id/status", json={"status": "accepted"}
        )
        assert res.status_code == 404
        assert "not found" in res.json()["detail"]


# =====================================================================
# 3. Full Integration & Persistence Across Re-fetch Tests
# =====================================================================


class TestFindingStatusPersistence:
    @pytest.mark.anyio
    async def test_status_update_and_persistence_across_get(self, monkeypatch):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            monkeypatch.setattr(app_db, "DB_PATH", tmp_path)
            await app_db.init_db()

            job_id = f"job-{uuid.uuid4().hex[:8]}"
            f1_id = f"finding-{uuid.uuid4().hex[:8]}"
            f2_id = f"finding-{uuid.uuid4().hex[:8]}"
            f3_id = f"finding-{uuid.uuid4().hex[:8]}"

            async with aiosqlite.connect(tmp_path) as db:
                await db.execute(
                    "INSERT INTO jobs (job_id, project_name, scan_method) VALUES (?, ?, ?)",
                    (job_id, "test-project", "zip"),
                )
                findings_to_insert = [
                    (
                        f1_id,
                        job_id,
                        "rule-1",
                        "Vulnerability 1",
                        "HIGH",
                        "sast",
                        "a.py",
                        10,
                        "CWE-89",
                        "semgrep",
                        "msg 1",
                        None,
                        None,
                        0.9,
                        None,
                        8.5,
                    ),
                    (
                        f2_id,
                        job_id,
                        "rule-2",
                        "Vulnerability 2",
                        "MEDIUM",
                        "sast",
                        "b.py",
                        20,
                        "CWE-79",
                        "semgrep",
                        "msg 2",
                        None,
                        None,
                        0.7,
                        None,
                        6.0,
                    ),
                    (
                        f3_id,
                        job_id,
                        "rule-3",
                        "Vulnerability 3",
                        "LOW",
                        "sast",
                        "c.py",
                        30,
                        "CWE-200",
                        "semgrep",
                        "msg 3",
                        None,
                        None,
                        0.3,
                        None,
                        3.0,
                    ),
                ]
                await app_db.create_findings(db, findings_to_insert)

            # 1. Initial GET /jobs/{job_id}/findings should show all as "open"
            res = client.get(f"/jobs/{job_id}/findings")
            assert res.status_code == 200
            data = res.json()
            findings = {f["id"]: f for f in data["findings"]}
            assert findings[f1_id]["status"] == "open"
            assert findings[f2_id]["status"] == "open"
            assert findings[f3_id]["status"] == "open"

            # 2. Update f1 to "accepted"
            patch_res1 = client.patch(
                f"/findings/{f1_id}/status", json={"status": "accepted"}
            )
            assert patch_res1.status_code == 200
            assert patch_res1.json() == {"id": f1_id, "status": "accepted"}

            # 3. Update f2 to "ignored"
            patch_res2 = client.patch(
                f"/findings/{f2_id}/status", json={"status": "ignored"}
            )
            assert patch_res2.status_code == 200
            assert patch_res2.json() == {"id": f2_id, "status": "ignored"}

            # 4. Simulate page reload: re-fetch GET /jobs/{job_id}/findings
            reload_res = client.get(f"/jobs/{job_id}/findings")
            assert reload_res.status_code == 200
            reloaded_findings = {f["id"]: f for f in reload_res.json()["findings"]}

            # Assert status survived and is persistent
            assert reloaded_findings[f1_id]["status"] == "accepted"
            assert reloaded_findings[f2_id]["status"] == "ignored"
            assert reloaded_findings[f3_id]["status"] == "open"

            # 5. Revert f1 back to "open"
            revert_res = client.patch(
                f"/findings/{f1_id}/status", json={"status": "open"}
            )
            assert revert_res.status_code == 200
            assert revert_res.json() == {"id": f1_id, "status": "open"}

            final_res = client.get(f"/jobs/{job_id}/findings")
            final_findings = {f["id"]: f for f in final_res.json()["findings"]}
            assert final_findings[f1_id]["status"] == "open"

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
