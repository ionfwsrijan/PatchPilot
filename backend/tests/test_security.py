import asyncio

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.security import verify_api_key


def test_verify_api_key_not_set(monkeypatch):
    # Case 1: PATCHPILOT_API_KEY not set -> returns True (auth disabled)
    monkeypatch.delenv("PATCHPILOT_API_KEY", raising=False)
    result = asyncio.run(verify_api_key(None))
    assert result is True


def test_verify_api_key_valid_token(monkeypatch):
    # Case 2: Valid key, correct Bearer token -> returns True
    monkeypatch.setenv("PATCHPILOT_API_KEY", "supersecret")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="supersecret")
    result = asyncio.run(verify_api_key(creds))
    assert result is True


def test_verify_api_key_missing_header(monkeypatch):
    # Case 3: Valid key, no Authorization header -> 401 with WWW-Authenticate: Bearer
    monkeypatch.setenv("PATCHPILOT_API_KEY", "supersecret")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_api_key(None))
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing Authorization header"
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_verify_api_key_wrong_token(monkeypatch):
    # Case 4: Valid key, wrong token -> 401 (not 403) with WWW-Authenticate: Bearer
    monkeypatch.setenv("PATCHPILOT_API_KEY", "supersecret")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrongsecret")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_api_key(creds))
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid API key"
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_verify_api_key_empty_token(monkeypatch):
    # Case 5: Valid key, Bearer prefix but empty token -> 401 with WWW-Authenticate: Bearer
    monkeypatch.setenv("PATCHPILOT_API_KEY", "supersecret")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_api_key(creds))
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid API key"
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
