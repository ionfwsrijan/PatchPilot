from __future__ import annotations

# Canonical category values used everywhere: scanners, DB queries, priority scorer.
# Adding a new scanner? Add its category here first.
VALID_CATEGORIES = {"dependency", "sast", "secret"}

# Maps known aliases / typos → canonical value.
_ALIASES: dict[str, str] = {
    # dependency variants
    "dependencies": "dependency",
    "dep": "dependency",
    "vuln": "dependency",
    "vulnerability": "dependency",
    # sast variants
    "static": "sast",
    "code": "sast",
    # secret variants
    "secrets": "secret",
    "credential": "secret",
    "credentials": "secret",
    "leak": "secret",
}

_FALLBACK = "sast"


def normalize_category(raw: str | None) -> str:
    """
    Return a canonical category string from any raw scanner value.

    - Strips whitespace and lowercases.
    - Passes through values already in VALID_CATEGORIES unchanged.
    - Resolves known aliases.
    - Falls back to ``_FALLBACK`` ("sast") for anything unrecognised.

    Examples:
    --------
    >>> normalize_category("dependency")
    'dependency'
    >>> normalize_category("Dependency")
    'dependency'
    >>> normalize_category("  SECRET  ")
    'secret'
    >>> normalize_category("vuln")
    'dependency'
    >>> normalize_category("whatever")
    'sast'
    >>> normalize_category(None)
    'sast'
    """
    if not raw:
        return _FALLBACK
    val = raw.strip().lower()
    if val in VALID_CATEGORIES:
        return val
    return _ALIASES.get(val, _FALLBACK)
