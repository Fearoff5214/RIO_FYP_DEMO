"""
GenICam/GigE camera stub.
Replace this with harvesters or pypylon when real hardware is available.
See docs/BLOCKERS.md BLK-003.
"""
from __future__ import annotations


class GenICamCamera:
    """Stub for industrial GenICam/GigE camera. Not yet implemented."""

    async def capture(self, recipe: dict) -> list[dict]:
        raise NotImplementedError(
            "GenICam camera not implemented. "
            "Set camera.adapter=mock or folder in config, "
            "or implement using harvesters/pypylon. See docs/BLOCKERS.md BLK-003."
        )

    def release(self):
        pass
