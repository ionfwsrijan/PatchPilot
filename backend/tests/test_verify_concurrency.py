import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from app.models import VerifyResponse

BLOCK_SECONDS = 2
HEALTH_MAX_SECONDS = BLOCK_SECONDS * 0.75


def _slow_verify_repo(_repo_dir: Path) -> VerifyResponse:
    time.sleep(BLOCK_SECONDS)
    return VerifyResponse(ok=True, checks={})


def _slow_scan_repo_dir(*_args, **_kwargs):
    time.sleep(BLOCK_SECONDS)
    return [], [], [], [], []


@pytest.mark.anyio
async def test_verify_does_not_block_event_loop(tmp_path):
    """Health checks must stay responsive while /verify runs blocking work."""
    job_id = "verify-concurrency-test"
    repo_dir = tmp_path / job_id / "repo"
    repo_dir.mkdir(parents=True)

    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.close = AsyncMock()

    async def mock_get_baseline_findings(_job_id: str):
        return set()

    with (
        patch("app.main.WORK_ROOT", tmp_path),
        patch("app.main.verify_repo", _slow_verify_repo),
        patch("app.main._scan_repo_dir", _slow_scan_repo_dir),
        patch("app.main.get_baseline_findings", mock_get_baseline_findings),
        patch("app.main.get_db", AsyncMock(return_value=db)),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            t0 = time.monotonic()
            health_done_at: dict[str, float] = {}

            async def run_verify():
                return await client.post("/verify", data={"job_id": job_id})

            async def run_health():
                await asyncio.sleep(0.05)
                response = await client.get("/health")
                health_done_at["elapsed"] = time.monotonic() - t0
                return response

            verify_response, health_response = await asyncio.gather(
                run_verify(), run_health()
            )

    assert health_response.status_code == 200
    assert verify_response.status_code == 200
    assert health_done_at["elapsed"] < HEALTH_MAX_SECONDS
    assert time.monotonic() - t0 >= BLOCK_SECONDS
