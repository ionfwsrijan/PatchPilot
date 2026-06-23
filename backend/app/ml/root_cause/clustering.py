from __future__ import annotations

from typing import List, Tuple
import numpy as np
from sklearn.cluster import AgglomerativeClustering

from .embedding_service import embed_texts
from .models import RootCauseFinding, RootCauseGroup, RootCauseResponse


def _average_pairwise_cosine(embeddings: np.ndarray) -> float:
    """Calculate average pairwise cosine similarity for a set of vectors.

    Parameters
    ----------
    embeddings: np.ndarray
        2‑D array where each row is an embedding.
    Returns
    -------
    float
        Average cosine similarity (0‑1).
    """
    if embeddings.shape[0] <= 1:
        return 1.0
    # Normalize vectors
    normed = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    similarity_matrix = np.dot(normed, normed.T)
    # Exclude self‑similarities
    n = embeddings.shape[0]
    sum_sim = similarity_matrix.sum() - n  # remove diagonal
    count = n * (n - 1)
    return float(sum_sim / count)


def cluster_findings(findings: List[RootCauseFinding], distance_threshold: float = 0.3) -> List[RootCauseGroup]:
    """Cluster findings using Agglomerative Clustering with cosine distance.

    Parameters
    ----------
    findings: List[RootCauseFinding]
        List of findings to cluster.
    distance_threshold: float
        The distance threshold for forming clusters. Smaller = stricter.
    Returns
    -------
    List[RootCauseGroup]
    """
    if not findings:
        return []

    # Prepare texts for embedding
    texts = [f"{f.title}. {f.description or ''}" for f in findings]
    embeddings = np.array(embed_texts(texts))

    # Agglomerative clustering with cosine metric
    clustering = AgglomerativeClustering(
        n_clusters=None,
        affinity="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
    )
    labels = clustering.fit_predict(embeddings)

    groups: dict[int, List[RootCauseFinding]] = {}
    for label, finding in zip(labels, findings):
        groups.setdefault(label, []).append(finding)

    result: List[RootCauseGroup] = []
    for label, group_findings in groups.items():
        group_embeddings = embeddings[labels == label]
        confidence = _average_pairwise_cosine(group_embeddings)
        root_cause_desc = _infer_root_cause(group_findings)
        result.append(
            RootCauseGroup(
                id=str(uuid.uuid4()),
                job_id="",
                root_cause=root_cause_desc,
                confidence=confidence,
                findings_count=len(group_findings),
                findings=group_findings,
            )
        )
    return result


def _infer_root_cause(findings: List[RootCauseFinding]) -> str:
    """Very naive heuristic to infer a root‑cause description.
    For now we concatenate the most common words from titles.
    """
    from collections import Counter
    tokens = []
    for f in findings:
        tokens.extend(f.title.split())
    if not tokens:
        return "Generic root cause"
    most_common = Counter(tokens).most_common(3)
    return " ".join([word for word, _ in most_common])
