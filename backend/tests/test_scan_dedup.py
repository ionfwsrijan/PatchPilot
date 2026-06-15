import io
import zipfile
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.utils.deduplicator as dedup_mod
from app.main import app as fastapi_app
from app.models import Finding, Location

client = TestClient(fastapi_app)


def make_dummy_zip():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr("dummy.py", "print('hello')")
    zip_buffer.seek(0)
    return zip_buffer


class MockSentenceTransformer:
    def __init__(self, *args, **kwargs):
        """Initialize mock."""
        pass

    def encode(self, texts, **kwargs):
        embs = []
        for text in texts:
            if "SQL Injection" in text:
                embs.append([1.0, 0.0])
            else:
                embs.append([0.0, 1.0])
        return np.array(embs)


findings_input = [
    Finding(
        id="1",
        category="sast",
        severity="HIGH",
        title="SQL Injection",
        description="SQL Injection in auth.py",
        location=Location(path="auth.py", start_line=10),
    ),
    Finding(
        id="2",
        category="sast",
        severity="HIGH",
        title="SQL Injection",
        description="SQL Injection in auth.py",
        location=Location(path="auth.py", start_line=15),
    ),
    Finding(
        id="3",
        category="secret",
        severity="CRITICAL",
        title="Hardcoded Password",
        description="Hardcoded password in config.py",
        location=Location(path="config.py", start_line=5),
    ),
]


@pytest.fixture(autouse=True)
def reset_dedup_cache():
    dedup_mod._MODEL = None
    yield
    dedup_mod._MODEL = None


# Case 1: Dedup enabled with duplicate findings
@patch("app.main.unzip_to_dir")
@patch("app.main._scan_repo_dir")
@patch("sentence_transformers.SentenceTransformer", new=MockSentenceTransformer)
def test_scan_dedup_enabled(mock_scan, mock_unzip, monkeypatch):
    monkeypatch.delenv("DISABLE_DEDUP", raising=False)
    monkeypatch.setenv("DEDUP_EPSILON", "0.15")
    mock_scan.return_value = ([], [], [], [], findings_input)

    zip_file = make_dummy_zip()
    res = client.post(
        "/scan",
        files={"project": ("project.zip", zip_file, "application/zip")},
        data={"project_name": "test_project"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["raw_finding_count"] == 3
    assert data["finding_count"] == 2
    assert len(data["findings"]) == 2
    assert {f["id"] for f in data["findings"]} == {"1", "3"}


# Case 2: DISABLE_DEDUP=true
@patch("app.main.unzip_to_dir")
@patch("app.main._scan_repo_dir")
@patch("sentence_transformers.SentenceTransformer", new=MockSentenceTransformer)
def test_scan_dedup_disabled(mock_scan, mock_unzip, monkeypatch):
    monkeypatch.setenv("DISABLE_DEDUP", "true")
    mock_scan.return_value = ([], [], [], [], findings_input)

    zip_file = make_dummy_zip()
    res = client.post(
        "/scan",
        files={"project": ("project.zip", zip_file, "application/zip")},
        data={"project_name": "test_project"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["raw_finding_count"] == 3
    assert data["finding_count"] == 3
    assert len(data["findings"]) == 3


# Case 3: sentence-transformers unavailable
@patch("app.main.unzip_to_dir")
@patch("app.main._scan_repo_dir")
def test_scan_dedup_sentence_transformers_unavailable(
    mock_scan, mock_unzip, monkeypatch
):
    monkeypatch.delenv("DISABLE_DEDUP", raising=False)
    mock_scan.return_value = ([], [], [], [], findings_input)

    with patch.dict("sys.modules", {"sentence_transformers": None}):
        zip_file = make_dummy_zip()
        res = client.post(
            "/scan",
            files={"project": ("project.zip", zip_file, "application/zip")},
            data={"project_name": "test_project"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["raw_finding_count"] == 3
        assert data["finding_count"] == 3
        assert len(data["findings"]) == 3


# Case 4: Invalid DEDUP_EPSILON value (fallback to 0.15)
@patch("app.main.unzip_to_dir")
@patch("app.main._scan_repo_dir")
@patch("sentence_transformers.SentenceTransformer", new=MockSentenceTransformer)
def test_scan_dedup_invalid_epsilon(mock_scan, mock_unzip, monkeypatch):
    monkeypatch.delenv("DISABLE_DEDUP", raising=False)
    monkeypatch.setenv("DEDUP_EPSILON", "abc")
    mock_scan.return_value = ([], [], [], [], findings_input)

    zip_file = make_dummy_zip()
    res = client.post(
        "/scan",
        files={"project": ("project.zip", zip_file, "application/zip")},
        data={"project_name": "test_project"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["raw_finding_count"] == 3
    assert data["finding_count"] == 2
    assert len(data["findings"]) == 2
