from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_leaderboard_update_spam_blocked():
    """Test that a massive username gets rejected by Pydantic validation to prevent DoS."""
    res = client.post(
        "/leaderboard/update",
        json={
            "github_username": "A" * 1000,
            "pr_description": "Fixes #1",
            "fixes_passed": 1,
            "is_pr_merged": True,
        },
    )

    assert res.status_code == 422
    assert "String should have at most 39 characters" in res.text


def test_leaderboard_update_invalid_chars_blocked():
    """Test that usernames with invalid characters (like !) are rejected."""
    res = client.post(
        "/leaderboard/update",
        json={"github_username": "hacker_user!", "pr_description": "Fixes #2"},
    )

    assert res.status_code == 422
    assert "String should match pattern" in res.text


def test_leaderboard_update_valid_username_accepted():
    """Test that a normal, valid GitHub username is processed correctly."""
    from unittest.mock import patch

    with patch("app.main.upsert_contributor_stat") as mock_upsert:
        res = client.post(
            "/leaderboard/update",
            json={
                "github_username": "valid-user123",
                "pr_description": "Fixes #3",
                "fixes_passed": 1,
                "is_pr_merged": True,
            },
        )

        assert res.status_code == 200
        assert res.json()["status"] == "success"
        mock_upsert.assert_called_once()


def test_leaderboard_update_returns_401_without_api_key(monkeypatch):
    """Test that a leaderboard update returns 401 when no api key is passed."""
    monkeypatch.setenv("PATCHPILOT_API_KEY", "test-secret")
    res = client.post(
        "/leaderboard/update",
        json={
            "github_username": "some_username",
            "pr_description": "Closes #1 Closes #2 Closes #3",
            "fixes_passed": 100,
            "is_pr_merged": True,
        },
    )

    assert res.status_code == 401


def test_leaderboard_update_returns_401_with_wrong_key(monkeypatch):
    """Test that a leaderboard update returns 401 when wrong api key is passed."""
    monkeypatch.setenv("PATCHPILOT_API_KEY", "test-secret")
    res = client.post(
        "/leaderboard/update",
        headers={"Authorization": "Bearer wrong-key"},
        json={
            "github_username": "some_username",
            "pr_description": "Closes #1",
            "fixes_passed": 1,
            "is_pr_merged": True,
        },
    )

    assert res.status_code == 401


def test_leaderboard_update_succeeds_with_valid_key(monkeypatch):
    """Test that a leaderboard update succeeds with a valid api key."""
    from unittest.mock import patch

    monkeypatch.setenv("PATCHPILOT_API_KEY", "test-secret")

    with patch("app.main.upsert_contributor_stat") as mock_upsert:
        res = client.post(
            "/leaderboard/update",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "github_username": "valid-user",
                "pr_description": "Fixes #5",
                "fixes_passed": 1,
                "is_pr_merged": True,
            },
        )

        assert res.status_code == 200
        assert res.json()["status"] == "success"
        mock_upsert.assert_called_once()
