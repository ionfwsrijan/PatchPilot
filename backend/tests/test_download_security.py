from unittest.mock import MagicMock, patch

import anyio
import pytest
from fastapi import HTTPException

import app.main


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

    def __init__(self, status_code, chunks=None):
        """Initialize the mock stream response."""
        self.status_code = status_code
        self.chunks = chunks or []

    async def aiter_bytes(self, chunk_size):
        """Iterate over the mocked byte chunks."""
        for chunk in self.chunks:
            yield chunk


@patch("app.main.MAX_UPLOAD_SIZE", 1024)
@patch("app.main.MAX_UPLOAD_MB", 1)
def test_download_aborts_when_exceeding_limit(tmp_path):
    """
    Test that the server streams the remote file and aborts midway
    if the actual bytes downloaded exceed the limit.
    """
    dest_path = tmp_path / "repo.zip"
    mock_resp = MockStreamResponse(200, chunks=[b"0" * 500, b"0" * 500, b"0" * 500])
    client_instance = MagicMock()
    client_instance.stream.return_value = AsyncContextManagerMock(mock_resp)
    mock_client_class = MagicMock()
    mock_client_class.return_value = AsyncContextManagerMock(client_instance)

    with patch("app.main.httpx.AsyncClient", mock_client_class):
        with pytest.raises(HTTPException) as excinfo:
            anyio.run(
                app.main.download_to_path,
                "https://github.com/test/repo/archive/main.zip",
                dest_path,
            )

        assert excinfo.value.status_code == 413
        assert "Remote repository exceeds" in excinfo.value.detail

        assert not dest_path.exists()


def test_download_blocked_host(tmp_path):
    """Test that the server rejects attempts to download from non-GitHub domains."""
    dest_path = tmp_path / "repo.zip"

    with pytest.raises(HTTPException) as excinfo:
        anyio.run(
            app.main.download_to_path,
            "https://malicious-domain.com/infinite-payload.zip",
            dest_path,
        )

    assert excinfo.value.status_code == 400
    assert "disallowed host" in excinfo.value.detail.lower()
