import argparse
import os
import sqlite3

import joblib
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_DB_PATH = os.path.join(BACKEND_DIR, "patchpilot.db")
MODEL_DIR = os.path.join(BACKEND_DIR, "app", "ml")
MODEL_PATH = os.path.join(MODEL_DIR, "fp_classifier.pkl")


def get_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def load_data(db_path: str, min_samples: int) -> pd.DataFrame:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    query = """
        SELECT rule_id, message, file_path, false_positive 
        FROM findings 
        WHERE false_positive IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df["false_positive"] = (
        df["false_positive"]
        .map({True: 1, False: 0, "1": 1, "0": 0, "true": 1, "false": 0})
        .fillna(0)
    )

    if len(df) < min_samples:
        raise ValueError(f"Insufficient data: need {min_samples}, found {len(df)}")

    class_counts = df["false_positive"].value_counts()
    if len(class_counts) < 2 or class_counts.min() < 2:
        raise ValueError(
            f"Class imbalance: requires at least 2 examples of both True and False Positives.\nCurrent distribution:\n{class_counts}"
        )

    print(f"✅ Loaded {len(df)} labeled findings from the database.")
    return df


def generate_embeddings(texts: list[str], batch_size: int = 16) -> torch.Tensor:
    device = get_device()
    print(f"⚙️ Loading CodeBERT model on {device}...")

    tokenizer = AutoTokenizer.from_pretrained("microsoft/codebert-base")
    model = AutoModel.from_pretrained("microsoft/codebert-base").to(device)
    model.eval()

    all_embeddings = []

    with torch.no_grad():
        for i in tqdm(range(0, len(texts), batch_size), desc="Generating Embeddings"):
            batch_texts = texts[i : i + batch_size]

            inputs = tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(device)

            outputs = model(**inputs)

            cls_embeddings = outputs.last_hidden_state[:, 0, :]
            all_embeddings.append(cls_embeddings.cpu())

    return torch.cat(all_embeddings, dim=0)


def main():
    parser = argparse.ArgumentParser(description="Train the False Positive Classifier")
    parser.add_argument("--min-samples", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--db-path",
        type=str,
        default=DEFAULT_DB_PATH,
        help="Path to the SQLite database",
    )
    args = parser.parse_args()

    try:
        df = load_data(args.db_path, args.min_samples)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Error: {e}")
        raise SystemExit(1)

    df["rule_id"] = df["rule_id"].fillna("unknown_rule")
    df["message"] = df["message"].fillna("")
    df["file_path"] = df["file_path"].fillna("")

    texts = (df["rule_id"] + " " + df["message"] + " " + df["file_path"]).tolist()
    labels = df["false_positive"].astype(int).values

    X = generate_embeddings(texts, batch_size=args.batch_size)
    y = labels

    X_train, X_test, y_train, y_test = train_test_split(
        X.numpy(), y, test_size=0.2, random_state=42, stratify=y
    )

    print("📈 Training Logistic Regression classifier...")
    classifier = LogisticRegression(max_iter=1000, class_weight="balanced")
    classifier.fit(X_train, y_train)

    y_pred = classifier.predict(X_test)
    print("\n📊 Classification Report:")
    print(
        classification_report(
            y_test, y_pred, target_names=["True Positive (0)", "False Positive (1)"]
        )
    )

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(classifier, MODEL_PATH)
    print(f"🚀 Model successfully trained and saved to: {MODEL_PATH}")


if __name__ == "__main__":
    main()
