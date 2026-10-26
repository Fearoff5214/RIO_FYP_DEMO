"""Stage 3 detectors behind one interface. YOLOv8 is real; SAM and Anomalib are deferred.

`detect(path)` returns [{cls, conf, bbox:[x1,y1,x2,y2], source}]. Manifest mode replays
labels from samples/manifest.json (keyed by file name) for demos without weights.
"""
import json
from functools import lru_cache
from pathlib import Path

from .. import config


@lru_cache(maxsize=1)
def _yolo():
    from ultralytics import YOLO
    return YOLO(str(config.YOLO_WEIGHTS))


def _detect_yolo(path: Path) -> list[dict]:
    res = _yolo().predict(str(path), conf=config.CONF_THRESHOLD, verbose=False)[0]
    names = res.names
    return [{"cls": names[int(b.cls)], "conf": round(float(b.conf), 4),
             "bbox": [round(float(v), 1) for v in b.xyxy[0].tolist()], "source": "yolo"}
            for b in res.boxes]


def _detect_manifest(path: Path) -> list[dict]:
    manifest = Path(config.ROOT / "samples" / "manifest.json")
    if not manifest.exists():
        return []
    return [{**d, "source": "manifest"} for d in json.loads(manifest.read_text()).get(path.name, [])]


def detect(path: Path) -> list[dict]:
    return _detect_manifest(path) if config.INSPECTION_MODE == "manifest" else _detect_yolo(path)


def severity(det: dict, img_shape: tuple) -> str:
    """Size-based severity: share of the image covered by the box."""
    h, w = img_shape[:2]
    x1, y1, x2, y2 = det["bbox"]
    frac = max(0.0, (x2 - x1) * (y2 - y1)) / float(h * w)
    return "high" if frac > 0.10 else "medium" if frac > 0.02 else "low"


def fuse(dets: list[dict], iou_thr: float = 0.5) -> list[dict]:
    """Merge detectors: drop same-class boxes with high IoU, keeping the higher confidence."""
    def iou(a, b):
        ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
        iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
        inter = ix * iy
        union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
        return inter / union if union else 0.0

    kept: list[dict] = []
    for d in sorted(dets, key=lambda x: x["conf"], reverse=True):
        if not any(k["cls"] == d["cls"] and iou(k["bbox"], d["bbox"]) > iou_thr for k in kept):
            kept.append(d)
    return kept
