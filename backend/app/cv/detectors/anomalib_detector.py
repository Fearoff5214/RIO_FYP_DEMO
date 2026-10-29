"""Anomalib anomaly detector — stub with fallback. See BLK-006."""
from __future__ import annotations


class AnomalibDetector:
    """PatchCore/EfficientAD anomaly detector. Returns empty list if model missing."""

    def __init__(self, model_path: str):
        self.model_path = model_path

    async def detect(self, images: list[dict]) -> list[dict]:
        """Return anomaly detections. Stub: returns empty list."""
        return []
