import unittest
from unittest.mock import patch

from app.ml.fp_predictor import FalsePositivePredictor


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
