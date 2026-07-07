"""Tests for FalsePositivePredictor and the _apply_fp_predictor helper.

Covers:
- Graceful fallback when the classifier model is missing or corrupt.
- Length-invariant assertion in adjust_scores (every return path must
  produce len(scores) == len(findings)).
- Mismatch guard in _apply_fp_predictor: when adjusted_scores is shorter
  than findings the update is aborted and an error is logged, preventing
  silent truncation via zip().
- Happy-path: all findings receive updated ml_score values.
"""

import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Stub out heavy ML dependencies (torch, transformers) so the tests run in
# environments where those packages are not installed (CI, dev machines).
# The stubs are inserted into sys.modules BEFORE the app modules are imported.
# ---------------------------------------------------------------------------
def _make_torch_stub() -> types.ModuleType:
    torch = types.ModuleType("torch")

    # torch.Tensor — needed by scipy's array_api_compat is_torch_array check
    class _Tensor:
        pass

    torch.Tensor = _Tensor  # type: ignore[attr-defined]

    # torch.device
    torch.device = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]

    # torch.no_grad — used as a context manager
    class _NoGrad:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    torch.no_grad = _NoGrad  # type: ignore[attr-defined]

    # torch.cat
    torch.cat = MagicMock(return_value=MagicMock(numpy=MagicMock(return_value=[])))  # type: ignore[attr-defined]

    # torch.backends.mps stub
    backends = types.ModuleType("torch.backends")
    mps = types.ModuleType("torch.backends.mps")
    mps.is_available = lambda: False  # type: ignore[attr-defined]
    backends.mps = mps  # type: ignore[attr-defined]
    torch.backends = backends  # type: ignore[attr-defined]

    # torch.cuda stub
    cuda = types.ModuleType("torch.cuda")
    cuda.is_available = lambda: False  # type: ignore[attr-defined]
    torch.cuda = cuda  # type: ignore[attr-defined]

    sys.modules.setdefault("torch", torch)
    sys.modules.setdefault("torch.backends", backends)
    sys.modules.setdefault("torch.backends.mps", mps)
    sys.modules.setdefault("torch.cuda", cuda)
    return torch


def _make_transformers_stub() -> types.ModuleType:
    transformers = types.ModuleType("transformers")
    transformers.AutoModel = MagicMock()  # type: ignore[attr-defined]
    transformers.AutoTokenizer = MagicMock()  # type: ignore[attr-defined]
    sys.modules.setdefault("transformers", transformers)
    return transformers


_make_torch_stub()
_make_transformers_stub()

# Now safe to import app modules.
from app.ml.fp_predictor import FalsePositivePredictor  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_findings(n: int):
    """Return a list of minimal Finding-like objects with ml_score=1.0."""
    findings = []
    for i in range(n):
        f = MagicMock()
        f.ml_score = 1.0
        f.description = f"desc-{i}"
        f.title = f"title-{i}"
        f.location = None
        f.metadata = {}
        findings.append(f)
    return findings


