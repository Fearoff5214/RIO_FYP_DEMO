"""Mock camera: returns synthetic or sample images deterministically."""
from __future__ import annotations

import os
from pathlib import Path


class MockCamera:
    """Deterministic mock camera for CI and development."""

    SAMPLES_DIR = Path(__file__).resolve().parents[5] / "samples"

    async def capture(self, recipe: dict) -> list[dict]:
        """Return a list of image dicts using sample files if available."""
        angles = recipe.get("angles", ["top"])
        images = []

        sample_files = sorted(
            p for p in self.SAMPLES_DIR.glob("*.jpg")
            if "defect" in p.name or "clean" in p.name
        ) if self.SAMPLES_DIR.exists() else []

        for i, angle in enumerate(angles):
            if sample_files:
                path = sample_files[i % len(sample_files)]
                uri = str(path)
            else:
                uri = f"mock://image_{angle}"

            images.append({
                "uri": uri,
                "angle": angle,
                "kind": "raw",
                "quality_score": 0.95,
                "meta": {"source": "mock", "recipe": recipe},
            })

        return images

    def release(self):
        pass
