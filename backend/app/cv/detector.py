"""Stage 3 detectors behind one interface. YOLOv8 is real; SAM and Anomalib are deferred.

`detect(path)` returns [{cls, conf, bbox:[x1,y1,x2,y2], source}]. Manifest mode replays
labels from samples/manifest.json (keyed by file name) for demos without weights.
"""
import json
from functools import lru_cache
from pathlib import Path

from .. import config


@lru_cache(maxsize=2)
def _yolo(weights: str):
    from ultralytics import YOLO
    return YOLO(weights)


def reload_model() -> None:
    """Drop cached weights after a model promotion or rollback."""
    _yolo.cache_clear()


def _detect_yolo(path: Path) -> list[dict]:
    from .. import learning
    res = _yolo(str(learning.active_weights())).predict(str(path), conf=config.CONF_THRESHOLD, verbose=False)[0]
    names = res.names
    return [{"cls": names[int(b.cls)], "conf": round(float(b.conf), 4),
             "bbox": [round(float(v), 1) for v in b.xyxy[0].tolist()], "source": "yolo"}
            for b in res.boxes]


def _detect_manifest(path: Path) -> list[dict]:
    manifest = Path(config.ROOT / "samples" / "manifest.json")
    if not manifest.exists():
        return []
    return [{**d, "source": "manifest"} for d in json.loads(manifest.read_text()).get(path.name, [])]


def _detect_primary(path: Path) -> list[dict]:
    return _detect_manifest(path) if config.INSPECTION_MODE == "manifest" else _detect_yolo(path)


def _find_unseen(path: Path, known: list[dict], part_number: str | None) -> list[dict]:
    """Anomaly hotspots that no YOLO box explains become 'unknown_anomaly' detections.

    Confidence is capped under the label-review threshold on purpose: a defect the
    classifier has never seen must always be looked at by a person (the PDF's Anomalib step)."""
    if not config.ANOMALY_ENABLED:
        return []
    from . import anomaly
    model = anomaly.model_path(part_number)
    if model is None:
        return []
    import cv2
    res = anomaly.score(cv2.imread(str(path)), model)
    if not res["anomalous"] or not res["bbox"]:
        return []
    cx, cy = (res["bbox"][0] + res["bbox"][2]) / 2, (res["bbox"][1] + res["bbox"][3]) / 2
    if any(k["bbox"][0] <= cx <= k["bbox"][2] and k["bbox"][1] <= cy <= k["bbox"][3] for k in known):
        return []
    conf = round(min(config.LABEL_REVIEW_CONF - 0.05, 0.4 + 0.2 * (res["ratio"] - 1)), 3)
    return [{"cls": "unknown_anomaly", "conf": conf, "bbox": res["bbox"], "source": "anomaly",
             "anomaly_score": res["score"], "anomaly_ratio": res["ratio"]}]


def detect(path: Path, part_number: str | None = None) -> list[dict]:
    """Stage 3: parallel detectors on one image, merged. YOLO classifies, the anomaly model
    adds unseen defects, SAM turns every box into a mask."""
    from . import segmenter
    dets = _detect_primary(path)
    dets += _find_unseen(path, dets, part_number)
    return segmenter.segment(path, dets)


def severity(det: dict, img_shape: tuple) -> str:
    """Size-based severity: share of the image covered by the box."""
    h, w = img_shape[:2]
    x1, y1, x2, y2 = det["bbox"]
    frac = det.get("mask_frac")  # real defect area when SAM produced a mask
    if frac is None:
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
