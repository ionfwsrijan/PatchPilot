import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

JOB_ID = "testjob123"

# column order matches the SELECT in each endpoint
FINDINGS_COLS = (
    "id",
    "rule_id",
    "severity",
    "category",
    "file_path",
    "line_number",
    "cwe",
    "scanner",
    "message",
    "package_name",
    "package_version",
    "created_at",
    "ml_score",
)
VERIFY_COLS = ("id", "job_id", "passed", "new_issues_introduced", "verified_at")

FINDINGS = [
    (
        str(uuid.uuid4()),
        "semgrep.hardcoded-secret",
        "HIGH",
        "sast",
        "app/config.py",
        42,
        None,
        "semgrep",
        "Hardcoded secret detected",
        None,
        None,
        "2024-01-01 00:00:00",
        0.85,
    ),
    (
        str(uuid.uuid4()),
        "CVE-2023-1234",
        "CRITICAL",
        "dependency",
        None,
        None,
        None,
        "osv",
        "Vulnerable dependency",
        None,
        None,
        "2024-01-01 00:00:01",
        None,
    ),
    (
        str(uuid.uuid4()),
        "generic-api-key",
        "HIGH",
        "secret",
        ".env",
        3,
        None,
        "gitleaks",
        "API key exposed",
        None,
        None,
        "2024-01-01 00:00:02",
        0.95,
    ),
]

VERIFY_ROW = (str(uuid.uuid4()), JOB_ID, 1, 0, "2024-01-01 01:00:00")


def cursor(cols, one=None, all=None):
    cur = AsyncMock()
    cur.description = [(c,) for c in cols]
    cur.fetchone = AsyncMock(return_value=one)
    cur.fetchall = AsyncMock(return_value=all or [])
    return cur


def db_mock(job_exists, findings=None, verify_row=None):
    job_cur = cursor(("job_id",), one=(JOB_ID,) if job_exists else None)
    data_cur = (
        cursor(FINDINGS_COLS, all=findings)
        if findings is not None
        else cursor(VERIFY_COLS, one=verify_row)
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[job_cur, data_cur])
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    return db


# /findings


class TestGetFindings:
    def test_happy_path(self):
        with patch(
            "app.main.get_db", AsyncMock(return_value=db_mock(True, findings=FINDINGS))
        ):
            res = client.get(f"/jobs/{JOB_ID}/findings")
        assert res.status_code == 200
        body = res.json()
        assert body["job_id"] == JOB_ID
        assert body["finding_count"] == 3
        assert len(body["findings"]) == 3

    def test_all_scanners_present(self):
        with patch(
            "app.main.get_db", AsyncMock(return_value=db_mock(True, findings=FINDINGS))
        ):
            res = client.get(f"/jobs/{JOB_ID}/findings")
        assert {f["scanner"] for f in res.json()["findings"]} == {
            "semgrep",
            "osv",
            "gitleaks",
        }

    def test_unknown_job(self):
        with patch(
            "app.main.get_db", AsyncMock(return_value=db_mock(False, findings=[]))
        ):
            res = client.get("/jobs/does-not-exist/findings")
        assert res.status_code == 404
        assert "does-not-exist" in res.json()["detail"]

    def test_job_with_no_findings(self):
        with patch(
            "app.main.get_db", AsyncMock(return_value=db_mock(True, findings=[]))
        ):
            res = client.get(f"/jobs/{JOB_ID}/findings")
        assert res.status_code == 200
        assert res.json()["finding_count"] == 0
        assert res.json()["findings"] == []

    def test_finding_fields(self):
        with patch(
            "app.main.get_db",
            AsyncMock(return_value=db_mock(True, findings=FINDINGS[:1])),
        ):
            res = client.get(f"/jobs/{JOB_ID}/findings")
        f = res.json()["findings"][0]
        assert all(
            k in f
            for k in (
                "id",
                "rule_id",
                "severity",
                "category",
                "scanner",
                "message",
                "ml_score",
            )
        )


# /verify


class TestGetVerify:
    def test_happy_path(self):
        with patch(
            "app.main.get_db",
            AsyncMock(return_value=db_mock(True, verify_row=VERIFY_ROW)),
        ):
            res = client.get(f"/jobs/{JOB_ID}/verify")
        assert res.status_code == 200
        body = res.json()
        assert body["job_id"] == JOB_ID
        assert body["passed"] == 1
        assert "verified_at" in body

    def test_unknown_job(self):
        with patch("app.main.get_db", AsyncMock(return_value=db_mock(False))):
            res = client.get("/jobs/does-not-exist/verify")
        assert res.status_code == 404
        assert "does-not-exist" in res.json()["detail"]

    def test_verify_not_run_yet(self):
        with patch("app.main.get_db", AsyncMock(return_value=db_mock(True))):
            res = client.get(f"/jobs/{JOB_ID}/verify")
        assert res.status_code == 404
        assert "No verify outcome" in res.json()["detail"]


