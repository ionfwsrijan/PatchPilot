from collections import Counter


def evaluate_policy(findings, policy):
    counts = Counter()

    for finding in findings:
        counts[finding.severity.lower()] += 1

    violations = []

    if "block_if" in policy:
        severity = policy["block_if"]["severity"]
        threshold = policy["block_if"]["threshold"]

        actual = counts.get(severity, 0)

        if actual > threshold:
            violations.append(
                {
                    "rule": f"{severity}>{threshold}",
                    "actual": actual,
                }
            )
    return {
        "policy_status": "FAILED" if violations else "PASSED",
        "violations": violations,
    }
