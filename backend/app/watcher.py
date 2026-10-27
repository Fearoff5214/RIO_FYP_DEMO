"""Watch mode: start an inspection when a part is shown to the camera, with no button press.

`Presence` is the pure decision logic (feed it frames and timestamps). `Watcher` runs it on a
live camera in a background thread, draws a status banner (and optional live YOLO boxes) on the
preview, and starts a normal job when a part has been placed and held still.

Cycle: calibrating (learn the empty view) -> empty -> settling (part present, waiting for it
to stop moving) -> triggered (job started; wait here) -> empty again once the part is removed.
"""
import threading
import time
import uuid
from collections import deque

import cv2
import numpy as np

from . import camera, config

_W = 320  # analysis width


class Presence:
    def __init__(self, hold: float | None = None, min_frac: float | None = None,
                 diff_thr: float | None = None, calib: float = 1.0, clear: float = 1.0,
                 motion_thr: float = 4.0):
        self.hold = config.WATCH_HOLD_SECONDS if hold is None else hold
        self.min_frac = config.WATCH_PRESENCE_MIN if min_frac is None else min_frac
        self.diff_thr = config.WATCH_DIFF_THR if diff_thr is None else diff_thr
        self.calib, self.clear, self.motion_thr = calib, clear, motion_thr
        self.state = "calibrating"
        self.frac = 0.0
        self.progress = 0.0
        self._bg = None
        self._n = 0
        self._t0 = None
        self._prev = None
        self._still_since = None
        self._absent_since = None

    @staticmethod
    def _prep(frame: np.ndarray) -> np.ndarray:
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        h = max(1, int(g.shape[0] * _W / g.shape[1]))
        return cv2.GaussianBlur(cv2.resize(g, (_W, h)), (5, 5), 0).astype(np.float32)

    def reset(self) -> None:
        self.__init__(self.hold, self.min_frac, self.diff_thr, self.calib, self.clear, self.motion_thr)

    def update(self, frame: np.ndarray, t: float) -> bool:
        """Feed one frame. Returns True exactly once per part, when it should be inspected."""
        g = self._prep(frame)
        if self.state == "calibrating":
            self._t0 = t if self._t0 is None else self._t0
            self._bg = g.copy() if self._bg is None else self._bg + (g - self._bg) / (self._n + 1)
            self._n += 1
            if t - self._t0 >= self.calib and self._n >= 5:
                self.state = "empty"
            self._prev = g
            return False
        # the camera's auto-exposure shifts everything a little: remove the median offset
        d = g - self._bg
        d -= np.median(d)
        fg = (np.abs(d) > self.diff_thr).astype(np.uint8)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        self.frac = float(fg.mean())
        motion = float(np.abs(g - self._prev).mean())
        self._prev = g
        present = self.frac >= (self.min_frac * 0.5 if self.state in ("settling", "triggered") else self.min_frac)

        if self.state == "empty":
            self.progress = 0.0
            if present:
                self.state, self._still_since = "settling", None
            else:
                self._bg += 0.02 * (g - self._bg)  # follow slow lighting drift while nothing is there
        elif self.state == "settling":
            if not present:
                self.state, self.progress = "empty", 0.0
            elif motion >= self.motion_thr:
                self._still_since, self.progress = None, 0.0
            else:
                self._still_since = t if self._still_since is None else self._still_since
                self.progress = min(1.0, (t - self._still_since) / self.hold)
                if self.progress >= 1.0:
                    self.state, self._absent_since = "triggered", None
                    return True
        elif self.state == "triggered":
            if present:
                self._absent_since = None
            else:
                self._absent_since = t if self._absent_since is None else self._absent_since
                if t - self._absent_since >= self.clear:
                    self.state, self.progress = "empty", 0.0
        return False