def _make_ml_input(n: int) -> list[dict]:
    return [
        {
            "rule_id": f"rule-{i}",
            "message": f"msg-{i}",
            "file_path": "",
            "ml_score": 1.0,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# FalsePositivePredictor unit tests
# ---------------------------------------------------------------------------


class TestFalsePositivePredictor(unittest.TestCase):
    @patch("app.ml.fp_predictor.os.path.exists")
    def test_graceful_fallback_missing_model(self, mock_exists):
        mock_exists.return_value = False

        predictor = FalsePositivePredictor()

        self.assertFalse(predictor.is_ready)

        mock_findings = [{"rule_id": "test", "ml_score": 1.0}]
        result_scores = predictor.adjust_scores(mock_findings)

        self.assertEqual(result_scores, [1.0])

    @patch("app.ml.fp_predictor.os.path.exists")
    @patch("app.ml.fp_predictor.joblib.load")
    def test_graceful_fallback_corrupt_model(self, mock_load, mock_exists):
        mock_exists.return_value = True
        mock_load.side_effect = Exception("Corrupt file")

        predictor = FalsePositivePredictor()

        self.assertFalse(predictor.is_ready)

    # --- length-invariant tests ---

    @patch("app.ml.fp_predictor.os.path.exists")
    def test_adjust_scores_same_length_as_findings_not_ready(self, mock_exists):
        """adjust_scores returns exactly len(findings) scores when not ready."""
        mock_exists.return_value = False
        predictor = FalsePositivePredictor()

        findings = _make_ml_input(5)
        scores = predictor.adjust_scores(findings)

        self.assertEqual(len(scores), len(findings))

    @patch("app.ml.fp_predictor.os.path.exists")
    def test_adjust_scores_empty_findings(self, mock_exists):
        """Empty findings list returns an empty scores list."""
        mock_exists.return_value = False
        predictor = FalsePositivePredictor()

        scores = predictor.adjust_scores([])
        self.assertEqual(scores, [])

    @patch("app.ml.fp_predictor.os.path.exists")
    def test_adjust_scores_length_invariant_on_inference_exception(self, mock_exists):
        """Even when ML inference raises, returned scores must match findings length."""
        mock_exists.return_value = False
        predictor = FalsePositivePredictor()
        # Force is_ready=True and simulate a crashing classifier.
        predictor.is_ready = True
        predictor._models_loaded = True
        predictor.tokenizer = MagicMock(side_effect=RuntimeError("boom"))

        findings = _make_ml_input(3)
        # adjust_scores should catch the exception internally and still return
        # a list of the correct length.
        scores = predictor.adjust_scores(findings)
        self.assertEqual(len(scores), len(findings))

    @patch("app.ml.fp_predictor.os.path.exists")
    def test_adjust_scores_ml_score_none_defaults_to_1(self, mock_exists):
        """Findings with ml_score=None default to 1.0 in the returned scores."""
        mock_exists.return_value = False
        predictor = FalsePositivePredictor()

        findings = [{"rule_id": "r", "ml_score": None}]
        scores = predictor.adjust_scores(findings)
        self.assertEqual(scores, [1.0])


# ---------------------------------------------------------------------------
# Stub heavy main.py third-party deps so _apply_fp_predictor can be imported
# without the full app stack (aiosqlite, httpx, fastapi, pydantic, etc.).
# ---------------------------------------------------------------------------
def _stub_main_deps() -> None:
    """Insert minimal stubs for every third-party module that main.py imports."""
    stubs: dict[str, object] = {}

    # aiosqlite
    aiosqlite = types.ModuleType("aiosqlite")
    stubs["aiosqlite"] = aiosqlite

    # httpx
    httpx = types.ModuleType("httpx")
    httpx.RequestError = Exception  # type: ignore[attr-defined]
    httpx.HTTPStatusError = Exception  # type: ignore[attr-defined]
    httpx.AsyncClient = MagicMock()  # type: ignore[attr-defined]
    stubs["httpx"] = httpx

    # pydantic
    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = object  # type: ignore[attr-defined]
    pydantic.Field = lambda *a, **kw: None  # type: ignore[attr-defined]
    stubs["pydantic"] = pydantic

    # fastapi + sub-modules
    for mod_name in (
        "fastapi",
        "fastapi.concurrency",
        "fastapi.middleware",
        "fastapi.middleware.cors",
        "fastapi.responses",
    ):
        stubs[mod_name] = types.ModuleType(mod_name)

    fastapi_mod = stubs["fastapi"]
    for attr in (
        "FastAPI",
        "BackgroundTasks",
        "File",
        "Form",
        "HTTPException",
        "Query",
        "Request",
        "UploadFile",
        "Depends",
    ):
        setattr(fastapi_mod, attr, MagicMock())

    fastapi_concurrency = stubs["fastapi.concurrency"]
    fastapi_concurrency.run_in_threadpool = AsyncMock()  # type: ignore[attr-defined]
    fastapi_mod.concurrency = fastapi_concurrency  # type: ignore[attr-defined]

    cors_mod = stubs["fastapi.middleware.cors"]
    cors_mod.CORSMiddleware = MagicMock()  # type: ignore[attr-defined]

    resp_mod = stubs["fastapi.responses"]
    for attr in ("FileResponse", "Response", "StreamingResponse"):
        setattr(resp_mod, attr, MagicMock())

    for name, stub in stubs.items():
        sys.modules.setdefault(name, stub)  # type: ignore[arg-type]

    # -----------------------------------------------------------------------
    # Stub every app.* sub-module that main.py imports from.
    # We register LEAF modules (e.g. "app.ml.ranker") individually so their
    # from-import symbols resolve without touching real package init files.
    # Order matters for packages: register the parent before children.
    # -----------------------------------------------------------------------
    def _mod(name: str, **attrs) -> types.ModuleType:
        m = sys.modules.get(name) or types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules.setdefault(name, m)
        return m

    # Parent packages (needed so sub-module dotted names resolve)
    _mod("app.ml")
    _mod("app.scanners")
    _mod("app.utils")
    _mod("app.remediation")
    _mod("app.reports")
    _mod("app.sandbox")

    # app.db
    _mod(
        "app.db",
        create_findings=MagicMock(),
        create_job=MagicMock(),
        delete_job=MagicMock(),
        get_cwe_distribution=MagicMock(),
        get_db=MagicMock(),
        get_dependency_diff=MagicMock(),
        get_finding=MagicMock(),
        get_findings_by_job_id=MagicMock(),
        get_job=MagicMock(),
        get_leaderboard_stats=MagicMock(),
        get_trend_data=MagicMock(),
        init_db=MagicMock(),
        update_finding_status=MagicMock(),
        update_job_status=MagicMock(),
        upsert_contributor_stat=MagicMock(),
    )

    # app.models
    _mod(
        "app.models",
        Finding=MagicMock,
        Location=MagicMock,
        FindingStatusUpdate=MagicMock,
        Fix=MagicMock,
        FixRequest=MagicMock,
        FixResponse=MagicMock,
        OrgJobStatusResponse=MagicMock,
        OrgScanRequest=MagicMock,
        RepoStatus=MagicMock,
        ScanResponse=MagicMock,
        VerifyResponse=MagicMock,
    )

    # app.ml.*  — stub BEFORE main.py's relative imports run
    _mod(
        "app.ml.deduplicator",
        SENTENCE_TRANSFORMERS_AVAILABLE=False,
        deduplicate=MagicMock(),
    )
    _mod("app.ml.fp_predictor", predictor=MagicMock())
    _mod(
        "app.ml.ranker",
        load_ranker=MagicMock(return_value=MagicMock()),
        scoring_function=MagicMock(),
    )
    _mod("app.ml.embedder", embed=MagicMock())
    _mod("app.ml.llm_patcher", patch_finding=MagicMock())

    # app.scanners.*
    _mod("app.scanners.entropy", run_entropy=MagicMock())
    _mod("app.scanners.gitleaks", run_gitleaks=MagicMock())
    _mod("app.scanners.osv", run_osv_scanner=MagicMock())
    _mod("app.scanners.semgrep", run_semgrep=MagicMock())

    # app.utils.*
    _mod(
        "app.utils.fs",
        ensure_dir=MagicMock(),
        safe_job_dir=MagicMock(),
        safe_rmtree=MagicMock(),
        unzip_to_dir=MagicMock(),
    )
    _mod("app.utils.ml_features", extract_features=MagicMock())

    # app.remediation.*
    _mod("app.remediation.engine", propose_fixes=MagicMock())

    # app.reports.*
    _mod("app.reports.evidence_pack", build_evidence_pack=MagicMock())
    _mod(
        "app.reports.pdf_builder",
        generate_audit_pdf=MagicMock(),
        generate_org_audit_pdf=MagicMock(),
    )

    # app.sandbox.*
    _mod("app.sandbox.verify", verify_repo=MagicMock())


_stub_main_deps()

# Import the function under test directly — avoids executing the full FastAPI
# app setup while still exercising the real logic in _apply_fp_predictor.
_main_module = importlib.import_module("app.main")  # noqa: E402
_apply_fp_predictor = _main_module._apply_fp_predictor


# ---------------------------------------------------------------------------
# _apply_fp_predictor integration tests
# ---------------------------------------------------------------------------


class TestApplyFpPredictor(unittest.IsolatedAsyncioTestCase):
    """Tests for the _apply_fp_predictor helper in main.py."""

    async def _call(self, findings, adjusted_scores):
        """Invoke _apply_fp_predictor with a mocked predictor return value."""
        with patch.object(
            _main_module,
            "run_in_threadpool",
            new=AsyncMock(return_value=adjusted_scores),
        ):
            await _apply_fp_predictor(findings)

    async def test_happy_path_all_findings_updated(self):
        """All findings have ml_score updated when lengths match."""
        findings = _make_findings(3)
        adjusted = [0.1, 0.2, 0.3]
        await self._call(findings, adjusted)
        for f, expected in zip(findings, adjusted):
            self.assertAlmostEqual(f.ml_score, expected)

    async def test_mismatch_aborts_update_and_logs_error(self):
        """When adjusted_scores is shorter than findings, no finding is updated."""
        findings = _make_findings(4)
        # Predictor returns only 2 scores for 4 findings.
        adjusted = [0.5, 0.5]

        with self.assertLogs("app.main", level="ERROR") as log_ctx:
            await self._call(findings, adjusted)

        # No finding should have been mutated.
        for f in findings:
            self.assertEqual(f.ml_score, 1.0)

        # An error must have been logged mentioning the mismatch.
        self.assertTrue(
            any(
                "length mismatch" in msg or "2 scores" in msg or "4 findings" in msg
                for msg in log_ctx.output
            ),
            "Expected a length-mismatch error in the logs",
        )

    async def test_mismatch_longer_adjusted_scores_also_detected(self):
        """adjusted_scores longer than findings is also a mismatch — no update."""
        findings = _make_findings(2)
        adjusted = [0.1, 0.2, 0.3, 0.4]  # too many scores

        with self.assertLogs("app.main", level="ERROR") as log_ctx:
            await self._call(findings, adjusted)

        for f in findings:
            self.assertEqual(f.ml_score, 1.0)

        self.assertTrue(
            any("length mismatch" in msg for msg in log_ctx.output),
        )

    async def test_single_finding_updated_correctly(self):
        """Edge-case: single finding is updated with the single returned score."""
        findings = _make_findings(1)
        await self._call(findings, [0.05])
        self.assertAlmostEqual(findings[0].ml_score, 0.05)
