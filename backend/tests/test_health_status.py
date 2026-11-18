from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.shutil.which", return_value="/usr/bin/tool")
def test_health_200_when_all_scanners_present(_which):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


@patch(
    "app.main.shutil.which",
    side_effect=lambda name: None if name == "semgrep" else "/bin/x",
)
def test_health_503_when_scanner_missing(_which):
    response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["status"] == "degraded"
    assert body["scanners"]["semgrep"] is False
