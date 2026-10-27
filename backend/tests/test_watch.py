import time

import numpy as np

from backend.app import camera, watcher
from backend.app.graph import workflow


def empty():
    return np.full((240, 320, 3), 90, np.uint8)


def with_part(shift=0):
    f = empty()
    f[60:180, 80 + shift:240 + shift] = 220  # a bright plate covering ~30% of the view
    return f


def feed(p, frames, t0=0.0, dt=0.1):
    events = []
    for i, f in enumerate(frames):
        events.append(p.update(f, t0 + i * dt))
    return events


def ready():
    p = watcher.Presence(hold=1.0, calib=0.5, clear=0.5)
    feed(p, [empty()] * 8)
    assert p.state == "empty"
    return p


def test_triggers_once_when_part_is_held_still_then_rearms_after_removal():
    p = ready()
    ev = feed(p, [with_part()] * 20, t0=1.0)
    assert ev.count(True) == 1 and p.state == "triggered"
    assert feed(p, [with_part()] * 20, t0=3.0).count(True) == 0  # same part: no second job
    feed(p, [empty()] * 10, t0=5.0)
    assert p.state == "empty"
    assert feed(p, [with_part()] * 20, t0=7.0).count(True) == 1  # next part


def test_moving_part_does_not_trigger_until_it_stops():
    p = ready()
    moving = [with_part(shift=(i % 2) * 40) for i in range(20)]
    assert not any(feed(p, moving, t0=1.0))
    assert p.state == "settling"
    assert any(feed(p, [with_part()] * 20, t0=4.0))


def test_empty_view_and_brightness_drift_never_trigger():
    p = ready()
    drift = [np.clip(empty().astype(int) + i, 0, 255).astype(np.uint8) for i in range(30)]
    assert not any(feed(p, drift, t0=1.0))
    assert p.state == "empty"


def test_small_object_below_threshold_is_ignored():
    p = ready()
    f = empty()
    f[10:20, 10:20] = 250
    assert not any(feed(p, [f] * 30, t0=1.0))


class FakeCam:
    def __init__(self):
        self.frame = empty()

    def __call__(self, device, settle_frames=3):
        return self.frame.copy()


def test_watcher_starts_a_job_from_a_shown_part(env, monkeypatch, detections):
    cam = FakeCam()
    monkeypatch.setattr(camera, "grab", cam)
    started = []
    monkeypatch.setattr(workflow, "start_job", lambda part, paths, **kw: started.append((part, paths, kw)))
    w = watcher.Watcher("SM-1001", 0, live_boxes=False, presence=watcher.Presence(hold=0.3, calib=0.3, clear=0.3))
    w.start()
    try:
        time.sleep(0.8)
        assert w.status()["state"] == "empty"
        cam.frame = with_part()
        for _ in range(60):
            if started:
                break
            time.sleep(0.1)
        assert len(started) == 1
        part, paths, kw = started[0]
        assert part == "SM-1001" and len(paths) == 1 and kw["source"]["mode"] == "watch"
        assert w.status()["jobs"] and w.jpeg()
    finally:
        w.stop()


def test_watcher_reports_camera_failure(env, monkeypatch):
    def boom(device, settle_frames=3):
        raise camera.CameraError("camera 9 not available")
    monkeypatch.setattr(camera, "grab", boom)
    w = watcher.Watcher("SM-1001", 9, live_boxes=False)
    w.start()
    time.sleep(0.5)
    assert w.status()["state"] == "error" and "camera 9" in w.status()["error"]
    assert not w.running
