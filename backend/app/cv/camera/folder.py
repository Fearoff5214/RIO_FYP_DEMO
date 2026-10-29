"""Folder-watch camera: reads images from a directory."""
from __future__ import annotations

from pathlib import Path


class FolderCamera:
    """Camera adapter that reads images from a local folder."""

    SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp"}

    def __init__(self, folder: str):
        self.folder = Path(folder)

    async def capture(self, recipe: dict) -> list[dict]:
        angles = recipe.get("angles", ["top"])
        files = sorted(
            p for p in self.folder.glob("*")
            if p.suffix.lower() in self.SUPPORTED
        )

        images = []
        for i, angle in enumerate(angles):
            if i < len(files):
                path = files[i]
            elif files:
                path = files[i % len(files)]
            else:
                continue

            images.append({
                "uri": str(path),
                "angle": angle,
                "kind": "raw",
                "quality_score": None,
                "meta": {"source": "folder"},
            })

        return images

    def release(self):
        pass
