from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import ACTIVE_SCANS, WORK_ROOT, app

client = TestClient(app)

JOB_ID = "deljob123"


def _make_job_dir():
    (WORK_ROOT / JOB_ID).mkdir(parents=True, exist_ok=True)


def test_delete_running_job_returns_409_and_keeps_workspace():
    _make_job_dir()
    ACTIVE_SCANS[JOB_ID] = {"status": "running"}
    try:
        with patch("app.main.delete_job", new_callable=AsyncMock) as mock_delete:
            response = client.delete(f"/jobs/{JOB_ID}")
        assert response.status_code == 409
        assert (WORK_ROOT / JOB_ID).exists()
        mock_delete.assert_not_called()
    finally:
        ACTIVE_SCANS.pop(JOB_ID, None)
        import shutil

        shutil.rmtree(WORK_ROOT / JOB_ID, ignore_errors=True)


@patch("app.main.get_db", new_callable=AsyncMock)
@patch("app.main.delete_job", new_callable=AsyncMock)
def test_delete_finished_job_clears_active_scan_entry(_delete, _get_db):
    _make_job_dir()
    ACTIVE_SCANS[JOB_ID] = {"status": "completed"}
    response = client.delete(f"/jobs/{JOB_ID}")
    assert response.status_code == 200
    assert JOB_ID not in ACTIVE_SCANS
    assert not (WORK_ROOT / JOB_ID).exists()
