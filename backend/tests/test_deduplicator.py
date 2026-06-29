import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml import deduplicator
from app.models import Finding


# Helper to create dummy Finding object
def make_finding(id_, title, desc):
    return Finding(
        id=id_,
        category="sast",
        severity="HIGH",
        title=title,
        description=desc,
        location=None,
    )


def test_deduplicate_not_installed():
    """Verify that when sentence-transformers is not installed, deduplicate returns original list."""
    with patch("app.ml.deduplicator.SENTENCE_TRANSFORMERS_AVAILABLE", False):
        findings = [make_finding("1", "XSS", "Same"), make_finding("2", "XSS", "Same")]
        res = deduplicator.deduplicate(findings)
        assert len(res) == 2
        assert res == findings


def test_deduplicate_with_mocked_transformer():
    """Verify that deduplicate correctly clusters similar findings when sentence-transformers is available."""
    with patch("app.ml.deduplicator.SENTENCE_TRANSFORMERS_AVAILABLE", True):
        mock_model = MagicMock()

        findings = [
            make_finding("1", "XSS", "Reflected cross site scripting in index.html"),
            make_finding(
                "2", "XSS Duplicate", "Reflected cross site scripting in index.html"
            ),
            make_finding("3", "SQLi", "SQL injection in query parameter"),
        ]

        # Embeddings for duplicate (similar) and orthogonal finding
        import numpy as np

        embeddings = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        mock_model.encode.return_value = embeddings

        with patch("app.ml.deduplicator.get_model", return_value=mock_model):
            res = deduplicator.deduplicate(findings, epsilon=0.15)

            assert len(res) == 2
            assert res[0].id == "1"
            assert res[1].id == "3"


def test_findings_response_shape():
    """Verify the /jobs/{job_id}/findings response shape contains both finding count fields."""
    client = TestClient(app)

    # job row has: job_id, raw_finding_count, finding_count
    job_row = ("testjob999", 5, 2)
    finding_rows = [
        (
            "f1",
            "rule1",
            "HIGH",
            "sast",
            "path1",
            10,
            "CWE-79",
            "semgrep",
            "msg1",
            None,
            None,
            "2024-01-01",
        ),
        (
            "f2",
            "rule2",
            "LOW",
            "sast",
            "path2",
            20,
            "CWE-89",
            "semgrep",
            "msg2",
            None,
            None,
            "2024-01-01",
        ),
    ]

    from tests.test_job_endpoints import cursor

    job_cur = cursor(("job_id", "raw_finding_count", "finding_count"), one=job_row)
    data_cur = cursor(
        (
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
        ),
        all=finding_rows,
    )

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[job_cur, data_cur])
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)

    with patch("app.main.get_db", AsyncMock(return_value=db)):
        res = client.get("/jobs/testjob999/findings")

    assert res.status_code == 200
    data = res.json()
    assert data["job_id"] == "testjob999"
    assert data["raw_finding_count"] == 5
    assert data["finding_count"] == 2
    assert len(data["findings"]) == 2


def test_findings_response_shape_defaults():
    """Verify the /jobs/{job_id}/findings response defaults correctly when counts are NULL."""
    client = TestClient(app)

    job_row = ("testjob888", None, None)
    finding_rows = [
        (
            "f1",
            "rule1",
            "HIGH",
            "sast",
            "path1",
            10,
            "CWE-79",
            "semgrep",
            "msg1",
            None,
            None,
            "2024-01-01",
        )
    ]

    from tests.test_job_endpoints import cursor

    job_cur = cursor(("job_id", "raw_finding_count", "finding_count"), one=job_row)
    data_cur = cursor(
        (
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
        ),
        all=finding_rows,
    )

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[job_cur, data_cur])
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)

    with patch("app.main.get_db", AsyncMock(return_value=db)):
        res = client.get("/jobs/testjob888/findings")

    assert res.status_code == 200
    data = res.json()
    assert data["job_id"] == "testjob888"
    assert data["raw_finding_count"] == 1
    assert data["finding_count"] == 1
    assert len(data["findings"]) == 1


@pytest.mark.anyio
async def test_run_single_scan_task_disable_dedup():
    """Verify DISABLE_DEDUP=true bypasses deduplication in single scan task."""
    from app.main import _run_single_scan_task

    findings = [make_finding("1", "XSS", "Same"), make_finding("2", "XSS", "Same")]

    mock_run_in_threadpool = AsyncMock(return_value=([], [], [], [], findings))

    db = AsyncMock()
    db.execute = AsyncMock()
    db.executemany = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.main.run_in_threadpool", mock_run_in_threadpool),
        patch("app.main.predictor.is_ready", False),
        patch("app.main.get_db", AsyncMock(return_value=db)),
        patch.dict(os.environ, {"DISABLE_DEDUP": "true"}),
        patch("app.main.SENTENCE_TRANSFORMERS_AVAILABLE", True),
        patch("app.ml.deduplicator.SENTENCE_TRANSFORMERS_AVAILABLE", True),
    ):
        from pathlib import Path

        await _run_single_scan_task("job123", "proj", "zip", Path("/tmp/dummy"))

        update_call = None
        for call in db.execute.call_args_list:
            args = call[0]
            if "UPDATE jobs SET status = 'completed'" in args[0]:
                update_call = args
                break

        assert update_call is not None
        assert update_call[1] == (2, 2, "job123")


@pytest.mark.anyio
async def test_run_single_scan_task_dedup_epsilon():
    """Verify deduplication uses DEDUP_EPSILON env var correctly."""
    from app.main import _run_single_scan_task

    findings = [make_finding("1", "XSS", "Same"), make_finding("2", "XSS", "Same")]

    mock_model = MagicMock()
    import numpy as np

    mock_model.encode.return_value = np.array([[1.0, 0.0], [1.0, 0.0]])

    mock_run_in_threadpool = AsyncMock(return_value=([], [], [], [], findings))

    db = AsyncMock()
    db.execute = AsyncMock()
    db.executemany = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.main.run_in_threadpool", mock_run_in_threadpool),
        patch("app.main.predictor.is_ready", False),
        patch("app.main.get_db", AsyncMock(return_value=db)),
        patch.dict(os.environ, {"DISABLE_DEDUP": "false", "DEDUP_EPSILON": "0.15"}),
        patch("app.main.SENTENCE_TRANSFORMERS_AVAILABLE", True),
        patch("app.ml.deduplicator.SENTENCE_TRANSFORMERS_AVAILABLE", True),
        patch("app.ml.deduplicator.get_model", return_value=mock_model),
    ):
        from pathlib import Path

        await _run_single_scan_task("job456", "proj", "zip", Path("/tmp/dummy"))

        update_call = None
        for call in db.execute.call_args_list:
            args = call[0]
            if "UPDATE jobs SET status = 'completed'" in args[0]:
                update_call = args
                break

        assert update_call is not None
        assert update_call[1] == (2, 1, "job456")
