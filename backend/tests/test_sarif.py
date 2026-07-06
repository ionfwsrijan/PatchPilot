"""Tests for SARIF export module."""

import pytest
from app.models import Finding, Location
from app.reports.sarif import (
    generate_sarif_report,
    finding_to_sarif_result,
    _severity_to_sarif_level,
    _tool_to_sarif_rule,
    SARIF_VERSION,
)


class TestSeverityMapping:
    def test_critical_maps_to_error(self):
        assert _severity_to_sarif_level("CRITICAL") == "error"
        assert _severity_to_sarif_level("critical") == "error"

    def test_high_maps_to_error(self):
        assert _severity_to_sarif_level("HIGH") == "error"

    def test_medium_maps_to_warning(self):
        assert _severity_to_sarif_level("MEDIUM") == "warning"

    def test_low_maps_to_warning(self):
        assert _severity_to_sarif_level("LOW") == "warning"

    def test_info_maps_to_note(self):
        assert _severity_to_sarif_level("INFO") == "note"


class TestToolMapping:
    def test_semgrep_rule(self):
        rule = _tool_to_sarif_rule("semgrep")
        assert rule["id"] == "SEMGREP"
        assert rule["name"] == "Semgrep"

    def test_osv_rule(self):
        rule = _tool_to_sarif_rule("osv")
        assert rule["id"] == "OSV"
        assert rule["name"] == "OSV"

    def test_gitleaks_rule(self):
        rule = _tool_to_sarif_rule("gitleaks")
        assert rule["id"] == "GITLEAKS"
        assert rule["name"] == "Gitleaks"

    def test_unknown_tool(self):
        rule = _tool_to_sarif_rule("custom-tool")
        assert rule["id"] == "CUSTOM-TOOL"
        assert rule["name"] == "custom-tool"


class TestFindingConversion:
    def test_finding_with_location(self):
        finding = Finding(
            id="test-1",
            title="SQL Injection vulnerability",
            severity="HIGH",
            category="Security",
            location=Location(path="src/app.py", start_line=42, end_line=45),
            description="Potential SQL injection in user input",
        )
        result = finding_to_sarif_result(finding)
        assert result["id"] == "test-1"
        assert result["level"] == "error"
        assert result["message"]["text"] == "SQL Injection vulnerability"
        assert len(result["locations"]) == 1
        assert result["locations"][0]["physical_location"]["artifact_location"]["uri"] == "src/app.py"

    def test_finding_without_location(self):
        finding = Finding(
            id="test-2",
            title="Missing dependency",
            severity="MEDIUM",
            category="Dependency",
        )
        result = finding_to_sarif_result(finding)
        assert result["id"] == "test-2"
        assert result["level"] == "warning"
        assert "locations" not in result


class TestSarifReportGeneration:
    def test_empty_report(self):
        report = generate_sarif_report([])
        assert report["version"] == SARIF_VERSION
        assert len(report["runs"]) == 1
        assert report["runs"][0]["tool"]["driver"]["name"] == "PatchPilot"
        assert len(report["runs"][0]["results"]) == 0

    def test_report_with_findings(self):
        findings = [
            Finding(
                id="finding-1",
                title="XSS Vulnerability",
                severity="CRITICAL",
                category="Security",
                location=Location(path="index.html", start_line=10),
                metadata={"engine": "semgrep"},
            ),
            Finding(
                id="finding-2",
                title="Outdated dependency",
                severity="MEDIUM",
                category="Dependency",
                metadata={"engine": "osv"},
            ),
        ]
        report = generate_sarif_report(findings, project_name="Test Project")

        assert report["version"] == SARIF_VERSION
        run = report["runs"][0]
        assert run["tool"]["driver"]["name"] == "PatchPilot"
        assert len(run["results"]) == 2
        assert run["properties"]["project_name"] == "Test Project"
        assert run["properties"]["metrics"]["critical"] == 1
        assert run["properties"]["metrics"]["medium"] == 1

    def test_report_includes_rules(self):
        findings = [
            Finding(
                id="finding-1",
                title="Test",
                severity="HIGH",
                category="Test",
                metadata={"engine": "semgrep"},
            ),
        ]
        report = generate_sarif_report(findings)
        rules = report["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 1
        assert rules[0]["id"] == "SEMGREP"
