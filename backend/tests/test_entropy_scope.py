from app.scanners.entropy import MAX_FILE_BYTES, run_entropy

SECRET = 'token = "aB3$kP9zQ7vL2xR8mN4wT6yU1cE5hJ0g"\n'


def test_finds_secret_in_source_file(tmp_path):
    (tmp_path / "app.py").write_text(SECRET)
    findings = run_entropy(tmp_path)
    assert [f.location.path for f in findings] == ["app.py"]


def test_skips_dependency_and_build_dirs(tmp_path):
    for d in ("node_modules", "venv", ".venv", "build", "dist", "__pycache__"):
        (tmp_path / d / "pkg").mkdir(parents=True)
        (tmp_path / d / "pkg" / "x.py").write_text(SECRET)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "keep.py").write_text(SECRET)

    findings = run_entropy(tmp_path)
    assert [f.location.path.replace("\\", "/") for f in findings] == ["src/keep.py"]


def test_skips_files_over_size_cap(tmp_path):
    (tmp_path / "big.js").write_text(SECRET + "x" * MAX_FILE_BYTES)
    assert run_entropy(tmp_path) == []
