"""Upload camera: accepts images already uploaded to object storage."""
from __future__ import annotations


class UploadCamera:
    """Camera adapter backed by uploaded file URIs (set externally via job trigger)."""

    _pending_uris: list[str] = []

    @classmethod
    def set_pending(cls, uris: list[str]) -> None:
        cls._pending_uris = list(uris)

    async def capture(self, recipe: dict) -> list[dict]:
        angles = recipe.get("angles", ["top"])
        images = []
        for i, uri in enumerate(self._pending_uris):
            angle = angles[i] if i < len(angles) else f"angle_{i}"
            images.append({
                "uri": uri,
                "angle": angle,
                "kind": "raw",
                "quality_score": None,
                "meta": {"source": "upload"},
            })
        return images

    def release(self):
        pass
