import pytest

from app.utils.fs import safe_job_dir


def test_valid_job_id_returns_correct_path(tmp_path):
    work_root = tmp_path / "work"
    work_root.mkdir()

    result = safe_job_dir(work_root, "job123")

    assert result == (work_root / "job123").resolve()


def test_job_id_with_slash_raises(tmp_path):
    work_root = tmp_path / "work"
    work_root.mkdir()

    with pytest.raises(ValueError):
        safe_job_dir(work_root, "abc/def")


def test_job_id_with_dot_dot_raises(tmp_path):
    work_root = tmp_path / "work"
    work_root.mkdir()

    with pytest.raises(ValueError):
        safe_job_dir(work_root, "../etc")


def test_path_traversal_sibling_raises(tmp_path):
    work_root = tmp_path / "work"
    work_root.mkdir()

    with pytest.raises(ValueError):
        safe_job_dir(work_root, "../work_evil")
