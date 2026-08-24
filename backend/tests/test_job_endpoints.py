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


class TestListJobs:
    def test_list_jobs_happy_path(self):
        mock_jobs = [
            {
                "job_id": "job1",
                "project_name": "repo1",
                "scan_method": "zip",
                "status": "completed",
                "finding_count": 5,
                "raw_finding_count": 10,
                "created_at": "2026-07-15 20:00:00",
            },
            {
                "job_id": "job2",
                "project_name": "repo2",
                "scan_method": "url",
                "status": "scanning",
                "finding_count": None,
                "raw_finding_count": None,
                "created_at": "2026-07-15 19:00:00",
            },
        ]

        count_cur = AsyncMock()
        count_cur.fetchone = AsyncMock(return_value={"total": 2})

        jobs_cur = AsyncMock()
        jobs_cur.fetchall = AsyncMock(return_value=mock_jobs)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[count_cur, jobs_cur])
        db.__aenter__ = AsyncMock(return_value=db)
        db.__aexit__ = AsyncMock(return_value=False)

        with patch("app.main.get_db", AsyncMock(return_value=db)):
            res = client.get("/jobs?limit=20&offset=0")

        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        assert len(data["jobs"]) == 2
        assert data["jobs"][0]["job_id"] == "job1"
        assert data["jobs"][1]["job_id"] == "job2"

    def test_list_jobs_invalid_limit_too_low(self):
        res = client.get("/jobs?limit=0")
        assert res.status_code == 422

    def test_list_jobs_invalid_limit_too_high(self):
        res = client.get("/jobs?limit=101")
        assert res.status_code == 422

    def test_list_jobs_invalid_offset(self):
        res = client.get("/jobs?offset=-1")
        assert res.status_code == 422
