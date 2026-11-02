import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import main


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def fake_cleanup(monkeypatch, tmp_path):
    fake = AsyncMock(return_value=0)
    monkeypatch.setattr(main, "cleanup_expired_jobs", fake)
    monkeypatch.setattr(main, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(main, "JOB_TTL_HOURS", 12.0)
    # Keep the loop to a single pass during the test.
    monkeypatch.setattr(main, "CLEANUP_INTERVAL_SECONDS", 3600)
    return fake


def test_lifespan_starts_cleanup_loop_with_app_settings(fake_cleanup, monkeypatch):
    monkeypatch.setattr(main, "CLEANUP_STARTUP_DELAY_SECONDS", 0)
    monkeypatch.setitem(main.ACTIVE_SCANS, "scanning1", {"status": "scanning"})
    monkeypatch.setitem(main.ACTIVE_SCANS, "finished1", {"status": "completed"})
    monkeypatch.setitem(main.ORG_CANCEL_EVENTS, "org-live", object())

    with TestClient(main.app):
        assert wait_for(lambda: fake_cleanup.await_count >= 1)

    args, kwargs = fake_cleanup.await_args
    assert args == (main.WORK_ROOT, 12.0)
    assert kwargs["active_job_ids"] == {"scanning1"}
    assert kwargs["active_org_job_ids"] == {"org-live"}


def test_lifespan_does_not_clean_up_before_startup_delay(fake_cleanup):
    assert main.CLEANUP_STARTUP_DELAY_SECONDS > 0

    with TestClient(main.app):
        time.sleep(0.3)

    fake_cleanup.assert_not_awaited()


def test_cleanup_loop_survives_a_failing_pass(fake_cleanup, monkeypatch):
    monkeypatch.setattr(main, "CLEANUP_STARTUP_DELAY_SECONDS", 0)
    monkeypatch.setattr(main, "CLEANUP_INTERVAL_SECONDS", 0.05)
    fake_cleanup.side_effect = [RuntimeError("boom"), 0, 0]

    with TestClient(main.app):
        assert wait_for(lambda: fake_cleanup.await_count >= 3)
