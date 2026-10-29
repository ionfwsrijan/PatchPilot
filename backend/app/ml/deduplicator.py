
from collections import defaultdict

from sklearn.cluster import DBSCAN


def get_model():
    return None


# Keep this module importable when sentence-transformers is unavailable.
try:
    from app.ml.embedder import embed_findings as _embed_findings
except Exception:  # pragma: no cover
    _embed_findings = None


SENTENCE_TRANSFORMERS_AVAILABLE = _embed_findings is not None


def embed_findings(findings):
    """Wrapper so tests can patch deduplicator.embed_findings."""
    if _embed_findings is None:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Install it using: pip install sentence-transformers"
        )
    return _embed_findings(findings)


def _get_value(finding, key, default=None):
    """Read a field from either a dictionary or a Pydantic model."""
    if isinstance(finding, dict):
        return finding.get(key, default)
    return getattr(finding, key, default)


def _get_location_path(finding):
    """Return a finding's file path when available."""
    location = _get_value(finding, "location")

    if isinstance(location, dict):
        return location.get("path")

    if location is not None:
        return getattr(location, "path", None)

    return _get_value(finding, "file_path")


def _attach_metadata(finding, duplicate_count, related_files):
    """Return a finding with duplicate metadata without mutating the input."""
    related_files = sorted(
        {path for path in related_files if isinstance(path, str) and path}
    )

    if isinstance(finding, dict):
        result = dict(finding)
        result["duplicate_count"] = duplicate_count
        result["related_files"] = related_files
        return result

    # Pydantic v2.
    if hasattr(finding, "model_copy"):
        return finding.model_copy(
            update={
                "duplicate_count": duplicate_count,
                "related_files": related_files,
            }
        )

    # Pydantic v1.
    if hasattr(finding, "copy"):
        return finding.copy(
            update={
                "duplicate_count": duplicate_count,
                "related_files": related_files,
            }
        )

    # Do not fail if a caller supplies a different object type.
    return finding


def deduplicate(findings: list, epsilon: float = 0.15) -> list:
    """
    Group similar findings using DBSCAN.

    The first finding in each duplicate cluster represents that cluster.
    Representatives include duplicate_count and related_files metadata.
    Noise findings are retained as individual findings.
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

    clusters = defaultdict(list)

    for index, label in enumerate(labels):
        clusters[int(label)].append(findings[index])

    results = []

    for label, cluster_findings in clusters.items():
        if label == -1:
            # DBSCAN noise points are not part of a duplicate cluster.
            for finding in cluster_findings:
                results.append(
                    _attach_metadata(
                        finding,
                        duplicate_count=1,
                        related_files=[_get_location_path(finding)],
                    )
                )
            continue

        representative = cluster_findings[0]
        related_files = [
            _get_location_path(finding) for finding in cluster_findings
        ]

        results.append(
            _attach_metadata(
                representative,
                duplicate_count=len(cluster_findings),
                related_files=related_files,
            )
        )

    return results
