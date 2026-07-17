from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_mock_client(status_code=200, json_data=None, side_effect=None):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    if json_data:
        mock_response.json.return_value = json_data

    mock_client_instance = AsyncMock()
    if side_effect:
        mock_client_instance.get.side_effect = side_effect
    else:
        mock_client_instance.get.return_value = mock_response

    mock_client = MagicMock()
    mock_client.__aenter__.return_value = mock_client_instance
    mock_client.__aexit__.return_value = False
    return mock_client


@patch("app.main.httpx.AsyncClient")
def test_ollama_health_success(mock_async_client):
    """Test that the endpoint returns True and a list of models when Ollama is running."""
    mock_async_client.return_value = create_mock_client(
        status_code=200,
        json_data={"models": [{"name": "llama3:latest"}, {"name": "mistral:instruct"}]},
    )

    response = client.get("/api/health/ollama")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["base_url"] == "http://localhost:11434"
    assert "llama3:latest" in data["models"]
    assert "mistral:instruct" in data["models"]


@patch("app.main.httpx.AsyncClient")
def test_ollama_health_offline(mock_async_client):
    """Test that the endpoint safely returns False when Ollama throws a connection error."""
    mock_async_client.return_value = create_mock_client(
        side_effect=httpx.ConnectError("Connection refused")
    )

    response = client.get("/api/health/ollama")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["base_url"] == "http://localhost:11434"
    assert data["models"] == []


@patch("app.main.httpx.AsyncClient")
def test_ollama_health_bad_status(mock_async_client):
    """Test that the endpoint safely returns False if Ollama returns a 404 or 500."""
    mock_async_client.return_value = create_mock_client(status_code=404)

    response = client.get("/api/health/ollama")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["base_url"] == "http://localhost:11434"
    assert data["models"] == []


@patch("app.main.httpx.AsyncClient")
def test_ollama_health_timeout(mock_async_client):
    """Test that the endpoint safely returns False when Ollama times out."""
    mock_async_client.return_value = create_mock_client(
        side_effect=httpx.TimeoutException("Connection timed out")
    )

    response = client.get("/api/health/ollama")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["base_url"] == "http://localhost:11434"
    assert data["models"] == []
