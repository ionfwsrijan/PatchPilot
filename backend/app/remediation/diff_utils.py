"""Utility functions for diff generation and formatting."""

import difflib
from pathlib import Path
from typing import List, Optional


def generate_unified_diff(
    file_path: Path,
    original_content: str,
    new_content: str,
    context_lines: int = 3,
) -> str:
    """Generate unified diff between original and new content.

    Args:
        file_path: Path to the file being changed
        original_content: Original file content
        new_content: Modified file content
        context_lines: Number of context lines (default: 3)

    Returns:
        Unified diff string
    """
    original_lines = original_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines,
    )

    return "".join(diff)


def parse_osv_finding_id(finding_id: str) -> Optional[dict]:
    """Parse OSV finding ID to extract package info.

    Example: "osv:PYSEC-2024-123" -> {"ecosystem": "PyPI", "id": "PYSEC-2024-123"}
    """
    if not finding_id.startswith("osv:"):
        return None

    parts = finding_id.split(":", 1)
    if len(parts) != 2:
        return None

    return {
        "scanner": parts[0],
        "vuln_id": parts[1],
    }


def format_patch_summary(diff: str, max_lines: int = 10) -> str:
    """Format patch summary for display (first few lines)."""
    if not diff:
        return "No patch available"

    lines = diff.splitlines()
    preview = lines[:max_lines]
    summary = "\n".join(preview)

    if len(lines) > max_lines:
        summary += f"\n... and {len(lines) - max_lines} more lines"

    return summary
