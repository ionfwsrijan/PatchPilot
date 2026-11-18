from app.ml.fp_classifier import classify, is_likely_false_positive, load_noisy_rules


def base(**over):
    f = {
        "scanner": "semgrep",
        "rule_id": "python.lang.security.audit.exec",
        "file_path": "app/main.py",
        "severity_score": 8,
        "cwe": "CWE-95",
    }
    f.update(over)
    return f


def test_test_path_raises_score():
    assert classify(base(file_path="tests/test_login.py")) > classify(base())


def test_nested_test_dir_counts_but_filename_alone_does_not():
    assert classify(base(file_path="src/__tests__/a.js")) > classify(base())
    assert classify(base(file_path="src/tests.py")) == classify(base())


def test_low_severity_raises_score():
    assert classify(base(severity_score=2)) > classify(base(severity_score=8))


def test_missing_cve_raises_score():
    assert classify(base(cwe=None)) > classify(base())


def test_known_noisy_rule_raises_score():
    assert "semgrep" in load_noisy_rules()
    noisy = base(rule_id="python.lang.best-practice.debug-print")
    assert classify(noisy) > classify(base())


def test_noisy_rule_matches_by_suffix():
    noisy = base(rule_id="some.prefix.javascript.console.log")
    assert classify(noisy) > classify(base())


def test_secret_finding_is_low_probability():
    secret = {"scanner": "gitleaks", "rule_id": "generic-api-key", "file_path": "a.py"}
    assert classify(secret) < 0.2


def test_osv_finding_is_very_low():
    osv = {"scanner": "osv", "file_path": "package-lock.json", "severity_score": 7}
    assert classify(osv) <= classify(secret_like())


def secret_like():
    return {"scanner": "gitleaks", "file_path": "a.py"}


def test_score_clamped_and_threshold():
    worst = base(
        file_path="tests/x.py",
        severity_score=1,
        cwe=None,
        rule_id="javascript.console.log",
    )
    score = classify(worst)
    assert 0.0 <= score <= 1.0
    assert is_likely_false_positive(score)
    assert not is_likely_false_positive(classify(base()))


def test_missing_rules_file_does_not_crash(tmp_path):
    assert 0.0 <= classify(base(), rules_path=str(tmp_path / "nope.yaml")) <= 1.0
