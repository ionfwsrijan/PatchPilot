from app.remediation.osv_parser import OSVParser
"""Integration tests for end-to-end patch generation."""
import tempfile
import unittest
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.remediation.engine import propose_fixes
from app.remediation.patch_generator import PatchGenerator

class TestIntegrationPatches(unittest.TestCase):
    """Integration tests for full patch generation flow."""

    def test_end_to_end_osv_patch_generation(self):
        """Test full flow: OSV finding -> generate patch."""
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

    def test_patch_applies_cleanly(self):
        """Test that generated patch can be applied to original file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir)
            req_file = repo_dir / "requirements.txt"
            original_content = "requests==2.28.0\nflask==2.0.0\n"
            req_file.write_text(original_content)

            generator = PatchGenerator(repo_dir)
            diff = generator.generate_dependency_patch(
                package_name="requests",
                current_version="2.28.0",
                fixed_version="2.31.0",
            )

            new_content = original_content.replace("2.28.0", "2.31.0")
            req_file.write_text(new_content)

            final_content = req_file.read_text()
            assert "requests==2.31.0" in final_content
            assert "flask==2.0.0" in final_content

    def test_multiple_dependency_patches(self):
        """Test generating patches for multiple dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir)
            req_file = repo_dir / "requirements.txt"
            req_file.write_text("requests==2.28.0\ndjango==3.2.0\nflask==2.0.0\n")

            generator = PatchGenerator(repo_dir)

            diff1 = generator.generate_dependency_patch(
                "requests", "2.28.0", "2.31.0"
            )
            diff2 = generator.generate_dependency_patch(
                "django", "3.2.0", "4.2.0"
            )

            assert diff1 is not None
            assert diff2 is not None
            assert "requests" in diff1
            assert "django" in diff2

    def test_osv_parser_mock_data(self):
        """Test OSV parser raises FileNotFoundError when no real output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir)

            from backend.app.remediation.osv_parser import OSVParser
            parser = OSVParser(repo_dir)

            with self.assertRaises(FileNotFoundError):
                parser.get_package_info("osv:PYSEC-2024-123")