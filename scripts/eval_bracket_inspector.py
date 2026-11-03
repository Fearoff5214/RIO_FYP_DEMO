"""Randomised evaluation of the bracket inspector on synthetic frames.

Generates frames with random defect type, size, position, lighting gain, sensor noise and JPEG
quality, resized to the browser's 480 px, then scores the inspector's output against the known
ground truth: frame-level precision / recall / F1 per defect class, localisation hit rate and
measurement error. Includes in-tolerance "good" frames as negatives.

This is a synthetic benchmark, not a measurement on real parts.
Run: py scripts/eval_bracket_inspector.py [frames_per_group] [seed]
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import bracket_variants as bv  # noqa: E402
import make_bracket_frames as mf  # noqa: E402
from app.cv.bracket_inspector import inspect_bracket  # noqa: E402

N_PER_GROUP = int(sys.argv[1]) if len(sys.argv) > 1 else 30
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
OUT = Path(__file__).resolve().parents[1] / "docs" / "demo" / "bracket_inspector_eval.json"
rng = np.random.default_rng(SEED)
CLASSES = ["crack", "scratch", "dent", "deformation", "length", "hole_dia", "hole_pos"]
S, OX, BOTTOM_TOP, BOTTOM_FRONT = mf.S, (640 - 120 * mf.S) / 2, 320 + 80 * mf.S / 2, 320 + 50 * mf.S / 2


def u(a, b):
    return float(rng.uniform(a, b))


def new_variant():
    return bv.Variant("t", "t")


def crack_path(center, ang, length, seed):
    p0 = (center[0] + 6.0 * math.cos(ang), center[1] + 6.0 * math.sin(ang))
    p1 = (center[0] + (6.0 + length) * math.cos(ang), center[1] + (6.0 + length) * math.sin(ang))
    return bv._jagged(p0, p1, seed=seed)


def make_case(group):
    """Return (variant, view, truth) where truth lists the ground-truth classes and locations."""
    v, view = new_variant(), "top"
    truth = {"classes": set(), "loc": {}, "values": {}}
    if group == "good":                                    # in-tolerance jitter only (should stay clean)
        v.length = 120 + u(-0.05, 0.05)
        v.base_holes = [[x + u(-0.04, 0.04), y + u(-0.04, 0.04), 12 + u(-0.025, 0.025)] for x, y in bv.BASE_HOLES]
        v.bend_deg = 90 + u(-0.2, 0.2)
        if rng.random() < 0.4:
            view = "front"
            v.flange_holes = [[x + u(-0.04, 0.04), z + u(-0.04, 0.04), 12 + u(-0.025, 0.025)] for x, z in bv.FLANGE_HOLES]
    elif group == "crack":
        if rng.random() < 0.65:
            hole = bv.BASE_HOLES[int(rng.integers(4))]
            ang = u(0, 2 * math.pi)
            path = crack_path(hole, ang, u(6, 14), int(rng.integers(1000)))
            v.cracks = [dict(plane="base", label="c", pts=path)]
            truth["loc"]["crack"] = path[len(path) // 2]
        else:
            view = "front"
            hole = bv.FLANGE_HOLES[int(rng.integers(2))]
            ang = u(0.15, math.pi - 0.15)                  # upward half-plane
            path = crack_path(hole, ang, u(6, 12), int(rng.integers(1000)))
            v.cracks = [dict(plane="flange", label="c", pts=path)]
            truth["loc"]["crack"] = path[len(path) // 2]
        truth["classes"].add("crack")
    elif group == "scratch":
        x0, y0, a = u(25, 70), u(26, 54), u(0, 2 * math.pi)
        seg = [u(18, 28), u(14, 24)]
        pts = [(x0, y0), (x0 + seg[0] * math.cos(a), y0 + seg[0] * math.sin(a))]
        a2 = a + u(-0.5, 0.5)
        pts.append((pts[1][0] + seg[1] * math.cos(a2), pts[1][1] + seg[1] * math.sin(a2)))
        pts = [(min(max(x, 14), 106), min(max(y, 14), 66)) for x, y in pts]
        v.scratches = [dict(pts=pts, width=0.9)]
        truth["classes"].add("scratch")
        truth["loc"]["scratch"] = pts[1]
    elif group == "dent":
        d = dict(x=u(32, 88), y=u(28, 52), r=u(5, 9), depth=1.0)
        v.dents = [d]
        truth["classes"].add("dent")
        truth["loc"]["dent"] = (d["x"], d["y"])
    elif group == "deformation":
        v.bend_deg = 90 + float(rng.choice([-1, 1])) * u(0.9, 3.0)
        truth["classes"].add("deformation")
        truth["values"]["bend"] = v.bend_deg
    elif group == "length":
        dl = float(rng.choice([-1, 1])) * u(0.2, 1.5)
        v.length = 120 + dl
        truth["classes"].add("length")
        truth["values"]["length"] = v.length
    elif group == "hole_dia":
        i = int(rng.integers(4))
        d = 12 + float(rng.choice([-1, 1])) * u(0.1, 0.7)
        v.base_holes = [[x, y, d if k == i else 12.0] for k, (x, y) in enumerate(bv.BASE_HOLES)]
        truth["classes"].add("hole_dia")
        truth["values"]["hole_dia"] = d
        truth["loc"]["hole_dia"] = bv.BASE_HOLES[i]
    elif group == "hole_pos":
        i = int(rng.integers(4))
        sh, a = u(0.2, 2.0), u(0, 2 * math.pi)
        v.base_holes = [[x + (sh * math.cos(a) if k == i else 0), y + (sh * math.sin(a) if k == i else 0), 12.0]
                        for k, (x, y) in enumerate(bv.BASE_HOLES)]
        truth["classes"].add("hole_pos")
        truth["values"]["hole_pos"] = sh
        truth["loc"]["hole_pos"] = (bv.BASE_HOLES[i][0] + sh * math.cos(a), bv.BASE_HOLES[i][1] + sh * math.sin(a))
    return v, view, truth


def render(v, view):
    fn = mf.top_frame if view == "top" else mf.front_frame
    img, _ = fn(v)
    gray = np.clip(img * u(0.85, 1.15) + rng.normal(0, u(0, 4), img.shape), 0, 255).astype(np.uint8)
    frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    frame = cv2.resize(frame, (480, 480), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(60, 91))])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def predicted_classes(defects):
    out = {}
    for d in defects:
        t, note = d["defect_type"], d.get("note") or ""
        if t == "size_mismatch":
            if note.startswith("length") or note.startswith("width") or note.startswith("height"):
                t = "length"
            elif "dia" in note:
                t = "hole_dia"
            else:
                t = "hole_pos"
            if t == "hole_dia" and "position" in note:        # one hole flagged for both
                out.setdefault("hole_pos", d)
        out.setdefault(t, d)
    return out


def px(view, x, y):
    base = BOTTOM_TOP if view == "top" else BOTTOM_FRONT
    return (OX + x * S) * 0.75, (base - y * S) * 0.75


def main():
    groups = ["good", "crack", "scratch", "dent", "deformation", "length", "hole_dia", "hole_pos"]
    stats = {c: dict(tp=0, fp=0, fn=0) for c in CLASSES}
    loc = defaultdict(lambda: [0, 0])                       # class -> [hits, total]
    err = defaultdict(list)
    per_group = {}
    fp_by_group = defaultdict(lambda: defaultdict(int))
    fn_by_group = defaultdict(lambda: defaultdict(int))
    times = []
    good_clean = 0
    for g in groups:
        hit = 0
        for _ in range(N_PER_GROUP):
            v, view, truth = make_case(g)
            frame = render(v, view)
            t0 = time.perf_counter()
            res = inspect_bracket(frame)
            times.append((time.perf_counter() - t0) * 1000)
            pred = predicted_classes(res or [])
            for c in CLASSES:
                gt, pr = c in truth["classes"], c in pred
                stats[c]["tp"] += gt and pr
                stats[c]["fp"] += (not gt) and pr
                stats[c]["fn"] += gt and (not pr)
                if pr and not gt:
                    fp_by_group[g][c] += 1
                if gt and not pr:
                    fn_by_group[g][c] += 1
            if g == "good":
                good_clean += not pred
            hit += (set(pred) == truth["classes"])
            for c, (gx, gy) in truth["loc"].items():
                if c in pred:
                    cx, cy = px(view, gx, gy)
                    b = pred[c]["bbox"]
                    loc[c][1] += 1
                    loc[c][0] += (b["x1"] - 6 <= cx <= b["x2"] + 6) and (b["y1"] - 6 <= cy <= b["y2"] + 6)
            nums = lambda d: [float(x) for x in re.findall(r"-?\d+\.\d+|-?\d+", d["note"])] if d.get("note") else []
            if "length" in truth["values"] and "length" in pred:
                err["length_mm"].append(abs(nums(pred["length"])[0] - truth["values"]["length"]))
            if "hole_dia" in truth["values"] and "hole_dia" in pred:
                m = re.search(r"dia (\d+\.\d+)", pred["hole_dia"]["note"])
                if m:
                    err["hole_dia_mm"].append(abs(float(m.group(1)) - truth["values"]["hole_dia"]))
            if "hole_pos" in truth["values"] and "hole_pos" in pred:
                m = re.search(r"off (\d+\.\d+)", pred["hole_pos"]["note"])
                if m:
                    err["hole_pos_mm"].append(abs(float(m.group(1)) - truth["values"]["hole_pos"]))
            if "bend" in truth["values"] and "deformation" in pred:
                m = re.search(r"bend (\d+\.\d+)", pred["deformation"]["note"])
                if m:
                    err["bend_deg"].append(abs(float(m.group(1)) - truth["values"]["bend"]))
        per_group[g] = hit / N_PER_GROUP
        print(f"{g:12s} exact-match frames: {hit}/{N_PER_GROUP}", flush=True)

    rows = {}
    for c in CLASSES:
        s = stats[c]
        p = s["tp"] / max(1, s["tp"] + s["fp"])
        r = s["tp"] / max(1, s["tp"] + s["fn"])
        rows[c] = dict(**{k: int(v) for k, v in s.items()}, precision=round(p, 3), recall=round(r, 3),
                       f1=round(2 * p * r / max(1e-9, p + r), 3),
                       localisation=(round(loc[c][0] / loc[c][1], 3) if loc[c][1] else None))
    tp = sum(stats[c]["tp"] for c in CLASSES)
    fp = sum(stats[c]["fp"] for c in CLASSES)
    fn = sum(stats[c]["fn"] for c in CLASSES)
    overall = dict(precision=round(tp / max(1, tp + fp), 3), recall=round(tp / max(1, tp + fn), 3))
    errors = {k: dict(mean=round(float(np.mean(v)), 3), p95=round(float(np.percentile(v, 95)), 3), max=round(float(np.max(v)), 3), n=len(v))
              for k, v in err.items()}
    result = dict(frames=N_PER_GROUP * len(groups), per_group=N_PER_GROUP, seed=SEED, classes=rows, overall=overall,
                  good_frames_clean=f"{good_clean}/{N_PER_GROUP}", measurement_error=errors,
                  inspector_ms=dict(mean=round(float(np.mean(times)), 1), p95=round(float(np.percentile(times, 95)), 1)),
                  exact_match_by_group=per_group,
                  false_alarms_by_group={g: dict(d) for g, d in fp_by_group.items()}, misses_by_group={g: dict(d) for g, d in fn_by_group.items()})
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
