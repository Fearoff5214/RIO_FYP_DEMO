"""SAM defect masks. YOLO boxes are used as prompts, so SAM only has to outline what was found.

Weights download on first use (ultralytics). If SAM cannot load, `segment` returns the
detections unchanged and sets `sam_error` so the caller can raise a flag instead of failing.
"""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .. import config

sam_error: str | None = None


@lru_cache(maxsize=1)
def _model():
    from ultralytics import SAM
    return SAM(config.SAM_WEIGHTS)


def segment(path: Path, dets: list[dict]) -> list[dict]:
    """Add mask_area_px, mask_frac and a polygon (image coords) to each detection with a box."""
    global sam_error
    boxes = [d for d in dets if d.get("bbox")]
    if not config.SAM_ENABLED or not boxes:
        return dets
    try:
        res = _model()(str(path), bboxes=[d["bbox"] for d in boxes], verbose=False)[0]
        masks = res.masks
        if masks is None:
            return dets
        h, w = res.orig_shape
        for d, m, poly in zip(boxes, masks.data.cpu().numpy(), masks.xy):
            m = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) if m.shape != (h, w) else m
            area = int(m.sum())
            d["mask_area_px"] = area
            d["mask_frac"] = round(area / float(h * w), 5)
            d["polygon"] = [[round(float(x), 1), round(float(y), 1)] for x, y in poly[::max(1, len(poly) // 40)]]
        sam_error = None
    except Exception as e:  # weights missing, no network, OOM: degrade, don't fail the inspection
        sam_error = f"{type(e).__name__}: {e}"
    return dets
