"""Stage 2 — Dimensional Check + Human Gate 1 nodes."""
from __future__ import annotations

from app.core.logging import get_logger
from app.workflow.state import InspectionState

logger = get_logger(__name__)


async def parse_drawing(state: InspectionState) -> dict:
    """Parse DXF/PDF drawing → extract features, dimensions, tolerances."""
    from app.cv.drawing.dxf_parser import parse_dxf
    from app.cv.drawing.pdf_parser import parse_pdf

    part_master = state.get("part_master", {}) or {}
    drawing_uri = part_master.get("drawing_uri", "")
    logger.info('"node":"parse_drawing","uri":"%s"', drawing_uri)

    if drawing_uri.endswith(".dxf") or drawing_uri.endswith(".DXF"):
        drawing = parse_dxf(drawing_uri)
    elif drawing_uri.endswith(".pdf") or drawing_uri.endswith(".PDF"):
        drawing = parse_pdf(drawing_uri)
    else:
        # Use synthetic drawing as fallback
        from app.cv.drawing.synthetic import generate_synthetic_drawing
        drawing = generate_synthetic_drawing(part_master.get("part_number", "MS-4505-001"))

    return {"drawing": drawing, "status": "DIMENSIONAL"}


async def detect_features(state: InspectionState) -> dict:
    """Detect geometric features (holes, edges, contours) in images using OpenCV."""
    from app.cv.features import detect_features as _detect

    images = state.get("images", []) or []
    drawing = state.get("drawing", {}) or {}
    part_master = state.get("part_master", {}) or {}
    calibration = part_master.get("calibration", {}) or {}

    logger.info('"node":"detect_features","n_images":%d', len(images))
    features = await _detect(images, drawing, calibration)
    return {"drawing": {**drawing, "detected_features": features}}


async def measure_mm(state: InspectionState) -> dict:
    """Measure detected features in mm using calibration."""
    from app.cv.measure import measure_features

    drawing = state.get("drawing", {}) or {}
    part_master = state.get("part_master", {}) or {}
    calibration = part_master.get("calibration", {}) or {}

    logger.info('"node":"measure_mm"')
    measurements = await measure_features(drawing, calibration)
    return {"measurements": measurements}


async def compare_drawing(state: InspectionState) -> dict:
    """Compare measurements vs drawing tolerances."""
    from app.cv.measure import compare_with_drawing

    measurements = state.get("measurements", []) or []
    drawing = state.get("drawing", {}) or {}

    logger.info('"node":"compare_drawing","n_measurements":%d', len(measurements))
    results = compare_with_drawing(measurements, drawing)
    return {"measurements": results}


async def set_dim_status(state: InspectionState) -> dict:
    """Set PASS/FAIL based on tolerance check."""
    measurements = state.get("measurements", []) or []
    all_pass = all(m.get("within_tolerance", True) for m in measurements)
    status = "PASS" if all_pass else "FAIL"
    logger.info('"node":"set_dim_status","status":"%s"', status)
    return {"dimensional_status": status, "status": "AWAIT_GATE1"}


async def gate1_engineer(state: InspectionState) -> dict:
    """
    Human Gate 1 — interrupt for engineer review.
    The LangGraph interrupt() pauses here until resumed via API.
    """
    from langgraph.types import interrupt

    measurements = state.get("measurements", []) or []
    dim_status = state.get("dimensional_status", "UNKNOWN")
    overlay_uri = state.get("dimensional_overlay_uri", "")
    job_id = state.get("job_id", "")

    logger.info('"node":"gate1_engineer","job_id":"%s"', job_id)

    # Build overlay image for review
    await _build_overlay(state)

    payload = {
        "gate": "GATE1",
        "job_id": job_id,
        "dimensional_status": dim_status,
        "measurements": measurements,
        "overlay_uri": state.get("dimensional_overlay_uri", ""),
        "message": "Please review dimensional results and confirm or reject.",
    }

    # interrupt() suspends the graph; resumed by POST /gates/1/{job_id}
    decision = interrupt(payload)
    return {"gate1": decision, "status": "GATE1_DECIDED"}


async def _build_overlay(state: InspectionState) -> None:
    """Generate annotated overlay image asynchronously (best-effort)."""
    try:
        from app.cv.measure import build_overlay_image
        uri = await build_overlay_image(state)
        state["dimensional_overlay_uri"] = uri  # type: ignore[typeddict-item]
    except Exception as e:
        logger.warning('"node":"_build_overlay","error":"%s"', str(e))


async def lock_result(state: InspectionState) -> dict:
    """Lock dimensional result after gate confirmation/override."""
    gate1 = state.get("gate1", {}) or {}
    # Apply any overrides from engineer
    overrides = gate1.get("overrides", []) or []
    measurements = state.get("measurements", []) or []
    if overrides:
        override_map = {o["feature_id"]: o for o in overrides}
        measurements = [
            {**m, "within_tolerance": override_map[m["feature_id"]]["within_tolerance"]}
            if m["feature_id"] in override_map else m
            for m in measurements
        ]
    return {"measurements": measurements, "status": "DIM_LOCKED"}


async def save_dim(state: InspectionState, *, db=None) -> dict:
    """Persist dimension_result rows and gate_decision row."""
    if db is None:
        return {"status": "DEFECT_DETECTION"}

    from datetime import datetime, timezone
    from app.db.models import DimensionResult, GateDecision

    job_id = state.get("job_id", "")
    measurements = state.get("measurements", []) or []
    gate1 = state.get("gate1", {}) or {}

    for m in measurements:
        row = DimensionResult(
            job_id=job_id,
            feature_id=m.get("feature_id", ""),
            feature_type=m.get("feature_type", "unknown"),
            nominal=m.get("nominal", 0.0),
            tol_plus=m.get("tol_plus", 0.1),
            tol_minus=m.get("tol_minus", 0.1),
            measured=m.get("measured", 0.0),
            deviation=m.get("deviation", 0.0),
            within_tolerance=m.get("within_tolerance", True),
        )
        db.add(row)

    gd = GateDecision(
        job_id=job_id,
        gate="GATE1",
        reviewer_id=gate1.get("reviewer_id"),
        decision=gate1.get("decision"),
        reason_code=gate1.get("reason_code"),
        comments=gate1.get("comments"),
        payload=gate1,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(gd)
    await db.commit()

    return {"status": "DEFECT_DETECTION"}


async def manual_measurement(state: InspectionState) -> dict:
    """L3 exhausted — flag for manual measurement."""
    flags = list(state.get("flags", []) or [])
    if "manual_measurement" not in flags:
        flags.append("manual_measurement")
    return {"flags": flags, "status": "DEFECT_DETECTION"}
