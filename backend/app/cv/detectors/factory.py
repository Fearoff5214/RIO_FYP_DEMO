"""Detector ensemble factory."""
from __future__ import annotations

from app.core.config import get_config


class DetectorEnsemble:
    def __init__(self, detectors: list):
        self._detectors = detectors

    async def detect_all(self, images: list[dict]) -> list[dict]:
        """Run all detectors and combine raw results."""
        import asyncio

        all_detections = []
        tasks = [det.detect(images) for det in self._detectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                continue
            all_detections.extend(result)

        return all_detections


def get_detector_ensemble(cfg=None) -> DetectorEnsemble:
    """Build the detector ensemble based on mode and config."""
    if cfg is None:
        cfg = get_config()

    detectors = []

    if cfg.is_mock:
        from app.cv.detectors.mock import MockDetector
        detectors.append(MockDetector())
    else:
        # Real mode: try to load YOLO
        yolo_path = (cfg.get("detection", "models", "yolo") or "models/best.pt")
        from pathlib import Path
        if Path(yolo_path).exists():
            try:
                from app.cv.detectors.yolo import YoloDetector
                detectors.append(YoloDetector(yolo_path))
            except ImportError:
                from app.cv.detectors.mock import MockDetector
                detectors.append(MockDetector())
        else:
            from app.cv.detectors.mock import MockDetector
            detectors.append(MockDetector())

        # SAM
        sam_path = cfg.get("detection", "models", "sam") or ""
        if Path(sam_path).exists():
            try:
                from app.cv.detectors.sam import SamSegmenter
                detectors.append(SamSegmenter(sam_path))
            except (ImportError, Exception):
                pass

        # Anomalib
        anomalib_path = cfg.get("detection", "models", "anomalib") or ""
        if Path(anomalib_path).exists():
            try:
                from app.cv.detectors.anomalib_detector import AnomalibDetector
                detectors.append(AnomalibDetector(anomalib_path))
            except (ImportError, Exception):
                pass

    return DetectorEnsemble(detectors)
