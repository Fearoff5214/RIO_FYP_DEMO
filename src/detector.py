"""
Loads a trained YOLO model once and runs inference on frames, returning a
small, framework-agnostic Detection type instead of leaking Ultralytics'
result objects into the rest of the app.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO


@dataclass
class Detection:
    class_name: str
    confidence: float
    xyxy: tuple[float, float, float, float]  # xmin, ymin, xmax, ymax in pixels


class Detector:
    def __init__(self, weights_path: str):
        self.model = YOLO(weights_path)
        self.class_names = self.model.names

    def detect(self, frame: np.ndarray, conf_threshold: float = 0.25) -> list[Detection]:
        results = self.model.predict(frame, conf=conf_threshold, verbose=False)[0]

        detections = []
        for box in results.boxes:
            class_idx = int(box.cls[0])
            detections.append(
                Detection(
                    class_name=self.class_names[class_idx],
                    confidence=float(box.conf[0]),
                    xyxy=tuple(box.xyxy[0].tolist()),
                )
            )
        return detections
