from collections import defaultdict

from sklearn.cluster import DBSCAN


def get_model():
    return None


try:
    from app.ml.embedder import embed_findings

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except Exception:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

    def embed_findings(findings):
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Install it using: pip install sentence-transformers"
        )


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
