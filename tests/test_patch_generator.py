"""Unit tests for patch generation functionality."""

import tempfile
from pathlib import Path

import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.remediation.patch_generator import PatchGenerator


class TestPatchGenerator:
    """Test cases for PatchGenerator class."""

    def test_generate_dependency_patch_requirements_txt(self):
        """Test generating patch for requirements.txt file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir)
            req_file = repo_dir / "requirements.txt"
            req_file.write_text("requests==2.28.0\nflask==2.0.0\n")

            generator = PatchGenerator(repo_dir)
            diff = generator.generate_dependency_patch(
                package_name="requests",
                current_version="2.28.0",
                fixed_version="2.31.0",
            )

            assert diff is not None
            assert "requests==2.31.0" in diff
            assert "-requests==2.28.0" in diff
            assert "+requests==2.31.0" in diff
            assert "flask==2.0.0" in diff  # Unchanged line preserved

    def test_generate_dependency_patch_package_json(self):
        """Test generating patch for package.json file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir)
            pkg_file = repo_dir / "package.json"
            pkg_file.write_text('{"dependencies": {"express": "4.17.3"}}')

            generator = PatchGenerator(repo_dir)
            diff = generator.generate_dependency_patch(
                package_name="express",
                current_version="4.17.3",
                fixed_version="4.18.0",
            )

            assert diff is not None
            assert "express" in diff
            assert "4.18.0" in diff

    def test_no_manifest_file(self):
        """Test when no manifest file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir)
            generator = PatchGenerator(repo_dir)

            diff = generator.generate_dependency_patch(
                package_name="requests",
                current_version="2.28.0",
                fixed_version="2.31.0",
            )

            assert diff is None

    def test_package_not_found_in_manifest(self):
        """Test when package doesn't exist in manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir)
            req_file = repo_dir / "requirements.txt"
            req_file.write_text("flask==2.0.0\n")

            generator = PatchGenerator(repo_dir)
            diff = generator.generate_dependency_patch(
                package_name="requests",
                current_version="2.28.0",
                fixed_version="2.31.0",
            )

            assert diff is None

    def test_supports_patch_osv(self):
        """Test supports_patch returns True for OSV findings."""
        generator = PatchGenerator(Path("."))
        assert generator.supports_patch("osv:PYSEC-2024-123") is True

    def test_supports_patch_gitleaks(self):
        """Test supports_patch returns False for Gitleaks findings."""
        generator = PatchGenerator(Path("."))
        assert generator.supports_patch("gitleaks:secret") is False

    def test_supports_patch_semgrep(self):
        """Test supports_patch returns False for Semgrep findings."""
        generator = PatchGenerator(Path("."))
        assert generator.supports_patch("semgrep:rule") is False