from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.utils.ml_features import extract_features  # noqa: E402

SEVERITY_MAP = {
    "INFO": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}

MIN_SAMPLES = 50


def load_findings(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        # Check if features column exists in the schema
        cursor = conn.execute("PRAGMA table_info(findings)")
        columns = {row[1] for row in cursor.fetchall()}
        select_features = ", features" if "features" in columns else ""

        df = pd.read_sql_query(
            f"""
            SELECT rule_id, severity, category, file_path,
                   line_number, cwe, scanner{select_features}
            FROM findings
            """,
            conn,
        )
    except Exception as e:
        raise SystemExit(
            f"Failed to load findings from '{db_path}'. "
            "Verify the database path and that scans have been run."
        ) from e
    conn.close()
    return df


def reconstruct_features(row: pd.Series) -> dict:
    file_path = row["file_path"]

    if pd.isna(file_path):
        file_path = ""

    cwe = row["cwe"]

    if pd.isna(cwe):
        cwe = "unknown"

    raw_finding = {
        "id": row["rule_id"],
        "severity": row["severity"],
        "location": {"path": str(file_path)},
        "metadata": {"cwe_category": str(cwe)},
    }

    return extract_features(
        raw_finding,
        scanner_name=str(row["scanner"]) if pd.notna(row["scanner"]) else "unknown",
    )


def build_feature_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    feature_rows = []

    for _, row in df.iterrows():
        if "features" in df.columns and pd.notna(row.get("features")):
            try:
                features = json.loads(row["features"])
            except Exception:
                features = reconstruct_features(row)
        else:
            features = reconstruct_features(row)

        feature_rows.append(features)

    feature_df = pd.DataFrame(feature_rows)

    for col in [
        "cwe_category",
        "file_extension",
        "scanner",
        "rule_id_prefix",
    ]:
        feature_df[col] = feature_df[col].fillna("unknown").astype(str)

    return feature_df


def prepare_dataset(df: pd.DataFrame):
    feature_df = build_feature_dataframe(df)
    y = df["severity"].str.upper().map(SEVERITY_MAP)

    unrecognised = y.isna()
    if unrecognised.any():
        bad = df.loc[unrecognised, "severity"].unique().tolist()
        print(
            f"WARNING: dropping {unrecognised.sum()} rows with unknown severity: {bad}"
        )
        feature_df = feature_df[~unrecognised]
        y = y[~unrecognised]

    # Drop raw_severity - it leaks the target label
    feature_df = feature_df.drop(columns=["raw_severity"], errors="ignore")
    feature_df["is_test_file"] = feature_df["is_test_file"].astype(int)

    return feature_df, y.astype(int)


def train_model(X: pd.DataFrame, y: pd.Series, test_size: float = 0.2) -> Pipeline:
    categorical_cols = X.select_dtypes(include=["object", "string"]).columns.tolist()

    numeric_cols = [c for c in X.columns if c not in categorical_cols]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                categorical_cols,
            ),
            ("num", "passthrough", numeric_cols),
        ]
    )

    pipeline = Pipeline(
        [
            ("preprocessor", preprocessor),
            ("model", GradientBoostingClassifier(random_state=42)),
        ]
    )

    # Skip stratify if any class has fewer than 2 samples
    stratify = y if y.value_counts().min() >= 2 else None
    if stratify is None:
        print("WARNING: some classes have <2 samples — skipping stratified split.")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=stratify
    )

    pipeline.fit(X_train, y_train)

    label_names = {v: k for k, v in SEVERITY_MAP.items()}
    present_labels = sorted(y_test.unique())
    target_names = [label_names[i] for i in present_labels]

    print("\nClassification Report")
    print()
    print(
        classification_report(
            y_test,
            pipeline.predict(X_test),
            labels=present_labels,
            target_names=target_names,
            digits=3,
            zero_division=0,
        )
    )

    return pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Train PatchPilot severity ranker.",
        epilog=(
            "Examples:\n"
            "  python scripts/train_ranker.py --db ../patchpilot.db\n"
            "  python scripts/train_ranker.py --db ../patchpilot.db"
            " --output app/ml/models/ranker.pkl\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", required=True, help="Path to patchpilot.db.")
    parser.add_argument(
        "--output",
        default="app/ml/models/ranker.pkl",
        help="Output path for ranker.pkl (default: app/ml/models/ranker.pkl).",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        metavar="FLOAT",
        help="Test split fraction (default: 0.2).",
    )
    args = parser.parse_args()

    df = load_findings(args.db)

    if len(df) < MIN_SAMPLES:
        raise SystemExit(
            f"ERROR: need ≥{MIN_SAMPLES} findings to train, found {len(df)}. "
            "Run more scans and retry."
        )

    X, y = prepare_dataset(df)
    pipeline = train_model(X, y, test_size=args.test_size)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(pipeline, output_path)
    print(f"\nSaved model to: {output_path}")


if __name__ == "__main__":
    main()
