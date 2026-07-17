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
    res = client.post(
        "/scan-url", data={"repo_url": "not-a-url", "project_name": "test_project"}
    )
    assert res.status_code == 400
    assert "Only GitHub repo URLs are supported right now." in res.json()["detail"]


@patch("app.main.httpx.AsyncClient")
def test_scan_url_not_found(mock_async_client):
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


@patch("app.main.httpx.AsyncClient")
def test_scan_url_timeout(mock_async_client):
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


@patch("app.main.httpx.AsyncClient")
@patch("app.main.download_to_path", new_callable=AsyncMock)
@patch("app.main.unzip_to_dir")
@patch("app.main._scan_repo_dir")
@patch("app.main.get_db")
def test_scan_url_success(
    mock_get_db, mock_scan, mock_unzip, mock_download, mock_async_client
):
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
