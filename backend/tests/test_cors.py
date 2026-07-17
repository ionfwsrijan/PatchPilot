from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cors_allowed_origin():
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/health", headers=headers)
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    )
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_disallowed_origin():
    headers = {
        "Origin": "https://evil-hacker.com",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/health", headers=headers)
    assert response.status_code == 400
    assert response.text == "Disallowed CORS origin"
