from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class AsyncContextManagerMock:
    """Mock for an asynchronous context manager."""

    def __init__(self, obj):
        """Initialize the context manager with the target object."""
        self.obj = obj

    async def __aenter__(self):
        """Enter the asynchronous context."""
        return self.obj

    async def __aexit__(self, exc_type, exc, tb):
        """Exit the asynchronous context."""
        pass


class MockStreamResponse:
    """Mock response for httpx stream."""

    def __init__(self, status_code):
        """Initialize the mock stream response."""
        self.status_code = status_code

    async def aiter_bytes(self, chunk_size):
        """Iterate over the mocked byte chunks."""
        yield b""


def test_scan_url_invalid_format():
    # No need to mock validate_git_ref here: repo_url format is
    # validated before the ref is ever checked against the remote, so
    # this never reaches validate_git_ref / the network.
    res = client.post(
        "/scan-url", data={"repo_url": "not-a-url", "project_name": "test_project"}
    )
    assert res.status_code == 400
    assert "Only GitHub repo URLs are supported right now." in res.json()["detail"]


def test_scan_url_invalid_ref_characters():
    res = client.post(
        "/scan-url",
        data={
            "repo_url": "https://github.com/owner/repo",
            "ref": "main; rm -rf /",
            "project_name": "test_project",
        },
    )
    assert res.status_code == 400
    assert "invalid characters" in res.json()["detail"].lower()


@patch("app.main.validate_git_ref")
def test_scan_url_ref_not_found(mock_validate_git_ref):
    mock_validate_git_ref.return_value = False

    res = client.post(
        "/scan-url",
        data={
            "repo_url": "https://github.com/owner/repo",
            "ref": "does-not-exist",
            "project_name": "test_project",
        },
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()
    mock_validate_git_ref.assert_called_once_with(
        "https://github.com/owner/repo", "does-not-exist"
    )


@patch("app.main.validate_git_ref")
@patch("app.main.httpx.AsyncClient")
def test_scan_url_not_found(mock_async_client, mock_validate_git_ref):
    mock_validate_git_ref.return_value = True

    mock_client = MagicMock()
    mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

    not_found = MockStreamResponse(status_code=404)
    mock_client.stream.return_value = AsyncContextManagerMock(not_found)

    res = client.post(
        "/scan-url",
        data={
            "repo_url": "https://github.com/owner/repo",
            "project_name": "test_project",
        },
    )
    assert res.status_code == 400
    assert "Failed to download repo ZIP" in res.json()["detail"]


@patch("app.main.validate_git_ref")
@patch("app.main.httpx.AsyncClient")
def test_scan_url_timeout(mock_async_client, mock_validate_git_ref):
    mock_validate_git_ref.return_value = True

    mock_client = MagicMock()
    mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_client.stream.side_effect = httpx.TimeoutException("timeout")

    res = client.post(
        "/scan-url",
        data={
            "repo_url": "https://github.com/owner/repo",
            "project_name": "test_project",
        },
    )
    assert res.status_code == 400
    assert "Network error downloading repo" in res.json()["detail"]


@patch("app.main.validate_git_ref")
@patch("app.main.httpx.AsyncClient")
@patch("app.main.download_to_path", new_callable=AsyncMock)
@patch("app.main.unzip_to_dir")
@patch("app.main._scan_repo_dir")
@patch("app.main.get_db")
def test_scan_url_success(
    mock_get_db,
    mock_scan,
    mock_unzip,
    mock_download,
    mock_async_client,
    mock_validate_git_ref,
):
    mock_validate_git_ref.return_value = True

    mock_client = MagicMock()
    mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_response = MockStreamResponse(status_code=200)
    mock_client.stream.return_value = AsyncContextManagerMock(mock_response)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.executemany = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_get_db.return_value = mock_db

    mock_scan.return_value = ([], [], [], [], [])

    res = client.post(
        "/scan-url",
        data={
            "repo_url": "https://github.com/owner/repo",
            "project_name": "test_project",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["project_name"] == "test_project"
    assert data["status"] == "running"
    assert "job_id" in data


def test_github_zip_url_supports_tags_and_shas():
    from app.main import github_zip_url

    assert (
        github_zip_url("https://github.com/owner/repo", ref="v1.0.0")
        == "https://github.com/owner/repo/archive/v1.0.0.zip"
    )
    assert (
        github_zip_url("https://github.com/owner/repo", ref="a1b2c3d4")
        == "https://github.com/owner/repo/archive/a1b2c3d4.zip"
    )