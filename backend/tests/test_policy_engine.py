from app.models import Finding
from app.policy.evaluator import evaluate_policy


def test_policy_fails_on_critical():
    findings = [
        Finding(
            id="1",
            category="sast",
            severity="CRITICAL",
            title="Critical issue",
        )
    ]

    policy = {
        "block_if": {
            "severity": "critical",
            "threshold": 0,
        }
    }

    result = evaluate_policy(findings, policy)

    assert result["policy_status"] == "FAILED"
    assert len(result["violations"]) == 1


def test_policy_passes_without_critical():
    findings = []

    policy = {
        "block_if": {
            "severity": "critical",
            "threshold": 0,
        }
    }

    result = evaluate_policy(findings, policy)

    assert result["policy_status"] == "PASSED"
    assert len(result["violations"]) == 0


def test_policy_counts_multiple_critical_findings():
    findings = [
        Finding(
            id="1",
            category="sast",
            severity="CRITICAL",
            title="Issue 1",
        ),
        Finding(
            id="2",
            category="sast",
            severity="CRITICAL",
            title="Issue 2",
        ),
    ]

    policy = {
        "block_if": {
            "severity": "critical",
            "threshold": 1,
        }
    }

    result = evaluate_policy(findings, policy)

    assert result["policy_status"] == "FAILED"
    assert result["violations"][0]["actual"] == 2
