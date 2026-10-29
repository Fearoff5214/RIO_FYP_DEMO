"""
Learning hub — triggers L10, L11, L12 background jobs after case close.
"""
from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


async def trigger_learning(job_id: str, state: dict) -> None:
    """
    Trigger all three learning loops after a case is closed.
    L10: export corrected labels for CV model retraining.
    L11: add finalized RCA to knowledge base.
    L12: recalibrate confidence using expert feedback.
    """
    await _l10_label_export(job_id, state)
    await _l11_kb_update(job_id, state)
    await _l12_recalibrate(job_id, state)


async def _l10_label_export(job_id: str, state: dict) -> None:
    """L10: export human-corrected labels to training dataset."""
    defects = state.get("defects", []) or []
    corrected = [d for d in defects if d.get("human_corrected")]

    if not corrected:
        return

    logger.info('"learning":"L10","job_id":"%s","n_corrected":%d', job_id, len(corrected))

    # In production: write to DVC-tracked dataset, check if n_new >= retrain_threshold
    # then submit a Celery task for retraining
    # For now: log and record in model_registry if count exceeds threshold
    from app.core.config import get_config
    cfg = get_config()
    min_labels = cfg.get("learning", "retrain_min_new_labels") or 200

    # Count total corrected labels (placeholder)
    logger.info('"learning":"L10_export","n_labels":%d,"threshold":%d', len(corrected), min_labels)


async def _l11_kb_update(job_id: str, state: dict) -> None:
    """L11: add finalized RCA as a new KB document."""
    final_rca = state.get("final_rca") or {}
    if not final_rca:
        return

    cause = final_rca.get("cause", "")
    effect = final_rca.get("effect", "")
    if not cause:
        return

    logger.info('"learning":"L11","job_id":"%s","cause":"%s"', job_id, cause[:50])

    # Build a knowledge document from the finalized RCA
    doc_text = (
        f"Job: {job_id}. "
        f"Root Cause: {cause}. "
        f"Effect: {effect}. "
        f"Corrective Actions: {final_rca.get('corrective_actions', [])}. "
        f"Preventive Actions: {final_rca.get('preventive_actions', [])}."
    )

    # In production: run through the ingestion pipeline
    # For now: log
    logger.info('"learning":"L11_doc","%s"', doc_text[:100])


async def _l12_recalibrate(job_id: str, state: dict) -> None:
    """L12: recalibrate confidence scores using gate2 expert feedback."""
    from app.core.config import get_config
    cfg = get_config()

    if cfg.get("learning", "threshold_change_requires_approval"):
        logger.info('"learning":"L12","status":"pending_approval","job_id":"%s"', job_id)
        return

    logger.info('"learning":"L12","job_id":"%s"', job_id)
    # Trigger calibrator refit (async, deferred)
    from app.scoring.calibration import refit_calibrator
    # Would load samples from DB feedback table here
    await refit_calibrator([])
