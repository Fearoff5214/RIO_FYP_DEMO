"""YOLO defect detector using Ultralytics."""
from __future__ import annotations

import uuid
from pathlib import Path


class YoloDetector:
    """Wraps Ultralytics YOLO for defect detection."""

    CLASS_MAP = {
        "scratches": "scratch",
        "scratch": "scratch",
        "dent": "dent",
        "crack": "crack",
        "deformation": "deformation",
        "patches": "dent",
        "inclusion": "crack",
        "pitted_surface": "dent",
        "rolled-in_scale": "scratch",
        "crazing": "deformation",
    }

    def __init__(self, weights_path: str):
        from ultralytics import YOLO
        self.model = YOLO(weights_path)
        self.class_names = self.model.names

    async def detect(self, images: list[dict]) -> list[dict]:
        """Run YOLO inference on all images."""
        import cv2
        import numpy as np

        detections = []
        for img_info in images:
            uri = img_info.get("uri", "")
            if uri.startswith("mock://"):
                continue

            path = Path(uri)
            if not path.exists():
                continue

            frame = cv2.imread(str(path))
            if frame is None:
                continue

            results = self.model.predict(frame, conf=0.10, verbose=False)[0]
            for box in results.boxes:
                class_idx = int(box.cls[0])
                raw_name = self.class_names.get(class_idx, "unknown")
                mapped = self.CLASS_MAP.get(raw_name.lower(), raw_name)
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append({
                    "defect_id": str(uuid.uuid4()),
                    "defect_type": mapped,
                    "confidence": float(box.conf[0]),
                    "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "size_px": (x2 - x1) * (y2 - y1),
                    "source": "yolo",
                })

        return detections
