from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_label_finding_success():
    """Test that a finding can be successfully labeled as a false positive."""
    mock_db = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.rowcount = 1
    mock_db.execute.return_value = mock_cursor

    with patch("app.main.get_db", AsyncMock(return_value=mock_db)):
        response = client.post(
            "/findings/fake-finding-123/label",
            json={"false_positive": True, "expected_version": 1},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "finding_id": "fake-finding-123",
        "false_positive": True,
    }
    assert mock_db.execute.call_count == 1
    assert mock_db.commit.called


def test_label_finding_not_found():
    """Test that labeling a non-existent finding returns a 404."""
    mock_db = AsyncMock()
    mock_cursor = AsyncMock()
    # rowcount == 0 means no row matched; second SELECT returns nothing → 404
    mock_cursor.rowcount = 0
    mock_cursor.fetchone.return_value = None
    mock_db.execute.return_value = mock_cursor

    with patch("app.main.get_db", AsyncMock(return_value=mock_db)):
        response = client.post(
            "/findings/missing-finding-404/label",
            json={"false_positive": False, "expected_version": 1},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Finding not found"
    assert not mock_db.commit.called


def test_label_finding_version_conflict():
    """Test that a stale expected_version returns a 409 Conflict."""
    mock_db = AsyncMock()
    mock_cursor = AsyncMock()
    # rowcount == 0 means the WHERE id=? AND version=? clause matched nothing
    mock_cursor.rowcount = 0
    # Second SELECT finds the row → the finding exists, so it's a version conflict
    mock_cursor.fetchone.return_value = {"id": "fake-finding-123"}
    mock_db.execute.return_value = mock_cursor

    with patch("app.main.get_db", AsyncMock(return_value=mock_db)):
        response = client.post(
            "/findings/fake-finding-123/label",
            json={"false_positive": True, "expected_version": 1},
        )

    assert response.status_code == 409
    assert "modified by another user" in response.json()["detail"]
    assert not mock_db.commit.called
