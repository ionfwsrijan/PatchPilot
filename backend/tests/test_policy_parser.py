import pytest
from app.policy.parser import parse_policy


def test_valid_policy(tmp_path):
    policy_file = tmp_path / "policy.yaml"

    policy_file.write_text(
        """
block_if:
  severity: critical
  threshold: 0
"""
    )

    policy = parse_policy(policy_file)

    assert policy["block_if"]["severity"] == "critical"
    assert policy["block_if"]["threshold"] == 0


def test_invalid_severity(tmp_path):
    policy_file = tmp_path / "policy.yaml"

    policy_file.write_text(
        """
block_if:
  severity: invalid
  threshold: 0
"""
    )

    with pytest.raises(ValueError):
        parse_policy(policy_file)


def test_missing_block_if(tmp_path):
    policy_file = tmp_path / "policy.yaml"

    policy_file.write_text(
        """
allow_if:
  severity: critical
  threshold: 0
"""
    )

    with pytest.raises(ValueError):
        parse_policy(policy_file)