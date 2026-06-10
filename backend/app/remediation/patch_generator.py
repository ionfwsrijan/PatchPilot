"""Patch generation for remediation engine."""

import difflib
from pathlib import Path
from typing import Optional


class PatchGenerator:
    """Generate unified diff patches for security remediations."""

    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir

    def generate_dependency_patch(
        self,
        package_name: str,
        current_version: str,
        fixed_version: str,
    ) -> Optional[str]:
        manifest_path = self.repo_dir / "requirements.txt"
        if not manifest_path.exists():
            return None

        original_content = manifest_path.read_text()
        new_content = original_content.replace(current_version, fixed_version)

        if new_content == original_content:
            return None

        return self._generate_unified_diff(manifest_path, original_content, new_content)

    def _generate_unified_diff(self, file_path: Path, original: str, new: str) -> str:
        original_lines = original.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
        return "".join(diff)

    def supports_patch(self, finding_id: str) -> bool:
        return finding_id.startswith("osv:")