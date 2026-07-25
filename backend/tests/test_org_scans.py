import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@patch("app.main.get_db", new_callable=AsyncMock)
@patch("app.main.fetch_org_repos", new_callable=AsyncMock)
@patch("app.main._run_org_batch")
def test_scan_org_valid_url(mock_run_batch, mock_fetch, mock_get_db, client):
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_db
    mock_fetch.return_value = [
        {
            "html_url": "https://github.com/test/repo1",
            "default_branch": "main",
            "name": "repo1",
        }
    ]
    response = client.post(
        "/api/scans/org", json={"org_url": "https://github.com/test"}
    )

    assert response.status_code == 200
    assert response.json()["repo_count"] == 1
    assert "org_job_id" in response.json()


def test_scan_org_invalid_url(client):
    response = client.post(
        "/api/scans/org", json={"org_url": "https://gitlab.com/test"}
    )
    assert response.status_code == 400


@patch("app.main.fetch_org_repos", new_callable=AsyncMock)
def test_scan_org_empty(mock_fetch, client):
    mock_fetch.return_value = []
    response = client.post(
        "/api/scans/org", json={"org_url": "https://github.com/empty"}
    )
    assert response.status_code == 400


@pytest.mark.anyio
@patch("app.main.httpx.AsyncClient.get")
async def test_fetch_org_repos(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"html_url": "url1", "default_branch": "main", "name": "r1", "archived": False},
        {"html_url": "url2", "default_branch": "main", "name": "r2", "archived": True},
    ]
    mock_get.return_value = mock_response

    from app.main import fetch_org_repos

    repos = await fetch_org_repos("test")

    assert len(repos) == 1
    assert repos[0]["name"] == "r1"


@patch("app.main.get_db", new_callable=AsyncMock)
def test_get_org_status_success(mock_get_db, client):
    mock_cursor = AsyncMock()
    mock_cursor.fetchone.return_value = {"status": "scanning"}
    mock_cursor.fetchall.return_value = [
        {"job_id": "1", "project_name": "r1", "status": "completed"}
    ]
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_cursor
    mock_get_db.return_value = mock_db

    response = client.get("/api/scans/org/123/status")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "scanning"
    assert len(data["repos"]) == 1
    assert data["repos"][0]["project_name"] == "r1"


@patch("app.main.get_db", new_callable=AsyncMock)
def test_get_org_status_not_found(mock_get_db, client):
    mock_cursor = AsyncMock()
    mock_cursor.fetchone.return_value = None
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_cursor
    mock_get_db.return_value = mock_db

    response = client.get("/api/scans/org/999/status")
    assert response.status_code == 404


@patch("app.main.get_db", new_callable=AsyncMock)
def test_abort_org_scan(mock_get_db, client):
    mock_db = AsyncMock()
    mock_get_db.return_value = mock_db

    response = client.post("/api/scans/org/123/abort")

    assert response.status_code == 200
    assert response.json() == {
        "status": "aborted",
        "org_job_id": "123",
        "mode": "pending",
    }


@patch("app.main.get_db", new_callable=AsyncMock)
def test_stream_org_status(mock_get_db, client):
    mock_cursor = AsyncMock()
    mock_cursor.fetchone.return_value = {"status": "completed"}
    mock_cursor.fetchall.return_value = [
        {"job_id": "1", "project_name": "r1", "status": "completed"}
    ]

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_cursor
    mock_get_db.return_value = mock_db

    response = client.get("/api/scans/org/123/stream")

    assert response.status_code == 200
    assert "data:" in response.text
    assert "completed" in response.text
    assert "r1" in response.text


