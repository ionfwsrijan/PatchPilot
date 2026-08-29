import logging
import numpy as np

try:
    from sentence_transformers import SentenceTransformer

    MODEL = SentenceTransformer("all-MiniLM-L6-v2")
except Exception:
    MODEL = None
    logging.getLogger(__name__).warning(
        "Failed to load sentence-transformers model: all-MiniLM-L6-v2", 
        exc_info=True
    )


def _extract_text(finding) -> str:
    """Safely extracts title and description from either a Pydantic Finding object or a raw dict."""
    if isinstance(finding, dict):
        return f"{finding.get('title', '')} {finding.get('description', '')}".strip()
    return f"{getattr(finding, 'title', '')} {getattr(finding, 'description', '')}".strip()


def embed_findings(findings: list) -> np.ndarray:
    """
    Convert findings into embeddings.

    Each finding is converted to:
    "{title} {description}"

    Returns:
    		np.ndarray of shape (n, 384)
    """
    if MODEL is None:
        raise RuntimeError(
            "sentence-transformers is not installed or failed to initialize. "
            "Install it using: pip install sentence-transformers"
        )

    texts = [_extract_text(finding) for finding in findings]

    return MODEL.encode(texts, convert_to_numpy=True)
