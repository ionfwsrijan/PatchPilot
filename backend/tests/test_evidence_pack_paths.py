import zipfile

import pytest

from app.reports.evidence_pack import _safe_name, build_evidence_pack


def _make_job(tmp_path):
    job_dir = tmp_path / "job"
    (job_dir / "raw").mkdir(parents=True)
    for name in ("semgrep.json", "osv.json", "gitleaks.json"):
        (job_dir / "raw" / name).write_text("[]", encoding="utf-8")
    repo_dir = job_dir / "repo"
    repo_dir.mkdir()
    out_dir = job_dir / "out"
    out_dir.mkdir()
    return job_dir, repo_dir, out_dir


@pytest.mark.parametrize(
    "name",
    [
        "../../evil",
        r"..\..\evil",
        "/etc/passwd",
        r"C:\Windows\system32",
        "a/b/../../../c",
        r"mixed/sep\arators",
        "caf\u00e9-\u202e-\u4e2d\u6587",
        "..",
        "",
    ],
)
def test_malicious_project_names_stay_inside_out_dir(tmp_path, name):
    job_dir, repo_dir, out_dir = _make_job(tmp_path)

    zip_path = build_evidence_pack(repo_dir, out_dir, name, "abc123", job_dir=job_dir)

    assert zip_path.parent == out_dir
    assert zip_path.exists()
    # Nothing was written outside the output directory
    assert {p.name for p in job_dir.iterdir()} == {"raw", "repo", "out"}
    assert list(tmp_path.iterdir()) == [job_dir]

    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
    assert "REPORT.md" in names
    assert "raw/semgrep.json" in names
    for entry in names:
        assert not entry.startswith("/")
        assert ".." not in entry.split("/")
        assert "\\" not in entry
        assert ":" not in entry


def test_normal_project_name_is_kept(tmp_path):
    job_dir, repo_dir, out_dir = _make_job(tmp_path)
    zip_path = build_evidence_pack(
        repo_dir, out_dir, "my-app_1.0", "job1", job_dir=job_dir
    )
    assert "patchpilot_evidence_my-app_1.0_job1_" in zip_path.name


def test_safe_name_fallback():
    assert _safe_name("") == "project"
    assert _safe_name("..", "job") == "job"
    assert _safe_name("a/b") == "a_b"
