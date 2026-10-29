"""Stage 3 — Defect Detection nodes."""
from __future__ import annotations

from app.core.config import get_config
from app.core.logging import get_logger
from app.workflow.state import InspectionState

logger = get_logger(__name__)


async def dispatch_detectors(state: InspectionState) -> dict:
    """Dispatch all detectors in parallel (YOLO + SAM + Anomalib)."""
    from app.cv.detectors.factory import get_detector_ensemble

    images = state.get("images", []) or []
    job_id = state.get("job_id", "")
    cfg = get_config()

    logger.info('"node":"dispatch_detectors","job_id":"%s","n_images":%d', job_id, len(images))

    ensemble = get_detector_ensemble(cfg)
    detections = await ensemble.detect_all(images)
    return {"detections": detections, "status": "DEFECT_DETECTION"}


async def detect_segment(state: InspectionState) -> dict:
    """(Already done in dispatch_detectors for simplicity; this node logs/passes through.)"""
    return {}


async def anomaly_check(state: InspectionState) -> dict:
    """(Anomalib results already included in dispatch_detectors output.)"""
    return {}


async def fuse(state: InspectionState) -> dict:
    """Fuse detections from all detectors using weighted NMS/WBF."""
    from app.cv.detectors.fuse import fuse_detections

    detections = state.get("detections", []) or []
    cfg = get_config()
    weights = cfg.get("detection", "fusion_weights") or {"yolo": 0.5, "sam": 0.2, "anomalib": 0.3}

    fused = fuse_detections(detections, weights)
    defect_found = len(fused) > 0

    logger.info('"node":"fuse","n_fused":%d,"defect_found":%s', len(fused), defect_found)
    return {"detections": fused, "defect_found": defect_found}


async def classify_measure(state: InspectionState) -> dict:
    """Classify defect types, compute severity, measure size in mm²."""
    from app.cv.detectors.classify import classify_and_measure

    detections = state.get("detections", []) or []
    part_master = state.get("part_master", {}) or {}
    calibration = part_master.get("calibration", {}) or {}
    cfg = get_config()

    severity_rules = cfg.get("detection", "severity_rules") or {
        "crack": "critical",
        "deformation": "major",
        "dent": "major",
        "scratch": "minor",
    }

    defects, min_conf = classify_and_measure(detections, calibration, severity_rules)

    logger.info('"node":"classify_measure","n_defects":%d,"min_conf":%.3f', len(defects), min_conf)
    return {"defects": defects, "min_confidence": min_conf}


async def label_review_gate(state: InspectionState) -> dict:
    """Human label review gate — interrupt for engineer."""
    from langgraph.types import interrupt

    defects = state.get("defects", []) or []
    job_id = state.get("job_id", "")
    logger.info('"node":"label_review_gate","job_id":"%s"', job_id)

    payload = {
        "gate": "LABEL",
        "job_id": job_id,
        "defects": defects,
        "message": "One or more detections have low confidence. Please review and correct labels.",
    }

    decision = interrupt(payload)
    return {"label_review": decision, "status": "LABEL_REVIEWED"}


async def save_defects(state: InspectionState, *, db=None) -> dict:
    """Persist defect rows; apply any label corrections from label review."""
    defects = state.get("defects", []) or []
    label_review = state.get("label_review") or {}
    job_id = state.get("job_id", "")

    # Apply corrections
    corrections = label_review.get("corrections", []) if label_review else []
    correction_map = {c["defect_id"]: c for c in corrections}
    final_defects = []
    for d in defects:
        if d.get("defect_id") in correction_map:
            c = correction_map[d["defect_id"]]
            final_defects.append({
                **d,
                "defect_type": c.get("defect_type", d["defect_type"]),
                "human_corrected": True,
                "original_label": d["defect_type"],
            })
        else:
            final_defects.append(d)

    if db is not None:
        from app.db.models import Defect, Feedback

        for d in final_defects:
            row = Defect(
                defect_id=d.get("defect_id", ""),
                job_id=job_id,
                defect_type=d.get("defect_type", "unknown"),
                bbox=d.get("bbox"),
                size_mm2=d.get("size_mm2"),
                severity=d.get("severity"),
                confidence=d.get("confidence", 0.0),
                source=d.get("source", "yolo"),
                human_corrected=d.get("human_corrected", False),
                original_label=d.get("original_label"),
            )
            db.add(row)

        # Save feedback for L10 learning
        if any(d.get("human_corrected") for d in final_defects):
            fb = Feedback(
                job_id=job_id,
                kind="label",
                ai_value=[d for d in defects if not d.get("human_corrected")],
                human_value=final_defects,
            )
            db.add(fb)

        await db.commit()

    return {"defects": final_defects, "status": "RETRIEVAL"}


async def fast_path_report(state: InspectionState) -> dict:
    """Fast path: no defects → skip Stages 4-6, go to OK report."""
    logger.info('"node":"fast_path_report","job_id":"%s"', state.get("job_id"))
    return {"fast_path": True, "status": "REPORTING"}
