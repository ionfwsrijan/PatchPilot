import logging
import os
from pathlib import Path
from typing import List

try:
    import joblib
    import pandas as pd

    FIX_PREDICTOR_DEPENDENCIES_AVAILABLE = True
except ImportError:
    FIX_PREDICTOR_DEPENDENCIES_AVAILABLE = False

from app.models import Fix

logger = logging.getLogger(__name__)

# The model file path
MODEL_PATH = Path(__file__).parent / "fix_predictor.pkl"


def load_model():
    if not FIX_PREDICTOR_DEPENDENCIES_AVAILABLE:
        logger.info("Fix predictor dependencies missing. Defaulting to None.")
        return None
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


# Do not load model at import time to avoid IO side-effects in tests/CI
FIX_PREDICTOR_MODEL = None


def _get_model():
    global FIX_PREDICTOR_MODEL
    if FIX_PREDICTOR_MODEL is None:
        FIX_PREDICTOR_MODEL = load_model()
    return FIX_PREDICTOR_MODEL


def predict_confidence(fixes: List[Fix]) -> List[Fix]:
    """
    Predicts confidence score for each proposed fix.
    Sets fix_confidence to None if model is not loaded.
    If the model is present, sorts fixes by confidence descending.
    """
    model = _get_model()
    if not FIX_PREDICTOR_DEPENDENCIES_AVAILABLE or model is None or not fixes:
        # Return new Fix objects with explicit None confidence (no in-place mutation)
        return [fix.model_copy(update={"fix_confidence": None}) for fix in fixes]

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
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X)
            if hasattr(probs, "ndim") and probs.ndim > 1 and probs.shape[1] > 1:
                scores = probs[:, 1]
            else:
                scores = probs
        else:
            scores = model.predict(X)

        # Build new Fix objects with confidence scores (avoid mutating input)
        new_fixes = []
        for fix, score in zip(fixes, scores):
            new_fixes.append(fix.model_copy(update={"fix_confidence": float(score)}))

        # Sort descending by confidence score
        fixes = sorted(
            new_fixes,
            key=lambda f: f.fix_confidence if f.fix_confidence is not None else -1.0,
            reverse=True,
        )
    except Exception as e:
        logger.error("Error running fix confidence prediction: %s", e)
        # On error, return copies with None confidence
        fixes = [fix.model_copy(update={"fix_confidence": None}) for fix in fixes]

    return fixes
