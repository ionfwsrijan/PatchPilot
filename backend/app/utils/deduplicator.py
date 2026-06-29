import logging
from typing import List

from app.models import Finding

logger = logging.getLogger(__name__)

_MODEL = None


def get_model():
    """Lazily load and cache the SentenceTransformer model."""
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def deduplicate(findings: List[Finding], epsilon: float = 0.15) -> List[Finding]:
    """
    Deduplicates finding descriptions/messages using SentenceTransformer embeddings.

    Note: sentence-transformers is an optional dependency. If the package or its
    dependencies (e.g. numpy) are not available, or if loading/encoding fails,
    this function will gracefully log a warning and return the original list of
    findings as-is (fallback behavior) without performing deduplication.
    """
    if not findings:
        return findings

    # Check for sentence_transformers availability
    import importlib.util

    if importlib.util.find_spec("sentence_transformers") is None:
        logger.warning(
            "sentence-transformers is not available. Skipping deduplication."
        )
        return findings

    try:
        import numpy as np
    except ImportError:
        logger.warning("numpy is not available. Skipping deduplication.")
        return findings

    try:
        model = get_model()
        texts = [f.description if f.description else f.title for f in findings]
        embeddings = model.encode(texts, convert_to_numpy=True)

        if len(embeddings.shape) == 1:
            embeddings = np.expand_dims(embeddings, axis=0)

        # Normalize embeddings to compute cosine similarity using dot product
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized_embeddings = embeddings / norms

        keep = []
        for i in range(len(findings)):
            is_dup = False
            for j in keep:
                sim = np.dot(normalized_embeddings[i], normalized_embeddings[j])
                dist = 1.0 - sim
                if dist <= epsilon:
                    is_dup = True
                    break
            if not is_dup:
                keep.append(i)

        return [findings[idx] for idx in keep]

    except Exception as e:
        logger.error(f"Error during deduplication: {e}. Skipping deduplication.")
        return findings
