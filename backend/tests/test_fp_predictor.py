"""Tests for FalsePositivePredictor and the _apply_fp_predictor helper.

Covers:
- Graceful fallback when the classifier model is missing or corrupt.
- Length-invariant assertion in adjust_scores (every return path must
  produce len(scores) == len(findings)).
- Mismatch guard in _apply_fp_predictor: when adjusted_scores is shorter
  than findings the update is aborted and an error is logged, preventing
  silent truncation via zip().
- Happy-path: all findings receive updated ml_score values.

Isolation strategy
------------------
All sys.modules stubs are applied via ``patch.dict`` inside
``setUpClass`` / ``tearDownClass`` so they are automatically removed
after each test class.  This prevents stubs from polluting sys.modules
for other test files (e.g. test_llm_patcher, test_deduplicator,
test_safe_job_dir, test_pdf_builder) that run in the same pytest session.
"""

import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Stub builders — pure functions, do NOT touch sys.modules at module scope
# ---------------------------------------------------------------------------


def _build_torch_stubs() -> dict:
    """Return a dict of torch sub-module stubs."""
    torch = types.ModuleType("torch")

    class _Tensor:
        pass

    class _NoGrad:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    torch.Tensor = _Tensor  # type: ignore[attr-defined]
    torch.device = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    torch.no_grad = _NoGrad  # type: ignore[attr-defined]
    torch.cat = MagicMock(return_value=MagicMock(numpy=MagicMock(return_value=[])))  # type: ignore[attr-defined]
    backends = types.ModuleType("torch.backends")
    mps = types.ModuleType("torch.backends.mps")
    mps.is_available = lambda: False  # type: ignore[attr-defined]
    backends.mps = mps  # type: ignore[attr-defined]
    torch.backends = backends  # type: ignore[attr-defined]
    cuda = types.ModuleType("torch.cuda")
    cuda.is_available = lambda: False  # type: ignore[attr-defined]
    torch.cuda = cuda  # type: ignore[attr-defined]
    return {
        "torch": torch,
        "torch.backends": backends,
        "torch.backends.mps": mps,
        "torch.cuda": cuda,
    }


def _build_transformers_stubs() -> dict:
    """Return a dict of transformers sub-module stubs."""
    transformers = types.ModuleType("transformers")
    transformers.AutoModel = MagicMock()  # type: ignore[attr-defined]
    transformers.AutoTokenizer = MagicMock()  # type: ignore[attr-defined]
    return {"transformers": transformers}


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
# Stubs are scoped via patch.dict in setUpClass/tearDownClass so they do
# not leak into other test files.
# ---------------------------------------------------------------------------


class TestFalsePositivePredictor(unittest.TestCase):
    _patcher = None

    @classmethod
    def setUpClass(cls):
        stubs = {**_build_torch_stubs(), **_build_transformers_stubs()}
        cls._patcher = patch.dict(sys.modules, stubs)
        cls._patcher.start()
        sys.modules.pop("app.ml.fp_predictor", None)
        cls._fp_module = importlib.import_module("app.ml.fp_predictor")

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()
        sys.modules.pop("app.ml.fp_predictor", None)

    @patch("app.ml.fp_predictor.os.path.exists")
    def test_graceful_fallback_missing_model(self, mock_exists):
        """Returns fallback scores when the classifier model file is absent."""
        mock_exists.return_value = False
        predictor = self._fp_module.FalsePositivePredictor()
        self.assertFalse(predictor.is_ready)
        self.assertEqual(
            predictor.adjust_scores([{"rule_id": "test", "ml_score": 1.0}]), [1.0]
        )

    @patch("app.ml.fp_predictor.os.path.exists")
    @patch("app.ml.fp_predictor.joblib.load")
    def test_graceful_fallback_corrupt_model(self, mock_load, mock_exists):
        """Stays not-ready when the classifier file is corrupt."""
        mock_exists.return_value = True
        mock_load.side_effect = Exception("Corrupt file")
        self.assertFalse(self._fp_module.FalsePositivePredictor().is_ready)

    @patch("app.ml.fp_predictor.os.path.exists")
    def test_adjust_scores_same_length_as_findings_not_ready(self, mock_exists):
        """adjust_scores returns exactly len(findings) scores when not ready."""
        mock_exists.return_value = False
        predictor = self._fp_module.FalsePositivePredictor()
        findings = _make_ml_input(5)
        self.assertEqual(len(predictor.adjust_scores(findings)), len(findings))

    @patch("app.ml.fp_predictor.os.path.exists")
    def test_adjust_scores_empty_findings(self, mock_exists):
        """Empty findings list returns an empty scores list."""
        mock_exists.return_value = False
        self.assertEqual(self._fp_module.FalsePositivePredictor().adjust_scores([]), [])

    @patch("app.ml.fp_predictor.os.path.exists")
    def test_adjust_scores_length_invariant_on_inference_exception(self, mock_exists):
        """Returned scores must match findings length even when inference raises."""
        mock_exists.return_value = False
        predictor = self._fp_module.FalsePositivePredictor()
        predictor.is_ready = True
        predictor._models_loaded = True
        predictor.tokenizer = MagicMock(side_effect=RuntimeError("boom"))
        findings = _make_ml_input(3)
        self.assertEqual(len(predictor.adjust_scores(findings)), len(findings))

    @patch("app.ml.fp_predictor.os.path.exists")
    def test_adjust_scores_ml_score_none_defaults_to_1(self, mock_exists):
        """Findings with ml_score=None default to 1.0 in the returned scores."""
        mock_exists.return_value = False
        predictor = self._fp_module.FalsePositivePredictor()
        self.assertEqual(
            predictor.adjust_scores([{"rule_id": "r", "ml_score": None}]), [1.0]
        )


