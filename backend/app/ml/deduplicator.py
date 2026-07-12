from collections import defaultdict

from sklearn.cluster import DBSCAN


def get_model():
    return None


# Import embedder in a way that keeps the module importable during tests.
# Tests may patch SENTENCE_TRANSFORMERS_AVAILABLE and/or embed functions.
try:
    from app.ml.embedder import embed_findings as _embed_findings
except Exception:  # pragma: no cover
    _embed_findings = None

SENTENCE_TRANSFORMERS_AVAILABLE = _embed_findings is not None


def embed_findings(findings):
    """Wrapper so tests can patch deduplicator.embed_findings if needed."""
    if _embed_findings is None:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Install it using: pip install sentence-transformers"
        )
    return _embed_findings(findings)


def deduplicate(
    findings: list[dict],
    epsilon: float = 0.15,
) -> list[dict]:
    """
    Group similar findings using DBSCAN and return
    representative findings with duplicate metadata.
    """
    if not findings:
        return []

    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        return findings

    embeddings = embed_findings(findings)

    clustering = DBSCAN(
        eps=epsilon,
        min_samples=2,
        metric="cosine",
    )

    labels = clustering.fit_predict(embeddings)

    results = []
    clusters = defaultdict(list)

    for idx, label in enumerate(labels):
        clusters[label].append(findings[idx])

    for label, cluster_findings in clusters.items():
        if label == -1:
            for finding in cluster_findings:
                # finding["duplicate_count"] = 0
                # finding["related_files"] = []
                results.append(finding)
            continue

        representative = cluster_findings[0]

        # representative["duplicate_count"] = len(cluster_findings)
        # representative["related_files"] = related_files

        results.append(representative)

    return results
