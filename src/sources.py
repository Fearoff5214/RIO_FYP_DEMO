"""
Pluggable frame sources. Every source exposes the same tiny interface
(`read() -> frame | None`, `release()`) so the rest of the app doesn't care
whether frames come from a folder of images, a video file, a webcam, or
(later) an ESP32-CAM MJPEG stream.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


class FileSource:
    """Yields frames from either a folder of images or a single video file."""

    def __init__(self, path: str):
        self.path = Path(path)
        self._cap: Optional[cv2.VideoCapture] = None
        self._image_paths: list[Path] = []
        self._image_idx = 0

        if self.path.is_dir():
            self._image_paths = sorted(
                p for p in self.path.iterdir() if p.suffix.lower() in IMAGE_EXTS
            )
            if not self._image_paths:
                raise ValueError(f"No images found in folder: {self.path}")
        elif self.path.is_file():
            if self.path.suffix.lower() in IMAGE_EXTS:
                self._image_paths = [self.path]
            else:
                self._cap = cv2.VideoCapture(str(self.path))
                if not self._cap.isOpened():
                    raise ValueError(f"Could not open video file: {self.path}")
        else:
            raise FileNotFoundError(f"Path does not exist: {self.path}")

    def read(self) -> Optional[np.ndarray]:
        if self._cap is not None:
            ok, frame = self._cap.read()
            return frame if ok else None

        if self._image_idx >= len(self._image_paths):
            return None
        frame = cv2.imread(str(self._image_paths[self._image_idx]))
        self._image_idx += 1
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()


class WebcamSource:
    """Yields frames from a local webcam."""

    def __init__(self, camera_index: int = 0):
        self._cap = cv2.VideoCapture(camera_index)
        if not self._cap.isOpened():
            raise ValueError(f"Could not open webcam index {camera_index}")

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self._cap.read()
        return frame if ok else None

    def release(self) -> None:
        self._cap.release()


class Esp32Source:
    """
    Yields frames from an ESP32-CAM's MJPEG stream over HTTP.

    Not usable until Phase 3 hardware (ESP32-CAM running the project's
    firmware) exists - included now so `app.py` can offer it as a source
    option without further code changes once the hardware arrives.
    """

    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self._cap = cv2.VideoCapture(stream_url)
        if not self._cap.isOpened():
            raise ValueError(f"Could not open ESP32-CAM stream at {stream_url}")

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self._cap.read()
        return frame if ok else None

    def release(self) -> None:
        self._cap.release()
