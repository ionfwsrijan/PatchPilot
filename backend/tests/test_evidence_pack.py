import json

from app.reports import evidence_pack


def test_deduplicate_findings_from_raw_outputs():
    semgrep_stdout = json.dumps(
        {
            "results": [
                {
                    "check_id": "python.django.security.audit.xss",
                    "path": "app/views.py",
                    "start": {"line": 10},
                    "extra": {"message": "Possible XSS", "metadata": {"severity": "HIGH"}},
                },
                {
                    "check_id": "python.django.security.audit.xss",
                    "path": "app/helpers.py",
                    "start": {"line": 5},
                    "extra": {"message": "Possible XSS", "metadata": {"severity": "HIGH"}},
                },
                {
                    "check_id": "python.django.security.audit.sql_injection",
                    "path": "app/query.py",
                    "start": {"line": 42},
                    "extra": {"message": "SQL injection risk", "metadata": {"severity": "CRITICAL"}},
                },
            ]
        }
    )
    osv_stdout = json.dumps({"results": []})
    gitleaks_stdout = json.dumps([])

    deduped_findings, raw_total, deduped_count, source = evidence_pack._load_deduped_findings(
        job_id="missing-job", raw_outputs={
            "semgrep": semgrep_stdout,
            "osv": osv_stdout,
            "gitleaks": gitleaks_stdout,
        },
    )

    assert source == "in-memory raw scan results"
    assert raw_total == 3
    assert deduped_count == 2

    xss_finding = next(
        f for f in deduped_findings if f["rule_id"] == "python.django.security.audit.xss"
    )
    assert sorted(xss_finding["related_files"]) == ["app/helpers.py", "app/views.py"]
    assert xss_finding["severity"] == "HIGH"

    sql_finding = next(
        f for f in deduped_findings if f["rule_id"] == "python.django.security.audit.sql_injection"
    )
    assert sql_finding["related_files"] == ["app/query.py"]
