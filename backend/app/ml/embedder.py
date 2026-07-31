import logging
from typing import Any, Dict, List, Union
import numpy as np

from app.models import Finding

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"

try:
    from sentence_transformers import SentenceTransformer

    MODEL = SentenceTransformer(MODEL_NAME)
except Exception:
    MODEL = None
    logger.warning(
        "Failed to load sentence-transformers model: %s",
        MODEL_NAME,
        exc_info=True,
    )


def _extract_text(finding: Union[Finding, Dict[str, Any]]) -> str:
    """Safely extracts title and description from either a Pydantic Finding object or a raw dict."""
    if isinstance(finding, dict):
        title = finding.get("title", "")
        description = finding.get("description", "")
        return f"{title} {description}".strip()

    title = getattr(finding, "title", "")
    description = getattr(finding, "description", "")
    return f"{title} {description}".strip()


def embed_findings(findings: List[Union[Finding, Dict[str, Any]]]) -> np.ndarray:
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
