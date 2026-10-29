"""Defect classification and severity measurement."""
from __future__ import annotations


def classify_and_measure(
    detections: list[dict],
    calibration: dict,
    severity_rules: dict,
) -> tuple[list[dict], float]:
    """Classify detections and return (classified_defects, min_confidence)."""
    from app.cv.detectors.fuse import classify_and_measure_basic
    return classify_and_measure_basic(detections, calibration, severity_rules)
