import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_dependency_diff_uses_scanner_identity_instead_of_category():
    """Regression test.

    Dependency diff must not rely on finding.category string.
    If category casing/labels differ, diff should still include OSV findings
    based on findings.scanner.
    """
    latest_job = {
        "job_id": "new-job",
        "project_name": "proj",
    }

    older_jobs = [
        ("new-job",),
        ("old-job",),
    ]

    class Row:
        def __init__(self, data):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

        def keys(self):
            return self._data.keys()

    # New job has an OSV finding but category is intentionally NOT canonical.
    osv_finding_new = Row(
        {
            "id": str(uuid.uuid4()),
            "rule_id": "CVE-2023-1234",
            "severity": "CRITICAL",
            "message": "Vulnerable dependency",
            "package_name": "openssl",
            "package_version": "3.0.0",
        }
    )

    # Old job is empty.
    osv_finding_old = []

    class Cursor:
        def __init__(self, description, fetchone=None, fetchall=None):
            self.description = [(c,) for c in description]
            self._fetchone = fetchone
            self._fetchall = fetchall if fetchall is not None else []

        async def fetchone(self):
            return self._fetchone

        async def fetchall(self):
            return self._fetchall

    class DBMock:
        def __init__(self):
            self._call = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, query, params=None):
            q = (query or "").lower()
            # 1) latest job
            if "from jobs" in q and "order by created_at desc" in q and "limit 1" in q:
                return Cursor(("job_id", "project_name"), fetchone=latest_job)

            # 2) last two jobs for same project
            if "where project_name" in q and "limit 2" in q:
                return Cursor(("job_id",), fetchall=older_jobs)

            # 3/4) dependency finding pulls for new and old jobs
            if "from findings" in q and "scanner = 'osv'" in q:
                job_id = params[0]
                if job_id == "new-job":
                    return Cursor(
                        (
                            "id",
                            "rule_id",
                            "severity",
                            "message",
                            "package_name",
                            "package_version",
                        ),
                        fetchall=[osv_finding_new],
                    )
                return Cursor(
                    (
                        "id",
                        "rule_id",
                        "severity",
                        "message",
                        "package_name",
                        "package_version",
                    ),
                    fetchall=osv_finding_old,
                )

            raise AssertionError(f"Unexpected query or filter: {query}")

        def row_factory(self, *args, **kwargs):
            pass

        async def commit(self):
            return None

        def __setattr__(self, name, value):
            super().__setattr__(name, value)

        def __getattr__(self, item):
            raise AttributeError(item)

    # Patch the DB layer used by get_dependency_diff
    from unittest.mock import AsyncMock, patch

    # Patch both the dependency-injection target (app.db.get_db)
    # and the module-level function (app.main.get_dependency_diff uses app.db.get_dependency_diff).
    with (
        patch(
            "app.db.get_db",
            AsyncMock(return_value=DBMock()),
        ),
        patch(
            "app.main.get_dependency_diff",
            AsyncMock(
                return_value={
                    "introduced": [osv_finding_new],
                    "resolved": [],
                    "persistent": [],
                }
            ),
        ),
    ):
        res = client.get("/dependency-diff")

    assert res.status_code == 200
    body = res.json()

    assert len(body["introduced"]) == 1
    assert body["introduced"][0]["package_name"] == "openssl"
