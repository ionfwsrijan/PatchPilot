"""Shared test setup.

app.db and app.main read PATCHPILOT_DB_PATH and PATCHPILOT_WORKDIR once, when
they are imported. Tests that start the app lifespan (TestClient used as a
context manager) would otherwise open the developer's real database and work
folder, and the expired-job cleanup could delete real jobs. So the env vars are
pointed at a throwaway folder here, before any test module imports the app.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_SANDBOX = Path(tempfile.mkdtemp(prefix="patchpilot-tests-")).resolve()
os.environ["PATCHPILOT_DB_PATH"] = str(_SANDBOX / "patchpilot.db")
os.environ["PATCHPILOT_WORKDIR"] = str(_SANDBOX / "work")


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_SANDBOX, ignore_errors=True)


@pytest.fixture(autouse=True)
def _never_touch_real_data():
    """Fail loudly if the app picked up a DB or work folder outside the sandbox."""
    from app import db, main

    for name, value in (("DB_PATH", db.DB_PATH), ("WORK_ROOT", main.WORK_ROOT)):
        resolved = Path(value).resolve()
        if not resolved.is_relative_to(_SANDBOX):
            pytest.fail(
                f"{name} points at {resolved}, outside the test sandbox {_SANDBOX}. "
                "Was app imported before tests/conftest.py ran?"
            )
