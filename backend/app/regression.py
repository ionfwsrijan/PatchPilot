from collections import Counter


def _finding_key(finding: dict):
    """Generate a stable identity for a finding across scans."""
    return (
        finding.get("rule_id"),
        finding.get("scanner"),
        finding.get("file_path"),
        finding.get("line_number"),
    )


def compare_scans(baseline_findings, current_findings):
    baseline = {_finding_key(f): f for f in baseline_findings}
    current = {_finding_key(f): f for f in current_findings}

    introduced = []
    resolved = []
    persistent = []

    for key, finding in current.items():
        if key in baseline:
            persistent.append(finding)
        else:
            introduced.append(finding)

    for key, finding in baseline.items():
        if key not in current:
            resolved.append(finding)

    severity_levels = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

    base_counts = Counter(
        f.get("severity", "").upper()
        for f in baseline_findings
    )

    current_counts = Counter(
        f.get("severity", "").upper()
        for f in current_findings
    )

    regressions = {}
    improvements = {}

    for sev in severity_levels:
        diff = current_counts[sev] - base_counts[sev]

        if diff > 0:
            regressions[sev.lower()] = diff
        elif diff < 0:
            improvements[sev.lower()] = abs(diff)

    overall = "No Change"

    if sum(regressions.values()) > sum(improvements.values()):
        overall = "Worsened"
    elif sum(improvements.values()) > sum(regressions.values()):
        overall = "Improved"

    return {
        "introduced": introduced,
        "resolved": resolved,
        "persistent": persistent,
        "regressions": regressions,
        "improvements": improvements,
        "overall_trend": overall,
    }