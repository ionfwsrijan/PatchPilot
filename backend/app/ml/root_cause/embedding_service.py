from __future__ import annotations

import joblib
from pathlib import Path
from typing import Any

# Lazy loaded SentenceTransformer model
_MODEL: Any = None

MODEL_PATH = Path(__file__).parent / "models" / "all-MiniLM-L6-v2"

def load_model() -> Any:
    """Load the sentence‑transformers model lazily.

    The model files are expected to be located at ``backend/app/ml/root_cause/models/all-MiniLM-L6-v2``.
    If the directory does not exist, the function will raise a clear ``FileNotFoundError``.
    """
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Embedding model not found at {MODEL_PATH}. Ensure the model is downloaded.")
    try:
        _MODEL = joblib.load(MODEL_PATH / "model.joblib")
    except Exception as exc:
        raise RuntimeError(f"Failed to load embedding model: {exc}")
    return _MODEL

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return embeddings for a list of strings.

    Parameters
    ----------
    texts: list[str]
        Texts to embed.
    Returns
    -------
    list[list[float]]
        Embedding vectors.
    """
    model = load_model()
    # The model follows the SentenceTransformer interface with ``encode``.
    return model.encode(texts, show_progress_bar=False).tolist()
