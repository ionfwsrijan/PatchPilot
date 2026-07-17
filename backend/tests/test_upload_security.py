import io
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.MAX_UPLOAD_SIZE", 1024)
@patch("app.main.MAX_UPLOAD_MB", 1)
def test_upload_fast_fail_via_content_length_header():
    """
    Test that the server rejects uploads early if the Content-Length header
    itself declares a size larger than the allowed limit.
    """
    headers = {"content-length": "9999999"}
    files = {"project": ("dummy.zip", io.BytesIO(b"tiny data"), "application/zip")}
    data = {"project": "test_project"}

    response = client.post("/scan", files=files, data=data, headers=headers)

    assert response.status_code == 413
    assert "Header indicates file is too large" in response.json()["detail"]


@patch("app.main.MAX_UPLOAD_SIZE", 1024)
@patch("app.main.MAX_UPLOAD_MB", 1)
def test_upload_aborts_when_stream_exceeds_limit():
    """
    Test that the server streams the file and aborts midway if the actual
    bytes received exceed the limit, even if the Content-Length header was spoofed.
    """
    oversized_payload = b"0" * 2048
    headers = {"content-length": "500"}

    files = {
        "project": ("malicious.zip", io.BytesIO(oversized_payload), "application/zip")
    }
    data = {"project": "test_project"}

    response = client.post("/scan", files=files, data=data, headers=headers)

    assert response.status_code == 413
    assert "Actual file size exceeds" in response.json()["detail"]
