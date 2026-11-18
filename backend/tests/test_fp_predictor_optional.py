import importlib
import sys
from unittest.mock import patch


def test_predictor_imports_and_falls_back_without_ml_packages():
    import app.ml.fp_predictor as mod

    blocked = {"torch": None, "transformers": None}
    with patch.dict(sys.modules, blocked):
        reloaded = importlib.reload(mod)
        assert reloaded.HAS_ML is False
        predictor = reloaded.FalsePositivePredictor()
        scores = predictor.adjust_scores([{"rule_id": "r", "ml_score": 0.7}, {}])
        assert scores == [0.7, 1.0]
        assert predictor.is_ready is False
    importlib.reload(mod)
