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
    "created_at",
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
        "2024-01-01 00:00:00",
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
        "2024-01-01 00:00:01",
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
        "2024-01-01 00:00:02",
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
            for k in ("id", "rule_id", "severity", "category", "scanner", "message")
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


class TestGetFindingsCsv:
    def test_happy_path(self):
        with patch(
            "app.main.get_db", AsyncMock(return_value=db_mock(True, findings=FINDINGS))
        ):
            res = client.get(f"/jobs/{JOB_ID}/findings/csv")
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        assert f'attachment; filename="findings-{JOB_ID}.csv"' in res.headers["content-disposition"]
        
        csv_text = res.text.lstrip('\ufeff')
        lines = csv_text.splitlines()
        assert len(lines) == 4  # header + 3 findings
        
        # Verify headers
        headers = lines[0].split(",")
        expected_headers = ["finding_id", "scanner", "severity", "file_path", "line_number", "title", "description", "status"]
        assert headers == expected_headers
        
        # Verify one of the rows
        row1 = lines[1].split(",")
        assert row1[1] == "semgrep"
        assert row1[2] == "HIGH"
        assert row1[3] == "app/config.py"
        assert row1[4] == "42"
        assert row1[5] == "semgrep.hardcoded-secret"
        assert row1[6] == "Hardcoded secret detected"
        assert row1[7] == "open"

    def test_job_with_no_findings(self):
        with patch(
            "app.main.get_db", AsyncMock(return_value=db_mock(True, findings=[]))
        ):
            res = client.get(f"/jobs/{JOB_ID}/findings/csv")
        assert res.status_code == 200
        csv_text = res.text.lstrip('\ufeff')
        lines = csv_text.splitlines()
        assert len(lines) == 1  # only header row
        headers = lines[0].split(",")
        expected_headers = ["finding_id", "scanner", "severity", "file_path", "line_number", "title", "description", "status"]
        assert headers == expected_headers

    def test_unknown_job(self):
        with patch(
            "app.main.get_db", AsyncMock(return_value=db_mock(False, findings=[]))
        ):
            res = client.get("/jobs/does-not-exist/findings/csv")
        assert res.status_code == 404
        assert "does-not-exist" in res.json()["detail"]

