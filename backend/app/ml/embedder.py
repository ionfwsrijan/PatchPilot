import numpy as np

try:
    from sentence_transformers import SentenceTransformer

    MODEL = SentenceTransformer("all-MiniLM-L6-v2")
except ImportError:
    MODEL = None


def embed_findings(findings: list[dict]) -> np.ndarray:
    """
    Convert findings into embeddings.

    Each finding is converted to:
    "{rule_id} {message} {file_path}"

    Returns:
        np.ndarray of shape (n, 384)
    """
    if MODEL is None:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Install it using: pip install sentence-transformers"
        )

    texts = [
        f"{getattr(finding, 'title', '')} {getattr(finding, 'description', '')}"
        for finding in findings
    ]

    return MODEL.encode(texts, convert_to_numpy=True)
