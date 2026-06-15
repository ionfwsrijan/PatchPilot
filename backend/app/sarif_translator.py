import json
from typing import List, Dict, Any

class SarifTranslator:
    def __init__(self, triage_elements: List[Dict[str, Any]]):
        """
        Initializes the translator with PatchPilot's internal triage JSON array elements.
        """
        self.triage_elements = triage_elements

    def _map_severity(self, internal_severity: str) -> str:
        """
        Maps internal tool severities to official SARIF levels:
        'error', 'warning', 'note', or 'none'.
        """
        severity_upper = str(internal_severity).upper()
        if severity_upper in ["ERROR", "CRITICAL", "HIGH"]:
            return "error"
        elif severity_upper in ["WARNING", "MEDIUM"]:
            return "warning"
        elif severity_upper in ["INFO", "NOTE", "LOW"]:
            return "note"
        else:
            return "none"

    def _translate_result(self, element: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translates a single PatchPilot internal element into a SARIF result item.
        """
        rule_id = element.get("check_id", "patchpilot-generic-rule")
        extra_data = element.get("extra", {})
        message_text = extra_data.get("message", "No message provided by tool.")
        raw_severity = extra_data.get("severity", "WARNING")
        
        sarif_result = {
            "ruleId": rule_id,
            "message": {
                "text": message_text
            },
            "level": self._map_severity(raw_severity),
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": element.get("path", "unknown_file")
                        },
                        "region": {
                            "startLine": element.get("start", {}).get("line", 1),
                            "startColumn": element.get("start", {}).get("col", 1),
                            "endLine": element.get("end", {}).get("line", 1),
                            "endColumn": element.get("end", {}).get("col", 1)
                        }
                    }
                }
            ]
        }
        return sarif_result

    def generate_payload(self) -> Dict[str, Any]:
        """
        Executes the pipeline and returns the full schema-compliant SARIF payload.
        """
        sarif_results = [self._translate_result(item) for item in self.triage_elements]
        
        payload = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "PatchPilot Engine"
                        }
                    },
                    "results": sarif_results
                }
            ]
        }
        return payload