def sharpness(frame: np.ndarray) -> float:
    return float(cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


_COLORS = {"calibrating": (0, 165, 255), "empty": (160, 160, 160), "settling": (0, 215, 255),
           "triggered": (0, 200, 0), "error": (0, 0, 255)}
_TEXT = {"calibrating": "Learning empty view - keep the part out",
         "empty": "Ready - show a part",
         "settling": "Hold still...",
         "triggered": "Part captured - remove it for the next one",
         "error": "Camera error"}


class Watcher:
    def __init__(self, part_number: str, device: int, live_boxes: bool = True, presence: Presence | None = None):
        self.part_number, self.device, self.live_boxes = part_number, device, live_boxes
        self.presence = presence or Presence()
        self.jobs: list[str] = []
        self.error = ""
        self.stopped = threading.Event()
        self._jpeg: bytes | None = None
        self._boxes: list[dict] = []
        self._frames: deque = deque(maxlen=5)
        self._thread = threading.Thread(target=self._run, daemon=True, name="watcher")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.stopped.set()
        self._thread.join(timeout=5)

    @property
    def running(self) -> bool:
        return self._thread.is_alive() and not self.stopped.is_set()

    def status(self) -> dict:
        p = self.presence
        return {"running": self.running, "state": "error" if self.error else p.state,
                "part_number": self.part_number, "device": self.device, "progress": round(p.progress, 2),
                "coverage": round(p.frac, 3), "jobs": self.jobs[-20:], "error": self.error,
                "live_boxes": self.live_boxes}

    def jpeg(self) -> bytes | None:
        return self._jpeg

    def _inspect(self, frames: list[np.ndarray]) -> None:
        from .graph import workflow
        job_id = uuid.uuid4().hex[:12]
        self.jobs.append(job_id)
        try:
            dest = config.UPLOAD_DIR / job_id
            dest.mkdir(parents=True, exist_ok=True)
            best = max(frames, key=sharpness)
            path = dest / f"watch{self.device}_{int(time.time() * 1000)}.png"
            cv2.imwrite(str(path), best)
            workflow.start_job(self.part_number, [str(path)], job_id=job_id,
                               source={"type": "camera", "device": self.device, "mode": "watch"},
                               recipe=dict(camera.DEFAULT_RECIPE))
        except Exception as e:  # keep watching; the job list shows which one failed
            self.error = f"job {job_id} failed to start: {e}"

    def _overlay(self, frame: np.ndarray) -> bytes | None:
        img = frame.copy()
        for b in self._boxes:
            x1, y1, x2, y2 = map(int, b["bbox"])
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(img, f'{b["cls"]} {b["conf"]:.2f}', (x1, max(15, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        st = self.presence.state
        cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
        cv2.putText(img, _TEXT[st], (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, _COLORS[st], 2)
        if st == "settling":
            cv2.rectangle(img, (0, 34), (int(img.shape[1] * self.presence.progress), 40), _COLORS[st], -1)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return buf.tobytes() if ok else None

    def _run(self) -> None:
        last_boxes = 0.0
        while not self.stopped.is_set():
            try:
                frame = camera.grab(self.device, settle_frames=0)
            except camera.CameraError as e:
                self.error = str(e)
                self.stopped.set()
                break
            now = time.time()
            if self.presence.state in ("settling", "triggered"):
                self._frames.append(frame)
            else:
                self._frames.clear()
            if self.live_boxes and self.presence.state in ("settling", "triggered") and now - last_boxes > 0.5:
                last_boxes = now
                try:
                    from .cv import detector
                    self._boxes = detector.detect_frame(frame)
                except Exception:
                    self._boxes = []  # the overlay is cosmetic; never stop watching because of it
            elif self.presence.state == "empty":
                self._boxes = []
            if self.presence.update(frame, now) and self._frames:
                threading.Thread(target=self._inspect, args=(list(self._frames),), daemon=True).start()
            self._jpeg = self._overlay(frame)
            time.sleep(0.05)

    def mjpeg(self):
        while self.running:
            jpg = self._jpeg
            if jpg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            time.sleep(0.1)


_watcher: Watcher | None = None
_lock = threading.Lock()


def start(part_number: str, device: int, live_boxes: bool = True) -> Watcher:
    global _watcher
    with _lock:
        if _watcher and _watcher.running:
            raise RuntimeError("already watching")
        _watcher = Watcher(part_number, device, live_boxes)
        _watcher.start()
        return _watcher


def stop() -> None:
    global _watcher
    with _lock:
        if _watcher:
            _watcher.stop()


def current() -> Watcher | None:
    return _watcher
