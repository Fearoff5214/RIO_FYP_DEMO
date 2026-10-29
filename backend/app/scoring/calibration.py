"""
Confidence calibration using isotonic regression.
Falls back to identity mapping with conservative cap until min_samples reached.
"""
from __future__ import annotations

from app.core.config import get_config


async def calibrate_scores(top3: list[dict]) -> list[dict]:
    """
    Apply calibration to confidence_raw to produce confidence_cal.
    Uses identity mapping until sufficient data is available.
    """
    cfg = get_config()
    min_samples = int(cfg.get("prediction", "calibration", "min_samples") or 50)

    n_samples = await _count_calibration_samples()

    if n_samples < min_samples:
        # Identity mapping with conservative cap
        return [
            {
                **c,
                "confidence_cal": round(min(c.get("confidence_raw", 0.5), 0.95), 4),
                "calibration_method": "identity_uncalibrated",
            }
            for c in top3
        ]

    # Isotonic regression calibration
    calibrator = await _load_calibrator()
    if calibrator is None:
        return [{**c, "confidence_cal": c.get("confidence_raw", 0.5)} for c in top3]

    raw_scores = [c.get("confidence_raw", 0.5) for c in top3]
    try:
        cal_scores = calibrator.predict(raw_scores)
        return [
            {**c, "confidence_cal": round(float(s), 4), "calibration_method": "isotonic"}
            for c, s in zip(top3, cal_scores)
        ]
    except Exception:
        return [{**c, "confidence_cal": c.get("confidence_raw", 0.5)} for c in top3]


async def _count_calibration_samples() -> int:
    """Count available calibration samples (rca_choice feedback rows)."""
    try:
        from app.db.session import _get_session_factory
        from sqlalchemy import select, func
        from app.db.models import Feedback

        factory = _get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(func.count()).where(Feedback.kind == "rca_choice")
            )
            return result.scalar_one() or 0
    except Exception:
        return 0


async def _load_calibrator():
    """Load the isotonic regression calibrator from storage."""
    # Placeholder: in production load from MLflow or object storage
    return None


async def refit_calibrator(feedback_samples: list[dict]) -> None:
    """
    Refit the isotonic regression calibrator on (confidence_raw, accepted) pairs.
    Called by the learning hub (L12).
    """
    if len(feedback_samples) < 10:
        return

    try:
        from sklearn.isotonic import IsotonicRegression
        import numpy as np

        X = np.array([s["confidence_raw"] for s in feedback_samples])
        y = np.array([1.0 if s["accepted"] else 0.0 for s in feedback_samples])

        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(X.reshape(-1, 1), y)

        # TODO: persist to object storage / MLflow
        from app.core.logging import get_logger
        get_logger(__name__).info('"calibration":"refitted","n_samples":%d', len(feedback_samples))

    except ImportError:
        pass
