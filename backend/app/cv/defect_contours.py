"""Turn detector boxes into tight defect outlines for live overlay."""
from __future__ import annotations

import cv2
import numpy as np

_MIN_AREA_FRACTION = 0.05


def _box_polygon(x1: int, y1: int, x2: int, y2: int) -> list[list[int]]:
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def refine_contour(frame: np.ndarray, bbox: dict) -> list[list[int]]:
    """Return an outline polygon hugging the defect inside its bbox.

    Segments pixels that differ from the local background (large-kernel blur)
    and keeps the largest blob. Falls back to the box corners when no usable
    blob is found.
    """
    h, w = frame.shape[:2]
    x1 = max(0, int(bbox["x1"])); y1 = max(0, int(bbox["y1"]))
    x2 = min(w, int(bbox["x2"])); y2 = min(h, int(bbox["y2"]))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return _box_polygon(x1, y1, x2, y2)

    pad = max(8, int(0.25 * max(x2 - x1, y2 - y1)))
    rx1, ry1 = max(0, x1 - pad), max(0, y1 - pad)
    rx2, ry2 = min(w, x2 + pad), min(h, y2 + pad)
    gray = cv2.cvtColor(frame[ry1:ry2, rx1:rx2], cv2.COLOR_BGR2GRAY)
    k = max(3, (min(gray.shape) // 2) | 1)
    background = cv2.medianBlur(gray, min(k, 255))
    diff = cv2.absdiff(cv2.GaussianBlur(gray, (3, 3), 0), background)
    _, mask = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Only the detected box may contribute to the mask.
    box_mask = np.zeros_like(mask)
    box_mask[y1 - ry1:y2 - ry1, x1 - rx1:x2 - rx1] = 255
    mask = cv2.bitwise_and(mask, box_mask)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return _box_polygon(x1, y1, x2, y2)
    best = max(contours, key=cv2.contourArea)
    if cv2.contourArea(best) < _MIN_AREA_FRACTION * (x2 - x1) * (y2 - y1):
        return _box_polygon(x1, y1, x2, y2)
    eps = 0.015 * cv2.arcLength(best, True)
    approx = cv2.approxPolyDP(best, eps, True).reshape(-1, 2)
    if len(approx) < 3:
        return _box_polygon(x1, y1, x2, y2)
    return [[int(px) + rx1, int(py) + ry1] for px, py in approx]
