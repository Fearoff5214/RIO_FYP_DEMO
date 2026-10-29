"""Fusion of multi-detector outputs using class-aware NMS / WBF."""
from __future__ import annotations

from typing import Any


def _iou(b1: dict, b2: dict) -> float:
    """Compute IoU between two bounding boxes."""
    x1 = max(b1["x1"], b2["x1"])
    y1 = max(b1["y1"], b2["y1"])
    x2 = min(b1["x2"], b2["x2"])
    y2 = min(b1["y2"], b2["y2"])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    a1 = (b1["x2"] - b1["x1"]) * (b1["y2"] - b1["y1"])
    a2 = (b2["x2"] - b2["x1"]) * (b2["y2"] - b2["y1"])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def fuse_detections(
    detections: list[dict],
    weights: dict[str, float] | None = None,
    iou_threshold: float = 0.5,
) -> list[dict]:
    """
    Fuse detections from multiple sources using weighted NMS.
    Groups detections by class, merges overlapping boxes by source weights.
    """
    if not detections:
        return []

    weights = weights or {"yolo": 0.5, "sam": 0.2, "anomalib": 0.3}

    # Group by class
    by_class: dict[str, list[dict]] = {}
    for d in detections:
        cls = d.get("defect_type", "unknown")
        by_class.setdefault(cls, []).append(d)

    fused = []
    for cls, dets in by_class.items():
        # Sort by weighted confidence descending
        scored = sorted(
            dets,
            key=lambda d: d.get("confidence", 0) * weights.get(d.get("source", "yolo"), 0.5),
            reverse=True,
        )

        kept = []
        suppressed = set()
        for i, det in enumerate(scored):
            if i in suppressed:
                continue
            for j, other in enumerate(scored):
                if j <= i or j in suppressed:
                    continue
                bbox_i = det.get("bbox") or {}
                bbox_j = other.get("bbox") or {}
                if bbox_i and bbox_j and _iou(bbox_i, bbox_j) >= iou_threshold:
                    suppressed.add(j)
            kept.append(det)

        fused.extend(kept)

    return fused


def classify_and_measure_basic(
    detections: list[dict],
    calibration: dict,
    severity_rules: dict,
) -> tuple[list[dict], float]:
    """Classify defect types and compute sizes in mm²."""
    px_per_mm = calibration.get("px_per_mm", 10.0)
    result = []
    min_conf = 1.0

    for d in detections:
        bbox = d.get("bbox") or {}
        size_px = d.get("size_px", 0)
        if not size_px and bbox:
            size_px = max(0, (bbox.get("x2", 0) - bbox.get("x1", 0))) * \
                      max(0, (bbox.get("y2", 0) - bbox.get("y1", 0)))

        size_mm2 = round(size_px / (px_per_mm ** 2), 2) if px_per_mm > 0 else 0.0
        dtype = d.get("defect_type", "unknown")
        severity = severity_rules.get(dtype, "minor")
        conf = d.get("confidence", 0.0)
        min_conf = min(min_conf, conf)

        result.append({
            **d,
            "size_mm2": size_mm2,
            "severity": severity,
        })

    return result, min_conf if result else 1.0
