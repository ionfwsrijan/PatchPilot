import logging
import os
from pathlib import Path
from typing import List

import joblib
import pandas as pd

from app.models import Fix

logger = logging.getLogger(__name__)

# The model file path
MODEL_PATH = Path(__file__).parent / "fix_predictor.pkl"


def load_model():
    if not os.path.exists(MODEL_PATH):
        logger.info(
            "Fix predictor model not found at %s. Defaulting to None.", MODEL_PATH
        )
        return None
    try:
        model = joblib.load(MODEL_PATH)
        logger.info("Fix predictor model loaded successfully.")
        return model
    except Exception as e:
        logger.error("Failed to load fix predictor model: %s", e)
        return None


# Load model at startup
FIX_PREDICTOR_MODEL = load_model()


def predict_confidence(fixes: List[Fix]) -> List[Fix]:
    """
    Predicts confidence score for each proposed fix.
    Sets fix_confidence to None if model is not loaded.
    If the model is present, sorts fixes by confidence descending.
    """
    if FIX_PREDICTOR_MODEL is None or not fixes:
        for fix in fixes:
            fix.fix_confidence = None
        return fixes

    try:
        # Prepare features for the ML model
        features = []
        for fix in fixes:
            features.append(
                {
                    "diff_line_count": len(fix.diff.splitlines()) if fix.diff else 0,
                    "diff_file_count": len(fix.files_changed)
                    if fix.files_changed
                    else 0,
                    "notes_count": len(fix.notes) if fix.notes else 0,
                }
            )

        X = pd.DataFrame(features)

        # Check predict or predict_proba methods on the model
        if hasattr(FIX_PREDICTOR_MODEL, "predict_proba"):
            probs = FIX_PREDICTOR_MODEL.predict_proba(X)
            if probs.ndim > 1 and probs.shape[1] > 1:
                scores = probs[:, 1]
            else:
                scores = probs
        else:
            scores = FIX_PREDICTOR_MODEL.predict(X)

        for fix, score in zip(fixes, scores):
            fix.fix_confidence = float(score)

        # Sort descending by confidence score
        fixes = sorted(
            fixes,
            key=lambda f: f.fix_confidence if f.fix_confidence is not None else -1.0,
            reverse=True,
        )
    except Exception as e:
        logger.error("Error running fix confidence prediction: %s", e)
        for fix in fixes:
            if not hasattr(fix, "fix_confidence") or fix.fix_confidence is None:
                fix.fix_confidence = None

    return fixes
