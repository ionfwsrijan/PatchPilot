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
