from app.regression import compare_scans


def test_compare_scans_detects_regressions():
    baseline = [
        {
            "rule_id": "R1",
            "scanner": "semgrep",
            "file_path": "app.py",
            "line_number": 10,
            "severity": "HIGH",
        }
    ]

    current = [
        {
            "rule_id": "R1",
            "scanner": "semgrep",
            "file_path": "app.py",
            "line_number": 10,
            "severity": "HIGH",
        },
        {
            "rule_id": "R2",
            "scanner": "gitleaks",
            "file_path": "config.py",
            "line_number": 20,
            "severity": "CRITICAL",
        },
    ]

    result = compare_scans(baseline, current)

    assert len(result["introduced"]) == 1
    assert len(result["persistent"]) == 1
    assert len(result["resolved"]) == 0
    assert result["regressions"]["critical"] == 1
    assert result["overall_trend"] == "Worsened"


def test_compare_scans_detects_improvements():
    baseline = [
        {
            "rule_id": "R1",
            "scanner": "semgrep",
            "file_path": "app.py",
            "line_number": 10,
            "severity": "HIGH",
        }
    ]

    current = []

    result = compare_scans(baseline, current)

    assert len(result["resolved"]) == 1
    assert result["improvements"]["high"] == 1
    assert result["overall_trend"] == "Improved"