@pytest.mark.anyio
async def test_org_repo_scan_keeps_api_responsive_during_blocking_scan(tmp_path):
    from app import main

    def blocking_scan(*args, **kwargs):
        time.sleep(0.3)
        return [], [], [], [], []

    mock_cursor = AsyncMock()
    mock_cursor.fetchone.return_value = {"status": "scanning"}
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_cursor

    transport = httpx.ASGITransport(app=app)

    with (
        patch("app.main.get_db", AsyncMock(return_value=mock_db)),
        patch("app.main.download_to_path", new_callable=AsyncMock),
        patch("app.main.unzip_to_dir"),
        patch("app.main._scan_repo_dir", side_effect=blocking_scan),
        patch("app.main._extract_dependencies", return_value=[]),
        patch("app.main._apply_fp_predictor", new_callable=AsyncMock),
    ):
        scan_task = asyncio.create_task(
            main._run_repo_scan_task(
                asyncio.Semaphore(1),
                "job-1",
                "https://github.com/acme/repo",
                "main",
                "repo",
                "org-1",
            )
        )

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            started_at = time.perf_counter()
            response = await c.get("/health")
            elapsed = time.perf_counter() - started_at

        await scan_task

    assert response.status_code == 200
    assert elapsed < 0.5


@patch("app.main.get_db", new_callable=AsyncMock)
def test_get_org_summary(mock_get_db, client):
    mock_db = AsyncMock()
    mock_get_db.return_value = mock_db
    mock_cursor_1 = AsyncMock()
    mock_cursor_1.fetchone.return_value = {"total": 10, "completed": 8, "failed": 2}

    mock_cursor_2 = AsyncMock()
    mock_cursor_2.fetchall.return_value = [{"severity": "CRITICAL", "count": 5}]

    mock_cursor_3 = AsyncMock()
    mock_cursor_3.fetchall.return_value = [{"repo_name": "frontend-app", "count": 12}]

    mock_db.execute.side_effect = [mock_cursor_1, mock_cursor_2, mock_cursor_3]

    response = client.get("/api/scans/org/123/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total_repositories"] == 10
    assert data["completed_repositories"] == 8
    assert data["severity_distribution"] == {"critical": 5}
    assert data["top_vulnerable_repositories"][0]["repo_name"] == "frontend-app"


@patch("app.main.get_db", new_callable=AsyncMock)
def test_get_org_findings(mock_get_db, client):
    mock_db = AsyncMock()
    mock_get_db.return_value = mock_db
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = [
        {
            "id": "123-abc",
            "repo_name": "backend-api",
            "title": "Hardcoded Secret",
            "description": "Found an AWS key",
            "severity": "CRITICAL",
            "file_path": "config.py",
            "line_number": 42,
            "cwe": "CWE-798",
        }
    ]
    mock_db.execute.return_value = mock_cursor

    response = client.get("/api/scans/org/123/findings")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["repo_name"] == "backend-api"
    assert data[0]["severity"] == "CRITICAL"


