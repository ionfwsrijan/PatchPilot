from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import List

from ..models import Finding, Location
from ..utils.ml_features import extract_features

UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SVG_PATH_REGEX = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9\s,\.\-]+$")
HEX_COLOR_REGEX = re.compile(r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
STRING_LITERAL_REGEX = re.compile(r"(['\"])(.*?)\1")


def calculate_shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    frequencies = Counter(text)
    total_chars = len(text)
    entropy = 0.0
    for count in frequencies.values():
        probability = count / total_chars
        entropy -= probability * math.log2(probability)
    return entropy


def is_allowlisted(token: str) -> bool:
    if len(token) < 12:
        return True
    if UUID_REGEX.match(token):
        return True
    if HEX_COLOR_REGEX.match(token):
        return True
    if "data:image/" in token:
        return True
    if SVG_PATH_REGEX.match(token) and any(c in token for c in "mMvVlLcCzZ"):
        return True
    return False


def run_entropy(repo_dir: Path) -> List[Finding]:
    findings: List[Finding] = []
    ignored_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".svg",
        ".zip",
        ".tar",
        ".gz",
        ".mp4",
        ".pdf",
        ".woff",
        ".woff2",
        ".eot",
        ".ttf",
    }

    for file_path in repo_dir.rglob("*"):
        if (
            not file_path.is_file()
            or file_path.suffix.lower() in ignored_extensions
            or ".git" in file_path.parts
        ):
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        lines = content.splitlines()
        for line_idx, line in enumerate(lines, start=1):
            for match in STRING_LITERAL_REGEX.finditer(line):
                token = match.group(2)

                if is_allowlisted(token):
                    continue

                entropy_score = calculate_shannon_entropy(token)
                if entropy_score > 4.0:
                    relative_path = str(file_path.relative_to(repo_dir))
                    finding_id = (
                        f"entropy:high-entropy-string:{relative_path}:{line_idx}"
                    )
                    severity = "HIGH"

                    raw_data_for_extractor = {
                        "id": finding_id,
                        "severity": severity,
                        "location": {"path": relative_path},
                        "metadata": {"cwe_category": "CWE-798"},
                    }

                    ml_features = extract_features(
                        raw_data_for_extractor, scanner_name="entropy"
                    )

                    findings.append(
                        Finding(
                            id=finding_id,
                            category="secret",
                            severity=severity,
                            title="High Entropy String Detected",
                            description=f"Potential hardcoded secret or token discovered (Entropy: {entropy_score:.2f})",
                            location=Location(
                                path=relative_path,
                                start_line=line_idx,
                                end_line=line_idx,
                            ),
                            metadata={
                                "engine": "entropy",
                                "entropy_score": entropy_score,
                                "token_preview": token[:10],
                            },
                            features=ml_features,
                        )
                    )
    return findings