# ---------------------------------------------------------------------------
# Builder for all app.* + third-party stubs needed to import app.main
# ---------------------------------------------------------------------------


def _build_main_dep_stubs() -> dict:
    """Return a dict of stubs for every third-party / app module main.py uses."""
    stubs: dict = {}

    def _mod(name: str, **attrs) -> types.ModuleType:
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        stubs[name] = m
        return m

    _mod("aiosqlite")
    httpx = _mod("httpx")
    httpx.RequestError = Exception  # type: ignore[attr-defined]
    httpx.HTTPStatusError = Exception  # type: ignore[attr-defined]
    httpx.AsyncClient = MagicMock()  # type: ignore[attr-defined]
    pydantic = _mod("pydantic")
    pydantic.BaseModel = object  # type: ignore[attr-defined]
    pydantic.Field = lambda *a, **kw: None  # type: ignore[attr-defined]
    for mod_name in (
        "fastapi",
        "fastapi.concurrency",
        "fastapi.middleware",
        "fastapi.middleware.cors",
        "fastapi.responses",
    ):
        _mod(mod_name)
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
    fc = stubs["fastapi.concurrency"]
    fc.run_in_threadpool = AsyncMock()  # type: ignore[attr-defined]
    fastapi_mod.concurrency = fc  # type: ignore[attr-defined]
    stubs["fastapi.middleware.cors"].CORSMiddleware = MagicMock()  # type: ignore[attr-defined]
    for attr in ("FileResponse", "Response", "StreamingResponse"):
        setattr(stubs["fastapi.responses"], attr, MagicMock())

    for pkg in (
        "app.ml",
        "app.scanners",
        "app.utils",
        "app.remediation",
        "app.reports",
        "app.sandbox",
    ):
        _mod(pkg)
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
    _mod("app.scanners.entropy", run_entropy=MagicMock())
    _mod("app.scanners.gitleaks", run_gitleaks=MagicMock())
    _mod("app.scanners.osv", run_osv_scanner=MagicMock())
    _mod("app.scanners.semgrep", run_semgrep=MagicMock())
    _mod(
        "app.utils.fs",
        ensure_dir=MagicMock(),
        safe_job_dir=MagicMock(),
        safe_rmtree=MagicMock(),
        unzip_to_dir=MagicMock(),
    )
    _mod("app.utils.ml_features", extract_features=MagicMock())
    _mod("app.remediation.engine", propose_fixes=MagicMock())
    _mod("app.reports.evidence_pack", build_evidence_pack=MagicMock())
    _mod(
        "app.reports.pdf_builder",
        generate_audit_pdf=MagicMock(),
        generate_org_audit_pdf=MagicMock(),
    )
    _mod("app.sandbox.verify", verify_repo=MagicMock())
    return stubs


# ---------------------------------------------------------------------------
# _apply_fp_predictor integration tests
# Stubs are scoped via patch.dict in setUpClass/tearDownClass.
# ---------------------------------------------------------------------------


class TestApplyFpPredictor(unittest.IsolatedAsyncioTestCase):
    """Tests for the _apply_fp_predictor helper in main.py."""

    _patcher = None
    _main_module = None
    _apply_fp_predictor = None

    @classmethod
    def setUpClass(cls):
        stubs = {
            **_build_torch_stubs(),
            **_build_transformers_stubs(),
            **_build_main_dep_stubs(),
        }
        cls._patcher = patch.dict(sys.modules, stubs)
        cls._patcher.start()
        # Evict any previously cached app.main so it re-imports under our stubs.
        sys.modules.pop("app.main", None)
        cls._main_module = importlib.import_module("app.main")
        # Wrap in staticmethod so self is not injected when called as
        # self._apply_fp_predictor(findings) inside test methods.
        cls._apply_fp_predictor = staticmethod(cls._main_module._apply_fp_predictor)

    @classmethod
    def tearDownClass(cls):
        # Only remove app.main itself — patch.dict.stop() restores the stubs
        # we inserted. Wiping all app.* would also remove C-extension backed
        # modules (numpy, sklearn internals) which Python refuses to reload.
        sys.modules.pop("app.main", None)
        cls._patcher.stop()

    async def _call(self, findings, adjusted_scores):
        """Invoke _apply_fp_predictor with run_in_threadpool mocked."""
        with patch.object(
            self._main_module,
            "run_in_threadpool",
            new=AsyncMock(return_value=adjusted_scores),
        ):
            await self._apply_fp_predictor(findings)

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
        adjusted = [0.5, 0.5]  # only 2 scores for 4 findings

        with self.assertLogs("app.main", level="ERROR") as log_ctx:
            await self._call(findings, adjusted)

        for f in findings:
            self.assertEqual(f.ml_score, 1.0)
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
        self.assertTrue(any("length mismatch" in msg for msg in log_ctx.output))

    async def test_single_finding_updated_correctly(self):
        """Edge-case: single finding is updated with the single returned score."""
        findings = _make_findings(1)
        await self._call(findings, [0.05])
        self.assertAlmostEqual(findings[0].ml_score, 0.05)
