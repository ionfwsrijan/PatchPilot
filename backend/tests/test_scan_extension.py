import io
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_scan_rejects_non_zip_before_writing():
    with patch("app.main.ensure_dir") as ensure_dir:
        files = {"project": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
        response = client.post("/scan", files=files, data={"project_name": "t"})

    assert response.status_code == 415
    assert ".zip" in response.json()["detail"]
    ensure_dir.assert_not_called()


def test_scan_extension_check_is_case_insensitive():
    files = {"project": ("ARCHIVE.ZIP", io.BytesIO(b"not a zip"), "application/zip")}
    response = client.post("/scan", files=files, data={"project_name": "t"})
    # Passes the extension check, then fails zip validation.
    assert response.status_code == 400
