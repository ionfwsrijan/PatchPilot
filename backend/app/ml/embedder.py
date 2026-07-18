import logging

import numpy as np

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

MODEL = None


def _get_model():
    global MODEL

    if SentenceTransformer is None:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Install it using: pip install sentence-transformers"
        )

    if MODEL is None:
        logger.info("Loading sentence-transformers model for deduplication...")
        MODEL = SentenceTransformer("all-MiniLM-L6-v2")

    return MODEL


def embed_findings(findings: list[dict]) -> np.ndarray:
    """
    Convert findings into embeddings.

    Each finding is converted to:
    "{rule_id} {message} {file_path}"

    Returns:
        np.ndarray of shape (n, 384)
    """
    texts = [
        f"{getattr(finding, 'title', '')} {getattr(finding, 'description', '')}"
        for finding in findings
    ]

    return _get_model().encode(texts, convert_to_numpy=True)
