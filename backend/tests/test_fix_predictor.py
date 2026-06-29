import unittest
from unittest.mock import MagicMock, patch

from app.ml.fix_predictor import load_model, predict_confidence
from app.models import Fix


class TestFixPredictor(unittest.TestCase):
    @patch("app.ml.fix_predictor.os.path.exists")
    def test_graceful_fallback_missing_model(self, mock_exists):
        mock_exists.return_value = False

        # Test loader fallback
        model = load_model()
        self.assertIsNone(model)

        fixes = [
            Fix(finding_id="1", status="suggested", summary="Fix 1"),
            Fix(finding_id="2", status="suggested", summary="Fix 2"),
        ]

        with patch("app.ml.fix_predictor.FIX_PREDICTOR_MODEL", None):
            result = predict_confidence(fixes)
            self.assertEqual(len(result), 2)
            self.assertIsNone(result[0].fix_confidence)
            self.assertIsNone(result[1].fix_confidence)

    @patch("app.ml.fix_predictor.os.path.exists")
    @patch("app.ml.fix_predictor.joblib.load")
    def test_predict_confidence_and_sort(self, mock_load, mock_exists):
        mock_exists.return_value = True

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.85, 0.95]
        if hasattr(mock_model, "predict_proba"):
            del mock_model.predict_proba

        mock_load.return_value = mock_model

        fixes = [
            Fix(finding_id="low_conf", status="suggested", summary="Fix low", diff="abc"),
            Fix(finding_id="high_conf", status="suggested", summary="Fix high", diff="xyz\n123"),
        ]

        with patch("app.ml.fix_predictor.FIX_PREDICTOR_MODEL", mock_model):
            result = predict_confidence(fixes)

            # High confidence should be first
            self.assertEqual(result[0].finding_id, "high_conf")
            self.assertEqual(result[0].fix_confidence, 0.95)

            # Low confidence should be second
            self.assertEqual(result[1].finding_id, "low_conf")
            self.assertEqual(result[1].fix_confidence, 0.85)
