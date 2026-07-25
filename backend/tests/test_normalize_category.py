"""
Tests for issue #63 – Normalize Dependency Finding Categories.

Verifies that normalize_category always returns a value from VALID_CATEGORIES
and that all three scanners use it consistently.
"""

import pytest

from app.utils.categories import _FALLBACK, VALID_CATEGORIES, normalize_category

# ---------------------------------------------------------------------------
# normalize_category unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # already canonical
        ("dependency", "dependency"),
        ("sast", "sast"),
        ("secret", "secret"),
        # casing / whitespace
        ("Dependency", "dependency"),
        ("SAST", "sast"),
        ("  SECRET  ", "secret"),
        # known aliases
        ("dependencies", "dependency"),
        ("dep", "dependency"),
        ("vuln", "dependency"),
        ("vulnerability", "dependency"),
        ("static", "sast"),
        ("code", "sast"),
        ("secrets", "secret"),
        ("credential", "secret"),
        ("credentials", "secret"),
        ("leak", "secret"),
        # unknowns fall back
        ("whatever", _FALLBACK),
        ("", _FALLBACK),
        # None
        (None, _FALLBACK),
    ],
)
def test_normalize_category(raw, expected):
    assert normalize_category(raw) == expected


def test_output_always_in_valid_categories():
    """Every possible output must be a member of VALID_CATEGORIES."""
    samples = [
        "dependency",
        "Dependency",
        "DEPENDENCY",
        "sast",
        "SAST",
        "secret",
        "SECRET",
        "vuln",
        "leak",
        "garbage",
        "",
        None,
    ]
    for s in samples:
        result = normalize_category(s)
        assert result in VALID_CATEGORIES, (
            f"normalize_category({s!r}) = {result!r} not in VALID_CATEGORIES"
        )


# ---------------------------------------------------------------------------
# Scanner integration: confirm each scanner imports and uses normalize_category
# ---------------------------------------------------------------------------


def test_osv_scanner_uses_normalize_category():
    import inspect

    import app.scanners.osv as osv_mod

    source = inspect.getsource(osv_mod)
    assert "normalize_category" in source, "osv.py must call normalize_category"
    assert "from ..utils.categories import normalize_category" in source


def test_semgrep_scanner_uses_normalize_category():
    import inspect

    import app.scanners.semgrep as semgrep_mod

    source = inspect.getsource(semgrep_mod)
    assert "normalize_category" in source, "semgrep.py must call normalize_category"
    assert "from ..utils.categories import normalize_category" in source


def test_gitleaks_scanner_uses_normalize_category():
    import inspect

    import app.scanners.gitleaks as gitleaks_mod

    source = inspect.getsource(gitleaks_mod)
    assert "normalize_category" in source, "gitleaks.py must call normalize_category"
    assert "from ..utils.categories import normalize_category" in source


# ---------------------------------------------------------------------------
# Regression: categories used in DB queries must exist in VALID_CATEGORIES
# ---------------------------------------------------------------------------


def test_db_hardcoded_categories_are_valid():
    """
    db.py has WHERE category = 'dependency' hardcoded.
    Ensure that value is in VALID_CATEGORIES so it always matches scanner output.
    """
    assert "dependency" in VALID_CATEGORIES
    assert "sast" in VALID_CATEGORIES
    assert "secret" in VALID_CATEGORIES


def test_priority_scorer_categories_are_valid():
    """
    main.py priority scorer uses {"dependency", "secret", "sast"}.
    All must be in VALID_CATEGORIES.
    """
    scorer_keys = {"dependency", "secret", "sast"}
    assert scorer_keys.issubset(VALID_CATEGORIES)
