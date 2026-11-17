"""IP-based rate limiting for the expensive scan endpoints."""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

DEFAULT_SCAN_RATE_LIMIT = "5/minute"


def get_scan_rate_limit() -> str:
    """Read the limit at request time so SCAN_RATE_LIMIT can be changed per deployment."""
    return os.environ.get("SCAN_RATE_LIMIT", "").strip() or DEFAULT_SCAN_RATE_LIMIT


limiter = Limiter(key_func=get_remote_address)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = getattr(exc, "retry_after", None)
    headers = {"Retry-After": str(retry_after if retry_after else 60)}
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
        headers=headers,
    )
