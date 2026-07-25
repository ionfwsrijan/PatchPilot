from pathlib import Path

import joblib
import pandas as pd

from app.utils.ml_features import extract_features

MODEL_PATH = Path(__file__).parent / "models" / "ranker.pkl"


def load_ranker():
    if not MODEL_PATH.exists():
        print("Ranker not found, using default sort")
        return None

    try:
        model = joblib.load(MODEL_PATH)
        print("Ranker loaded")
        return model

    except Exception as exc:
        print(f"Failed to load ranker: {exc}")
        print("Using default sort")
        return None


def scoring_function(findings, model):
    if model is None:
        return findings

    ml_features = []

    for finding in findings:
        raw_features = {
            "id": finding.id,
            "severity": finding.severity,
            "location": {"path": finding.location.path if finding.location else ""},
            "metadata": {
                "cwe_category": finding.metadata.get(
                    "cwe_category",
                    "unknown",
                )
            },
        }

        features = extract_features(
            raw_features,
            scanner_name=finding.metadata.get(
                "engine",
                "unknown",
            ),
        )
        features.pop("raw_severity", None)
        ml_features.append(features)

    X = pd.DataFrame(ml_features)
    scores = model.predict_proba(X).max(axis=1)

    for finding, score in zip(findings, scores):
        finding.ml_score = float(score)

    return findings
