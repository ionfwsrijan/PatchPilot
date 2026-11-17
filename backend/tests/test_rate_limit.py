from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _post_bad_url():
    # An invalid URL is rejected with 400 before any download or scan starts,
    # but the request still counts against the limit.
    return client.post(
        "/scan-url", data={"repo_url": "not-a-url", "project_name": "rl"}
    )


def test_sixth_scan_request_is_rate_limited(monkeypatch):
    monkeypatch.delenv("SCAN_RATE_LIMIT", raising=False)
    for _ in range(5):
        assert _post_bad_url().status_code == 400
    res = _post_bad_url()
    assert res.status_code == 429
    assert "Retry-After" in res.headers
    assert int(res.headers["Retry-After"]) > 0


def test_limit_is_configurable(monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT", "2/minute")
    assert _post_bad_url().status_code == 400
    assert _post_bad_url().status_code == 400
    assert _post_bad_url().status_code == 429


def test_limit_applies_to_scan_upload(monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT", "1/minute")
    files = {"project": ("a.txt", b"x", "text/plain")}
    first = client.post("/scan", files=files)
    assert first.status_code != 429
    second = client.post("/scan", files=files)
    assert second.status_code == 429
