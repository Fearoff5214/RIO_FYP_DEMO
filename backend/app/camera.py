"""Stage 1 camera: phone -> laptop via Iriun Webcam, which presents the phone as a normal
DirectShow webcam. Frames are grabbed with OpenCV by device index.

`recipe` is the Stage 1 "camera recipe" (exposure, brightness, focus, resolution). Whether a
property takes effect depends on the driver, so every change is read back and reported.
One capture object per device is shared by the MJPEG preview and still captures.
"""
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from . import config

_BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
_caps: dict[int, cv2.VideoCapture] = {}
_lock = threading.RLock()

DEFAULT_RECIPE = {"width": config.CAMERA_WIDTH, "height": config.CAMERA_HEIGHT}


class CameraError(RuntimeError):
    pass


def _open(device: int) -> cv2.VideoCapture:
    with _lock:
        cap = _caps.get(device)
        if cap is not None and cap.isOpened():
            return cap
        cap = cv2.VideoCapture(device, _BACKEND)
        if not cap.isOpened():
            raise CameraError(f"camera {device} not available (is Iriun running on phone and laptop?)")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
        _caps[device] = cap
        return cap


def release(device: int | None = None) -> None:
    with _lock:
        for d in [device] if device is not None else list(_caps):
            cap = _caps.pop(d, None)
            if cap:
                cap.release()


def list_devices(max_index: int = 6) -> list[dict]:
    out = []
    for i in range(max_index):
        with _lock:
            cap = _caps.get(i) or cv2.VideoCapture(i, _BACKEND)
            ok = cap.isOpened() and cap.read()[0]
            info = {"index": i, "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} if ok else None
            if i not in _caps:
                cap.release()
        if info:
            out.append(info)
    return out


def apply_recipe(device: int, recipe: dict) -> dict:
    """Set camera properties and return what the driver actually accepted."""
    props = {"width": cv2.CAP_PROP_FRAME_WIDTH, "height": cv2.CAP_PROP_FRAME_HEIGHT,
             "exposure": cv2.CAP_PROP_EXPOSURE, "brightness": cv2.CAP_PROP_BRIGHTNESS,
             "contrast": cv2.CAP_PROP_CONTRAST, "focus": cv2.CAP_PROP_FOCUS}
    cap = _open(device)
    applied = {}
    with _lock:
        if "auto_exposure" in recipe:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75 if recipe["auto_exposure"] else 0.25)
        if "autofocus" in recipe:
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 1 if recipe["autofocus"] else 0)
        for k, prop in props.items():
            if k in recipe:
                cap.set(prop, recipe[k])
                applied[k] = cap.get(prop)
    return applied


def grab(device: int, settle_frames: int = 3) -> np.ndarray:
    """Latest frame; a few frames are discarded first so auto-exposure can settle."""
    cap = _open(device)
    with _lock:
        for _ in range(settle_frames):
            cap.grab()
        ok, frame = cap.read()
    if not ok or frame is None:
        raise CameraError(f"camera {device} returned no frame")
    return frame


def capture(device: int, dest_dir: Path, n_frames: int = 1, recipe: dict | None = None,
            delay: float = 0.3) -> list[str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    if recipe:
        apply_recipe(device, recipe)
    paths = []
    for i in range(n_frames):
        p = dest_dir / f"cam{device}_{int(time.time() * 1000)}_{i}.png"
        cv2.imwrite(str(p), grab(device))
        paths.append(str(p))
        if i < n_frames - 1:
            time.sleep(delay)
    return paths


def adjust_recipe(recipe: dict, problems: list[str]) -> dict:
    """Next recipe to try after a failed quality check (loop L2 with a live camera)."""
    r = dict(recipe)
    if "exposure" in problems or "glare" in problems:
        r["auto_exposure"] = True  # let the sensor re-meter; then nudge brightness the right way
        r["brightness"] = r.get("brightness", 128) + (-20 if "glare" in problems else 20)
    if "blur" in problems:
        r["autofocus"] = True
    return r


def mjpeg(device: int):
    """Generator of multipart JPEG frames for the browser preview."""
    while True:
        try:
            ok, buf = cv2.imencode(".jpg", grab(device, settle_frames=0), [cv2.IMWRITE_JPEG_QUALITY, 80])
        except CameraError:
            return
        if ok:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        time.sleep(0.05)