class TestStreamSingleScan:
    def test_stream_job_not_found(self):
        with client.stream("GET", "/api/scans/invalid_job/stream") as response:
            assert response.status_code == 200
            content = next(response.iter_lines())
            assert "error" in content
            assert "Job not found" in content

    def test_stream_job_completed(self):
        from app.main import ACTIVE_SCANS

        ACTIVE_SCANS[JOB_ID] = {
            "status": "completed",
            "sast": "completed",
            "dependency": "completed",
            "secrets": "completed",
            "findings_count": 5,
        }
        with client.stream("GET", f"/api/scans/{JOB_ID}/stream") as response:
            assert response.status_code == 200
            content = next(response.iter_lines())
            assert '"status": "completed"' in content
            assert '"findings_count": 5' in content

        if JOB_ID in ACTIVE_SCANS:
            del ACTIVE_SCANS[JOB_ID]


class TestDeleteJob:
    @patch("app.main.get_job", new_callable=AsyncMock)
    @patch("app.main.safe_job_dir")
    @patch("app.main.safe_rmtree")
    def test_delete_success(self, mock_rmtree, mock_safe_job_dir, mock_get_job):
        mock_get_job.return_value = {"job_id": JOB_ID}
        from unittest.mock import MagicMock

        mock_job_dir = MagicMock()
        mock_job_dir.exists.return_value = True
        mock_safe_job_dir.return_value = mock_job_dir

        db = db_mock(True)
        # Mock successful execution
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        with patch("app.main.get_db", AsyncMock(return_value=db)):
            res = client.delete(f"/jobs/{JOB_ID}")

        assert res.status_code == 200
        assert res.json() == {"deleted": True}

        # Verify db logic called
        assert db.execute.call_count == 3  # DELETE x3
        assert db.commit.called
        assert not db.rollback.called

        # Verify rmtree called because job_dir exists and db commit didn't fail
        mock_rmtree.assert_called_once_with(mock_job_dir)

    @patch("app.main.get_job", new_callable=AsyncMock)
    @patch("app.main.safe_job_dir")
    @patch("app.main.safe_rmtree")
    def test_delete_missing_directory(
        self, mock_rmtree, mock_safe_job_dir, mock_get_job
    ):
        mock_get_job.return_value = {"job_id": JOB_ID}
        from unittest.mock import MagicMock

        mock_job_dir = MagicMock()
        mock_job_dir.exists.return_value = False
        mock_safe_job_dir.return_value = mock_job_dir

        db = db_mock(True)
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        with patch("app.main.get_db", AsyncMock(return_value=db)):
            res = client.delete(f"/jobs/{JOB_ID}")

        assert res.status_code == 200
        assert res.json() == {"deleted": True}

        # Verify db was cleaned
        assert db.commit.called

        # Verify rmtree NOT called
        mock_rmtree.assert_not_called()

    @patch("app.main.get_job", new_callable=AsyncMock)
    @patch("app.main.safe_job_dir")
    @patch("app.main.safe_rmtree")
    def test_delete_db_failure(self, mock_rmtree, mock_safe_job_dir, mock_get_job):
        mock_get_job.return_value = {"job_id": JOB_ID}
        from unittest.mock import MagicMock

        mock_job_dir = MagicMock()
        mock_job_dir.exists.return_value = True
        mock_safe_job_dir.return_value = mock_job_dir

        db = db_mock(True)
        db.execute = AsyncMock(side_effect=Exception("DB Error"))
        db.rollback = AsyncMock()

        with patch("app.main.get_db", AsyncMock(return_value=db)):
            res = client.delete(f"/jobs/{JOB_ID}")

        assert res.status_code == 500
        assert "Database error" in res.json()["detail"]

        # Verify rollback called
        assert db.rollback.called

        # Verify rmtree NOT called since db failed
        mock_rmtree.assert_not_called()

    @patch("app.main.get_job", new_callable=AsyncMock)
    @patch("app.main.safe_job_dir")
    @patch("app.main.safe_rmtree")
    def test_delete_missing_job_returns_404(
        self, mock_rmtree, mock_safe_job_dir, mock_get_job
    ):
        mock_get_job.return_value = None  # Job not found in DB

        db = db_mock(True)
        db.execute = AsyncMock()

        with patch("app.main.get_db", AsyncMock(return_value=db)):
            res = client.delete(f"/jobs/{JOB_ID}")

        assert res.status_code == 404
        assert "No job found" in res.json()["detail"]

        # Verify delete_job was not called (execute not called for DELETE)
        assert db.execute.call_count == 0

        # Verify rmtree NOT called
        mock_rmtree.assert_not_called()
