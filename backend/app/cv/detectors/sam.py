"""SAM (Segment Anything Model) segmenter — stub with fallback."""
from __future__ import annotations


class SamSegmenter:
    """SAM segmenter. Falls back to mock if weights not available. See BLK-005."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None

    def _load(self):
        try:
            from segment_anything import SamPredictor, sam_model_registry
            model_type = "vit_b"
            sam = sam_model_registry[model_type](checkpoint=self.model_path)
            self._model = SamPredictor(sam)
        except ImportError:
            self._model = None

    async def detect(self, images: list[dict]) -> list[dict]:
        """Return mask-based detections. Stub: returns empty list."""
        return []
