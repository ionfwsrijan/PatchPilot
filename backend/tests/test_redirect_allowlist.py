from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.main import ALLOWED_REDIRECT_HOSTS, MAX_REDIRECTS, download_to_path


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

    def __init__(self, status_code, headers=None, chunks=None):
        """Initialize the mock stream response."""
        self.status_code = status_code
        self.headers = headers or {}
        self.chunks = chunks or []

    async def aiter_bytes(self, chunk_size):
        """Iterate over the mocked byte chunks."""
        for chunk in self.chunks:
            yield chunk


def _make_redirect_response(
    location: str, status_code: int = 302
) -> MockStreamResponse:
    return MockStreamResponse(status_code=status_code, headers={"location": location})


def _make_ok_response(content: bytes = b"PK\x03\x04fakezip") -> MockStreamResponse:
    return MockStreamResponse(status_code=200, chunks=[content])


def test_allowlist_contains_required_github_hosts():
    assert "github.com" in ALLOWED_REDIRECT_HOSTS
    assert "codeload.github.com" in ALLOWED_REDIRECT_HOSTS


def test_max_redirects_is_reasonable():
    assert 1 <= MAX_REDIRECTS <= 10


@pytest.mark.anyio
async def test_blocks_redirect_to_internal_metadata_ip(tmp_path):
    dest = tmp_path / "repo.zip"
    redirect_resp = _make_redirect_response("http://169.254.169.254/latest/meta-data/")
    ok_resp = _make_ok_response()

    mock_client = MagicMock()
    mock_client.stream.side_effect = [
        AsyncContextManagerMock(redirect_resp),
        AsyncContextManagerMock(ok_resp),
    ]

    with patch("app.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await download_to_path(
                "https://github.com/owner/repo/archive/refs/heads/main.zip", dest
            )

    assert exc_info.value.status_code == 400
    assert "169.254.169.254" in exc_info.value.detail


@pytest.mark.anyio
async def test_blocks_redirect_to_localhost(tmp_path):
    dest = tmp_path / "repo.zip"
    redirect_resp = _make_redirect_response("http://localhost/internal")

    mock_client = MagicMock()
    mock_client.stream.side_effect = [AsyncContextManagerMock(redirect_resp)]

    with patch("app.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await download_to_path(
                "https://github.com/owner/repo/archive/refs/heads/main.zip", dest
            )

    assert exc_info.value.status_code == 400
    assert "localhost" in exc_info.value.detail


@pytest.mark.anyio
async def test_blocks_redirect_to_arbitrary_external_host(tmp_path):
    dest = tmp_path / "repo.zip"
    redirect_resp = _make_redirect_response("https://evil.example.com/malicious.zip")

    mock_client = MagicMock()
    mock_client.stream.side_effect = [AsyncContextManagerMock(redirect_resp)]

    with patch("app.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await download_to_path(
                "https://github.com/owner/repo/archive/refs/heads/main.zip", dest
            )

    assert exc_info.value.status_code == 400
    assert "evil.example.com" in exc_info.value.detail


@pytest.mark.anyio
async def test_follows_redirect_to_codeload_github(tmp_path):
    dest = tmp_path / "repo.zip"
    fake_zip = b"PK\x03\x04fakezip"
    redirect_resp = _make_redirect_response(
        "https://codeload.github.com/owner/repo/zip/refs/heads/main"
    )
    ok_resp = _make_ok_response(content=fake_zip)

    mock_client = MagicMock()
    mock_client.stream.side_effect = [
        AsyncContextManagerMock(redirect_resp),
        AsyncContextManagerMock(ok_resp),
    ]

    with patch("app.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await download_to_path(
            "https://github.com/owner/repo/archive/refs/heads/main.zip", dest
        )

    assert dest.exists()
    assert dest.read_bytes() == fake_zip


@pytest.mark.anyio
async def test_direct_200_no_redirect(tmp_path):
    dest = tmp_path / "repo.zip"
    fake_zip = b"PK\x03\x04directzip"
    ok_resp = _make_ok_response(content=fake_zip)

    mock_client = MagicMock()
    mock_client.stream.return_value = AsyncContextManagerMock(ok_resp)

    with patch("app.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await download_to_path(
            "https://github.com/owner/repo/archive/refs/heads/main.zip", dest
        )

    assert dest.read_bytes() == fake_zip


@pytest.mark.anyio
async def test_too_many_redirects_raises(tmp_path):
    dest = tmp_path / "repo.zip"
    redirect_resp = _make_redirect_response(
        "https://github.com/owner/repo/archive/refs/heads/main.zip"
    )

    mock_client = MagicMock()
    mock_client.stream.return_value = AsyncContextManagerMock(redirect_resp)

    with patch("app.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await download_to_path(
                "https://github.com/owner/repo/archive/refs/heads/main.zip", dest
            )

    assert exc_info.value.status_code == 400
    assert "Too many redirects" in exc_info.value.detail


@pytest.mark.anyio
async def test_redirect_missing_location_header_raises(tmp_path):
    dest = tmp_path / "repo.zip"
    bad_redirect = MockStreamResponse(status_code=302, headers={})

    mock_client = MagicMock()
    mock_client.stream.return_value = AsyncContextManagerMock(bad_redirect)

    with patch("app.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await download_to_path(
                "https://github.com/owner/repo/archive/refs/heads/main.zip", dest
            )

    assert exc_info.value.status_code == 400
    assert "Location" in exc_info.value.detail


@pytest.mark.anyio
async def test_non_200_non_redirect_raises(tmp_path):
    dest = tmp_path / "repo.zip"
    not_found = MockStreamResponse(status_code=404)

    mock_client = MagicMock()
    mock_client.stream.return_value = AsyncContextManagerMock(not_found)

    with patch("app.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await download_to_path(
                "https://github.com/owner/repo/archive/refs/heads/main.zip", dest
            )

    assert exc_info.value.status_code == 400
    assert "404" in exc_info.value.detail
