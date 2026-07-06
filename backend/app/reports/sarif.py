"""SARIF (Static Analysis Results Interchange Format) export module.

Generates SARIF 2.1.0 compliant output for integration with:
- GitHub Advanced Security
- SonarQube
- DefectDojo
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import Finding


SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def _severity_to_sarif_level(severity: str) -> str:
    """Map PatchPilot severity to SARIF level.

    SARIF levels: "error", "warning", "note", "none"
    """
    mapping = {
        "CRITICAL": "error",
        "HIGH": "error",
        "MEDIUM": "warning",
        "LOW": "warning",
        "INFO": "note",
    }
    return mapping.get(severity.upper(), "warning")


def _tool_to_sarif_rule(tool_name: str) -> Dict[str, Any]:
    """Map scanner tool name to SARIF rule properties."""
    tool_info = {
        "semgrep": {
            "id": "SEMGREP",
            "name": "Semgrep",
            "short_description": "Static analysis for security patterns",
            "full_description": "Semgrep findings from pattern matching",
            "default_level": "error",
        },
        "osv": {
            "id": "OSV",
            "name": "OSV",
            "short_description": "Open Source Vulnerabilities database",
            "full_description": "Dependency vulnerability findings from OSV",
            "default_level": "error",
        },
        "gitleaks": {
            "id": "GITLEAKS",
            "name": "Gitleaks",
            "short_description": "Secret scanning in repositories",
            "full_description": "Secret detection findings from Gitleaks",
            "default_level": "error",
        },
    }
    return tool_info.get(tool_name.lower(), {
        "id": tool_name.upper(),
        "name": tool_name,
        "short_description": f"{tool_name} findings",
        "full_description": f"Findings from {tool_name}",
        "default_level": "warning",
    })


def finding_to_sarif_result(finding: Finding, tool_driver: str = "PatchPilot") -> Dict[str, Any]:
    """Convert a PatchPilot Finding to a SARIF Result object."""
    result: Dict[str, Any] = {
        "id": finding.id,
        "rule_id": finding.metadata.get("engine", "unknown").upper(),
        "level": _severity_to_sarif_level(finding.severity),
        "message": {
            "text": finding.title,
        },
        "properties": {
            "category": finding.category,
            "ml_score": finding.ml_score,
        },
    }

    # Add location if available
    if finding.location and finding.location.path:
        result["locations"] = [{
            "physical_location": {
                "artifact_location": {
                    "uri": finding.location.path,
                    "uri_base_id": "%SRCROOT%",
                },
            }
        }]

        # Add line information
        if finding.location.start_line:
            result["locations"][0]["physical_location"]["region"] = {
                "start_line": finding.location.start_line,
            }
            if finding.location.end_line and finding.location.end_line != finding.location.start_line:
                result["locations"][0]["physical_location"]["region"]["end_line"] = finding.location.end_line

    # Add description as markdown with code context
    if finding.description:
        result["message"] = {
            "text": finding.title,
            "markdown": f"**{finding.title}**\n\n{finding.description}",
        }

    return result


def generate_sarif_report(
    findings: List[Finding],
    project_name: str = "PatchPilot Scan",
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a complete SARIF 2.1.0 report from PatchPilot findings.

    Args:
        findings: List of Finding objects to export
        project_name: Name of the scanned project
        run_id: Optional run identifier

    Returns:
        SARIF 2.1.0 compliant JSON object
    """
    if run_id is None:
        run_id = str(uuid.uuid4())

    # Collect unique tools from findings
    tools_seen: set = set()
    rules: List[Dict[str, Any]] = []

    for finding in findings:
        tool = finding.metadata.get("engine", "unknown")
        if tool.lower() not in tools_seen:
            tools_seen.add(tool.lower())
            rule_info = _tool_to_sarif_rule(tool)
            rules.append({
                "id": rule_info["id"],
                "name": rule_info["name"],
                "short_description": {
                    "text": rule_info["short_description"],
                },
                "full_description": {
                    "text": rule_info["full_description"],
                },
                "properties": {
                    "tags": ["security", "vulnerability"],
                },
            })

    # Convert findings to SARIF results
    sarif_results = [finding_to_sarif_result(f) for f in findings]

    # Build the complete SARIF document
    sarif_report = {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {
                "driver": {
                    "name": "PatchPilot",
                    "full_name": "PatchPilot Security Engine",
                    "version": "1.0.0",
                    "information_uri": "https://github.com/ionfwsrijan/PatchPilot",
                    "rules": rules,
                }
            },
            "invocations": [{
                "execution_successful": True,
                "end_time_utc": datetime.now(timezone.utc).isoformat(),
            }],
            "results": sarif_results,
            "properties": {
                "project_name": project_name,
                "run_id": run_id,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "total_findings": len(findings),
                "metrics": {
                    "critical": len([f for f in findings if f.severity.upper() == "CRITICAL"]),
                    "high": len([f for f in findings if f.severity.upper() == "HIGH"]),
                    "medium": len([f for f in findings if f.severity.upper() == "MEDIUM"]),
                    "low": len([f for f in findings if f.severity.upper() == "LOW"]),
                    "info": len([f for f in findings if f.severity.upper() == "INFO"]),
                },
            },
        }],
    }

    return sarif_report


def save_sarif_report(sarif_report: Dict[str, Any], output_path: str) -> None:
    """Save SARIF report to a file.

    Args:
        sarif_report: The SARIF report dictionary
        output_path: Path to save the .sarif file
    """
    Path(output_path).write_text(
        json.dumps(sarif_report, indent=2),
        encoding="utf-8"
    )
