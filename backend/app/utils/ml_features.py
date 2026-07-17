# app/utils/ml_features.py
import re
from typing import Any, Dict


def extract_features(raw_finding: dict, scanner_name: str) -> Dict[str, Any]:
    """
    Extracts the 7 ML features required for the severity ranker.
    Expects a raw dictionary representation of a Finding before it is validated.
    """
    location = raw_finding.get("location") or {}
    file_path = location.get("path", "")
    metadata = raw_finding.get("metadata") or {}
    rule_id = raw_finding.get("id", "")

    file_extension = "none"
    if "." in file_path:
        file_extension = file_path[file_path.rfind(".") :]

    path_depth = file_path.count("/")

    path_lower = file_path.lower()
    is_test_file = "test" in path_lower or "spec" in path_lower

    rule_id_prefix = re.split(r"[-_]", rule_id)[0] if rule_id else "unknown"

    return {
        "cwe_category": metadata.get("cwe_category", "unknown"),
        "file_extension": file_extension,
        "path_depth": path_depth,
        "scanner": scanner_name,
        "raw_severity": raw_finding.get("severity", "unknown"),
        "is_test_file": is_test_file,
        "rule_id_prefix": rule_id_prefix,
    }
