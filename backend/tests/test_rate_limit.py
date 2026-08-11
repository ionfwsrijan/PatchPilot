"""
Tests for IP-based rate limiting on /scan and /scan-url.

Strategy
--------
The rate limit is enforced via a shared FastAPI dependency (_scan_rate_limit)
applied with dependencies=[Depends(_scan_rate_limit)] on both routes.  This
avoids the Python 3.13 + FastAPI 0.115.0 incompatibility where
``from __future__ import annotations`` causes slowapi's functools.wraps wrapper
to present string annotations under extension.py's globals, breaking FastAPI's
dependency injection for complex types like BackgroundTasks and UploadFile.

Tests:
 - Structural: _scan_rate_limit is registered in the limiter; both routes list
   it as a dependency.
 - Behavioural: the 6th /scan-url request from the same IP returns HTTP 429
   with a Retry-After header.
 - Independence: two different IPs each get their own quota.
 - Header format: Retry-After is a numeric string.
"""

import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

# Ensure the env var is set before the first import of app.main
os.environ.setdefault("SCAN_RATE_LIMIT", "5/minute")

from app.main import _scan_rate_limit, app, limiter  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client(remote_addr: str) -> TestClient:
    """TestClient whose every request carries *remote_addr* as client IP."""
    return TestClient(app, headers={"X-Forwarded-For": remote_addr})


def _scan_url_post(client: TestClient):
    return client.post(
        "/scan-url",
        data={
            "repo_url": "https://github.com/owner/repo",
            "project_name": "rate_test",
        },
    )


# ---------------------------------------------------------------------------
# Structural: limiter registration + route dependency wiring
# ---------------------------------------------------------------------------

def test_scan_rate_limit_dep_registered_in_limiter():
    """_scan_rate_limit must be registered in slowapi's internal route limits."""
    # slowapi keys its internal dicts by the fully-qualified function name
    # ("<module>.<qualname>"), e.g. "app.main._scan_rate_limit".
    module = _scan_rate_limit.__module__
    qualname = _scan_rate_limit.__qualname__
    fn_name = f"{module}.{qualname}"

    marked = getattr(limiter, "_Limiter__marked_for_limiting", {})
    route_limits = getattr(limiter, "_route_limits", {})
    dynamic_limits = getattr(limiter, "_dynamic_route_limits", {})

    in_marked = fn_name in marked
    in_route = fn_name in route_limits
    in_dynamic = fn_name in dynamic_limits

    assert in_marked or in_route or in_dynamic, (
        f"'{fn_name}' is not registered in slowapi's limiter.\n"
        f"  _route_limits keys:   {list(route_limits.keys())}\n"
        f"  _dynamic_route_limits keys: {list(dynamic_limits.keys())}\n"
        f"  __marked_for_limiting keys: {list(marked.keys())}"
    )


def test_scan_route_has_rate_limit_dependency():
    """The /scan route must declare _scan_rate_limit as a dependency."""
    route = next(
        (r for r in app.routes if getattr(r, "path", None) == "/scan"), None
    )
    assert route is not None, "/scan route not found in app.routes"
    deps = [d.dependency for d in getattr(route, "dependencies", [])]
    # The dependency stored is the slowapi *wrapper* around _scan_rate_limit,
    # so we check by __name__ (functools.wraps preserves it).
    dep_names = [getattr(d, "__name__", "") for d in deps]
    assert "_scan_rate_limit" in dep_names, (
        f"/scan dependencies do not include '_scan_rate_limit'. Found: {dep_names}"
    )


def test_scan_url_route_has_rate_limit_dependency():
    """The /scan-url route must declare _scan_rate_limit as a dependency."""
    route = next(
        (r for r in app.routes if getattr(r, "path", None) == "/scan-url"), None
    )
    assert route is not None, "/scan-url route not found in app.routes"
    deps = [d.dependency for d in getattr(route, "dependencies", [])]
    dep_names = [getattr(d, "__name__", "") for d in deps]
    assert "_scan_rate_limit" in dep_names, (
        f"/scan-url dependencies do not include '_scan_rate_limit'. Found: {dep_names}"
    )


# ---------------------------------------------------------------------------
# /scan-url — 6th request returns 429
# ---------------------------------------------------------------------------

@patch("app.main.download_to_path", new_callable=AsyncMock)
@patch("app.main.unzip_to_dir")
@patch("app.main._run_single_scan_task", new_callable=AsyncMock)
def test_scan_url_rate_limit_sixth_request_returns_429(
    mock_scan_task, mock_unzip, mock_download
):
    """The 6th /scan-url request from the same IP within the window → 429."""
    mock_download.return_value = None
    mock_unzip.return_value = None
    mock_scan_task.return_value = None

    # Unique IP so this test never collides with others in the same process.
    client = _client("192.168.50.1")

    for i in range(5):
        resp = _scan_url_post(client)
        assert resp.status_code != 429, (
            f"Request {i + 1}/5 was unexpectedly rate-limited: {resp.json()}"
        )

    sixth = _scan_url_post(client)
    assert sixth.status_code == 429, (
        f"Expected 429 on 6th request, got {sixth.status_code}: {sixth.json()}"
    )
    assert "Retry-After" in sixth.headers, (
        "429 response must include a Retry-After header"
    )
    data = sixth.json()
    assert "detail" in data
    detail_lower = data["detail"].lower()
    assert "rate limit" in detail_lower or "rate" in detail_lower, (
        f"Unexpected detail: {data['detail']}"
    )


# ---------------------------------------------------------------------------
# Different IPs have independent quotas
# ---------------------------------------------------------------------------

@patch("app.main.download_to_path", new_callable=AsyncMock)
@patch("app.main.unzip_to_dir")
@patch("app.main._run_single_scan_task", new_callable=AsyncMock)
def test_scan_url_rate_limit_different_ips_are_independent(
    mock_scan_task, mock_unzip, mock_download
):
    """Exhausting IP A's quota must not affect IP B."""
    mock_download.return_value = None
    mock_unzip.return_value = None
    mock_scan_task.return_value = None

    client_a = _client("10.10.10.1")
    client_b = _client("10.20.20.2")

    # Exhaust client_a's quota.
    for _ in range(5):
        _scan_url_post(client_a)

    # client_a must now be rate-limited.
    assert _scan_url_post(client_a).status_code == 429, (
        "client_a should be rate-limited after 5 requests"
    )

    # client_b has used 0 requests — must NOT be rate-limited.
    resp_b = _scan_url_post(client_b)
    assert resp_b.status_code != 429, (
        f"client_b should not be rate-limited, got {resp_b.status_code}: {resp_b.json()}"
    )


# ---------------------------------------------------------------------------
# Custom 429 handler: Retry-After header is numeric
# ---------------------------------------------------------------------------

@patch("app.main.download_to_path", new_callable=AsyncMock)
@patch("app.main.unzip_to_dir")
@patch("app.main._run_single_scan_task", new_callable=AsyncMock)
def test_scan_url_429_retry_after_is_numeric(
    mock_scan_task, mock_unzip, mock_download
):
    """Retry-After header on a 429 response must be parseable as an integer."""
    mock_download.return_value = None
    mock_unzip.return_value = None
    mock_scan_task.return_value = None

    client = _client("172.16.99.1")

    for _ in range(5):
        _scan_url_post(client)

    sixth = _scan_url_post(client)
    assert sixth.status_code == 429
    retry_after = sixth.headers.get("Retry-After", "")
    assert retry_after.lstrip("-").isdigit(), (
        f"Retry-After header '{retry_after}' is not a valid integer string"
    )
