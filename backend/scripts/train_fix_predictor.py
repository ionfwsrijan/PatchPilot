import argparse
import os
import sqlite3
import sys
import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train a Logistic Regression model to predict fix verification success."
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="backend/data/patchpilot.db",
        help="Path to the SQLite database containing fix telemetry/history.",
    )
    parser.add_argument(
        "--csv-path",
        type=str,
        default=None,
        help="Optional path to a CSV dataset instead of SQLite database.",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="backend/app/ml/models/fix_predictor.pkl",
        help="Path where the trained fix predictor model (.pkl) will be saved.",
    )
    return parser.parse_args()


def load_data(db_path: str, csv_path: str = None) -> pd.DataFrame:
    """Loads dataset from either a CSV file or SQLite database."""
    if csv_path and os.path.exists(csv_path):
        print(f"Loading data from CSV: {csv_path}")
        return pd.read_csv(csv_path)

    if os.path.exists(db_path):
        print(f"Loading data from SQLite DB: {db_path}")
        conn = sqlite3.connect(db_path)
        try:
            df = pd.read_sql_query("SELECT * FROM fix_telemetry", conn)
            return df
        except Exception as e:
            print(f"Error querying 'fix_telemetry' table: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    print("No valid database or CSV found.")
    return pd.DataFrame()


def train():
    args = parse_args()
    df = load_data(args.db_path, args.csv_path)

    # Acceptance Criteria: Requires >= 100 examples; exits with message if fewer
    if len(df) < 100:
        print(
            f"Insufficient data to train fix_predictor model. Required: >= 100 examples, Found: {len(df)}. Exiting."
        )
        sys.exit(0)

    # Ensure target column exists
    target_col = "success" if "success" in df.columns else "verified"
    if target_col not in df.columns:
        print(f"Target column ('success' or 'verified') not found in dataset. Exiting.")
        sys.exit(1)

    # Separate target and features
    y = df[target_col].astype(int)
    feature_df = df.drop(columns=[target_col, "id", "finding_id", "job_id"], errors="ignore")

    # One-hot encode categorical features
    X = pd.get_dummies(feature_df, drop_first=True)

    # 80/20 train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if len(y.unique()) > 1 else None
    )

    # Train Logistic Regression model
    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)

    # Evaluate model
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else y_pred

    accuracy = accuracy_score(y_test, y_pred)
    try:
        roc_auc = roc_auc_score(y_test, y_proba)
    except ValueError:
        roc_auc = 0.5  # Fallback if only one class exists in test split

    # Acceptance Criteria: Prints ROC-AUC score to stdout
    print(f"Model Evaluation Results:")
    print(f"Accuracy: {accuracy:.4f}")
    print(f"ROC-AUC:  {roc_auc:.4f}")

    # Ensure output directory exists and save model
    os.makedirs(os.path.dirname(args.output_path), exist_ok=True)
    joblib.dump(model, args.output_path)
    print(f"Saved trained fix predictor model to: {args.output_path}")


if __name__ == "__main__":
    train()