@patch("app.main.generate_org_audit_pdf")
@patch("app.main.get_db", new_callable=AsyncMock)
def test_download_org_audit_pdf(mock_get_db, mock_generate_pdf, client):
    mock_db = AsyncMock()
    mock_get_db.return_value = mock_db

    mock_cursor_1 = AsyncMock()
    mock_cursor_1.fetchone.return_value = {"org_name": "AcmeCorp"}
    mock_cursor_2 = AsyncMock()
    mock_cursor_2.fetchone.return_value = {"total": 10, "completed": 8, "failed": 2}
    mock_cursor_3 = AsyncMock()
    mock_cursor_3.fetchall.return_value = [{"severity": "CRITICAL", "count": 5}]
    mock_cursor_4 = AsyncMock()
    mock_cursor_4.fetchall.return_value = [{"repo_name": "api-gateway", "count": 12}]
    mock_cursor_5 = AsyncMock()
    mock_cursor_5.fetchall.return_value = [
        {
            "id": "vuln-1",
            "repo_name": "api-gateway",
            "title": "Hardcoded Credentials",
            "description": "Found DB password",
            "severity": "CRITICAL",
            "file_path": "config.yml",
            "line_number": 15,
            "cwe": "CWE-798",
        }
    ]

    mock_db.execute.side_effect = [
        mock_cursor_1,
        mock_cursor_2,
        mock_cursor_3,
        mock_cursor_4,
        mock_cursor_5,
    ]

    mock_generate_pdf.return_value = b"%PDF-1.4 Mock PDF Content"
    response = client.get("/api/scans/org/123/report/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert "AcmeCorp" in response.headers["content-disposition"]
    assert response.content == b"%PDF-1.4 Mock PDF Content"

    mock_generate_pdf.assert_called_once()
    called_args = mock_generate_pdf.call_args[0]
    assert called_args[0] == "123"
    assert called_args[1] == "AcmeCorp"


def test_extract_dependencies(tmp_path):
    from app.main import _extract_dependencies

    pkg_json = tmp_path / "package.json"
    pkg_json.write_text(
        '{"dependencies": {"react": "^18.0.0"}, "devDependencies": {"vite": "4.0.0"}}',
        encoding="utf-8",
    )

    req_txt = tmp_path / "requirements.txt"
    req_txt.write_text("fastapi==0.95.0\n\npydantic>=1.10", encoding="utf-8")

    deps = _extract_dependencies(tmp_path)

    assert len(deps) == 4
    assert ("react", "^18.0.0") in deps
    assert ("vite", "4.0.0") in deps
    assert ("fastapi", "0.95.0") in deps
    assert ("pydantic", "1.10") in deps


def test_extract_dependencies_pyproject_poetry(tmp_path):
    from app.main import _extract_dependencies

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.poetry.dependencies]\n"
        'python = "^3.10"\n'
        'requests = "^2.28"\n'
        'httpx = {version = "^0.27", extras = ["http2"]}\n'
        'mylib = {git = "https://example.com/mylib.git"}\n',
        encoding="utf-8",
    )

    deps = _extract_dependencies(tmp_path)

    assert ("requests", "^2.28") in deps
    assert ("httpx", "^0.27") in deps
    assert ("mylib", "unknown") in deps
    assert all(name != "python" for name, _ in deps)


def test_extract_dependencies_pyproject_pep621(tmp_path):
    from app.main import _extract_dependencies

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        'name = "demo"\n'
        "dependencies = [\n"
        '    "flask>=3.0",\n'
        '    "click",\n'
        '    "uvicorn[standard]>=0.30",\n'
        "    \"tomli>=2.0; python_version < '3.11'\",\n"
        "]\n",
        encoding="utf-8",
    )

    deps = _extract_dependencies(tmp_path)

    assert ("flask", "3.0") in deps
    assert ("click", "unknown") in deps
    assert ("uvicorn", "0.30") in deps
    assert ("tomli", "2.0") in deps


def test_extract_dependencies_pyproject_dual_section_dedup(tmp_path):
    """Poetry + PEP 621 in one pyproject.toml must not duplicate packages."""
    from app.main import _extract_dependencies

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        'name = "demo"\n'
        'dependencies = ["requests>=2.28", "flask>=3.0"]\n'
        "\n"
        "[tool.poetry.dependencies]\n"
        'python = "^3.10"\n'
        'requests = "^2.28"\n',
        encoding="utf-8",
    )

    deps = _extract_dependencies(tmp_path)

    names = [name for name, _ in deps]
    assert names.count("requests") == 1
    # Poetry section is parsed first, so its version format wins.
    assert ("requests", "^2.28") in deps
    assert ("flask", "3.0") in deps


def test_extract_dependencies_pyproject_malformed(tmp_path):
    """A broken pyproject.toml must not crash extraction of other manifests."""
    from app.main import _extract_dependencies

    (tmp_path / "pyproject.toml").write_text("[not closed", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi==0.95.0", encoding="utf-8")

    deps = _extract_dependencies(tmp_path)

    assert deps == [("fastapi", "0.95.0")]


@pytest.mark.anyio
@patch("app.main.httpx.AsyncClient.get")
async def test_fetch_org_repos_timeout(mock_get):
    """
    Test that an httpx.TimeoutException gracefully degrades into a
    504 Gateway Timeout instead of hanging the worker thread indefinitely.
    """
    import httpx
    from fastapi import HTTPException

    from app.main import fetch_org_repos

    mock_get.side_effect = httpx.TimeoutException("Connection timed out")

    with pytest.raises(HTTPException) as exc_info:
        await fetch_org_repos("test-org")

    assert exc_info.value.status_code == 504
    assert "GitHub API request failed or timed out" in exc_info.value.detail
