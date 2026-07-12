import yaml


VALID_SEVERITIES = {"critical", "high", "medium", "low"}


def parse_policy(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        policy = yaml.safe_load(file)

    if not isinstance(policy, dict):
        raise ValueError("Policy must be a dictionary.")

    if "block_if" not in policy:
        raise ValueError("Policy must contain 'block_if'.")

    block = policy["block_if"]

    if not isinstance(block, dict):
        raise ValueError("'block_if' must be a dictionary.")

    if "severity" not in block:
        raise ValueError("'block_if' must contain 'severity'.")

    if "threshold" not in block:
        raise ValueError("'block_if' must contain 'threshold'.")

    severity = block["severity"].lower()

    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity: {severity}")

    threshold = block["threshold"]

    if not isinstance(threshold, int):
        raise ValueError("Threshold must be an integer.")

    return policy