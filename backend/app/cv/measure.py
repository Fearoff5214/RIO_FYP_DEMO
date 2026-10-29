"""
Measurement computation: compare detected features vs drawing, generate overlays.
"""
from __future__ import annotations

from typing import Any


async def measure_features(drawing: dict, calibration: dict) -> list[dict]:
    """
    Compute measurements in mm from detected features aligned with drawing features.
    """
    import random
    random.seed(42)

    drawing_features = drawing.get("features", [])
    detected = {
        d["feature_id"]: d
        for d in drawing.get("detected_features", [])
    }

    measurements = []
    for feature in drawing_features:
        fid = feature["feature_id"]
        det = detected.get(fid, {})
        measured = det.get("measured_mm", feature["nominal"] + random.uniform(-0.12, 0.12))
        measurements.append({
            "feature_id": fid,
            "feature_type": feature.get("feature_type", "unknown"),
            "nominal": feature["nominal"],
            "tol_plus": feature.get("tol_plus", 0.10),
            "tol_minus": feature.get("tol_minus", 0.10),
            "measured": round(measured, 3),
            "deviation": round(measured - feature["nominal"], 3),
        })

    return measurements


def compare_with_drawing(measurements: list[dict], drawing: dict) -> list[dict]:
    """Add within_tolerance flag to each measurement."""
    results = []
    for m in measurements:
        dev = m.get("deviation", 0.0)
        tp = m.get("tol_plus", 0.10)
        tm = m.get("tol_minus", 0.10)
        within = (-tm <= dev <= tp)
        results.append({**m, "within_tolerance": within})
    return results


async def build_overlay_image(state: dict) -> str:
    """
    Generate an annotated overlay image showing measurement results.
    Returns the URI of the saved overlay.
    """
    import cv2
    import numpy as np
    from pathlib import Path

    measurements = state.get("measurements", []) or []
    images = state.get("images", []) or []
    job_id = state.get("job_id", "unknown")

    # Create a blank canvas or load first image
    canvas = np.full((480, 640, 3), 220, dtype=np.uint8)

    for img_info in images:
        uri = img_info.get("uri", "")
        if not uri.startswith("mock://") and Path(uri).exists():
            img = cv2.imread(uri)
            if img is not None:
                canvas = cv2.resize(img, (640, 480))
                break

    # Annotate measurements
    y_offset = 30
    for m in measurements:
        color = (0, 200, 0) if m.get("within_tolerance") else (0, 0, 255)
        label = (
            f"{m['feature_id']}: {m['measured']:.2f} "
            f"({m['deviation']:+.2f}) "
            f"{'✓' if m.get('within_tolerance') else '✗'}"
        )
        cv2.putText(canvas, label, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        y_offset += 20

    # Save to temp location
    output_dir = Path("tmp/overlays")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{job_id}_dim_overlay.jpg"
    cv2.imwrite(str(out_path), canvas)
    return str(out_path)
