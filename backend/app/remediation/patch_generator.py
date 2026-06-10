"""Patch generation for remediation engine.

Generates unified diffs for security fixes, starting with dependency upgrades.
"""

import difflib
from pathlib import Path
from typing import List, Optional, Tuple


class PatchGenerator:
    """Generate unified diff patches for security remediations."""

    def __init__(self, repo_dir: Path):
        """Initialize with repository directory path."""
        self.repo_dir = repo_dir

    def generate_dependency_patch(
        self,
        package_name: str,
        current_version: str,
        fixed_version: str,
    ) -> Optional[str]:
        """Generate unified diff for upgrading a package version.

        Args:
            package_name: Name of the package to upgrade
            current_version: Current vulnerable version
            fixed_version: Safe version to upgrade to

        Returns:
            Unified diff string, or None if manifest not found
        """
        manifest_path = self._find_manifest_file(package_name)
        if not manifest_path:
            return None

        original_content = manifest_path.read_text()
        new_content = self._update_version_in_content(
            original_content, package_name, current_version, fixed_version
        )

        if not new_content or new_content == original_content:
            return None

        return self._generate_unified_diff(manifest_path, original_content, new_content)

    def _find_manifest_file(self, package_name: str) -> Optional[Path]:
        """Find the appropriate manifest file for the package."""
        # Check Python requirements.txt
        req_file = self.repo_dir / "requirements.txt"
        if req_file.exists():
            return req_file

        # Check Node.js package.json
        pkg_file = self.repo_dir / "package.json"
        if pkg_file.exists():
            return pkg_file

        # Check Go modules
        go_file = self.repo_dir / "go.mod"
        if go_file.exists():
            return go_file

        return None

    def _update_version_in_content(
        self,
        content: str,
        package_name: str,
        current_version: str,
        fixed_version: str,
    ) -> Optional[str]:
        """Update package version in manifest content."""
        lines = content.splitlines()
        new_lines = []
        updated = False

        for line in lines:
            if package_name in line and current_version in line:
                new_line = line.replace(current_version, fixed_version)
                new_lines.append(new_line)
                updated = True
            else:
                new_lines.append(line)

        return "\n".join(new_lines) if updated else None

    def _generate_unified_diff(
        self,
        file_path: Path,
        original_content: str,
        new_content: str,
    ) -> str:
        """Generate unified diff format string."""
        original_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )

        return "".join(diff)

    def supports_patch(self, finding_id: str) -> bool:
        """Check if finding type supports automated patch generation."""
        return finding_id.startswith("osv:")
