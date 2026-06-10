"""Parse OSV scanner findings to extract package and version information."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class OSVParser:
    """Parse OSV scanner output to extract vulnerability details."""

    def __init__(self, repo_dir: Path):
        """Initialize with repository directory."""
        self.repo_dir = repo_dir
        self.osv_output_path = repo_dir / "osv_output.json"

    def get_package_info(self, finding_id: str) -> Optional[Tuple[str, str, str]]:
        """Get package name, current version, and fixed version for a finding.

        Args:
            finding_id: OSV finding ID (e.g., "osv:PYSEC-2024-123")

        Returns:
            Tuple of (package_name, current_version, fixed_version) or None
        """
        if not self.osv_output_path.exists():
            raise FileNotFoundError(
                f"OSV scan results not found at {self.osv_output_path}. "
                "Run a scan first before requesting a fix."
            )
        try:
            data = json.loads(self.osv_output_path.read_text())
            return self._extract_from_osv_data(data, finding_id)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid OSV output JSON: {e}") from e
        except KeyError as e:
            raise ValueError(f"Unexpected OSV output format, missing key: {e}") from e

    def _extract_from_osv_data(
        self, data: Dict, finding_id: str
    ) -> Optional[Tuple[str, str, str]]:
        """Extract package info from actual OSV JSON output."""
        for vuln in data.get("vulns", []):
            if vuln.get("id") == finding_id.replace("osv:", ""):
                package = self._get_package_name(vuln)
                current_version = self._get_current_version(vuln)
                fixed_version = self._get_fixed_version(vuln)
                if package and fixed_version:
                    return (package, current_version or "unknown", fixed_version)
        return None

    def _get_package_name(self, vuln: Dict) -> Optional[str]:
        """Extract package name from OSV vulnerability data."""
        affected = vuln.get("affected", [])
        if affected:
            for pkg in affected:
                if "package" in pkg:
                    return pkg["package"].get("name")
        return None

    def _get_current_version(self, vuln: Dict) -> Optional[str]:
        """Extract current version from OSV data."""
        affected = vuln.get("affected", [])
        if affected:
            for pkg in affected:
                versions = pkg.get("versions", [])
                if versions:
                    return versions[0]
        return None

    def _get_fixed_version(self, vuln: Dict) -> Optional[str]:
        """Extract fixed version from OSV data."""
        affected = vuln.get("affected", [])
        if affected:
            for pkg in affected:
                ranges = pkg.get("ranges", [])
                for r in ranges:
                    events = r.get("events", [])
                    for event in events:
                        if "fixed" in event:
                            return event["fixed"]
        return None
