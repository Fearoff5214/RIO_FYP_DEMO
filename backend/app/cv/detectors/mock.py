"""
Mock detector — returns deterministic defect detections for CI/dev.
Always returns the 4 defect classes matching the infographic scenario.
"""
from __future__ import annotations

import uuid


class MockDetector:
    """Deterministic mock: Dent, Scratch, Crack, Deformation."""

    SOURCE = "yolo"

    MOCK_DEFECTS = [
        {
            "defect_type": "scratch",
            "confidence": 0.92,
            "bbox": {"x1": 100, "y1": 80, "x2": 240, "y2": 120},
            "size_px": 3200,
            "source": "yolo",
        },
        {
            "defect_type": "dent",
            "confidence": 0.88,
            "bbox": {"x1": 300, "y1": 200, "x2": 380, "y2": 280},
            "size_px": 6400,
            "source": "yolo",
        },
        {
            "defect_type": "crack",
            "confidence": 0.76,  # below 0.85 → triggers label review
            "bbox": {"x1": 450, "y1": 100, "x2": 520, "y2": 180},
            "size_px": 5600,
            "source": "yolo",
        },
        {
            "defect_type": "deformation",
            "confidence": 0.91,
            "bbox": {"x1": 150, "y1": 300, "x2": 350, "y2": 420},
            "size_px": 40000,
            "source": "yolo",
        },
    ]

    async def detect(self, images: list[dict]) -> list[dict]:
        """Return mock detections with unique IDs."""
        return [
            {**d, "defect_id": str(uuid.uuid4())}
            for d in self.MOCK_DEFECTS
        ]
