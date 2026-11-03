"""Generate simulated camera frames of bracket MS-4505-001 for the demo.

Frames use the same variant geometry as the 3D/2D models and are written to samples/ so the
simulated camera cycles through them. Frames carry no markings or annotations: defects are
found at demo time by app.cv.bracket_inspector.

Run: py scripts/make_bracket_frames.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bracket_variants as bv  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
N = 640
S = 4.6                         # px per mm
rng = np.random.default_rng(7)


def background() -> np.ndarray:
    base = np.full((N, N), 46.0)
    yy, xx = np.mgrid[0:N, 0:N]
    base -= 14 * (((xx - N / 2) ** 2 + (yy - N / 2) ** 2) / (N / 2) ** 2)             # vignette
    base += rng.normal(0, 2.2, (N, N))
    return base


def brushed(shape, level=168.0, amp=9.0) -> np.ndarray:
    h, w = shape
    streaks = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), sigmaX=22, sigmaY=0.6)
    streaks = streaks / (streaks.std() + 1e-6) * amp
    grain = rng.normal(0, 3.0, (h, w))
    grad = np.linspace(8, -8, h)[:, None]
    return level + streaks + grain + grad


SS = 4   # supersampling for exact sub-pixel coverage of part, hole and rim masks


def poly_mask(pts) -> np.ndarray:
    big = np.zeros((N * SS, N * SS), np.uint8)
    p = (np.array(pts, float) + 0.5) * SS - 0.5                       # pixel-centre coords -> sub-pixel grid
    cv2.fillPoly(big, [np.round(p * 16).astype(np.int32)], 255, cv2.LINE_8, 4)
    return cv2.resize(big, (N, N), interpolation=cv2.INTER_AREA)


def circle_mask(cx, cy, r) -> np.ndarray:
    big = np.zeros((N * SS, N * SS), np.uint8)
    c = ((cx + 0.5) * SS - 0.5) * 16
    cv2.circle(big, (int(round(c)), int(round(((cy + 0.5) * SS - 0.5) * 16))), int(round(r * SS * 16)), 255, -1, cv2.LINE_8, 4)
    return cv2.resize(big, (N, N), interpolation=cv2.INTER_AREA)


def blend(img, layer, mask):
    a = (mask.astype(np.float32) / 255.0)
    return img * (1 - a) + layer * a


def finish(img: np.ndarray, path: Path):
    img = np.clip(img, 0, 255).astype(np.uint8)
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    img = cv2.GaussianBlur(img, (0, 0), 0.6)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 93])


def polygon_pts(geom, simplify=0.6):
    g = geom.simplify(simplify)
    return [[round(x, 1), round(y, 1)] for x, y in g.exterior.coords][:-1]


def defect_entry(kind, geom, pad=5):
    x1, y1, x2, y2 = geom.bounds
    return dict(defect_type=kind, bbox=dict(x1=x1 - pad, y1=y1 - pad, x2=x2 + pad, y2=y2 + pad),
                polygon=polygon_pts(geom.buffer(pad * 0.6)))


# ---- Top view -----------------------------------------------------------------------
def top_frame(v: bv.Variant):
    L = v.length
    ox, bottom = (N - bv.NOMINAL_L * S) / 2, N / 2 + bv.W * S / 2
    P = lambda x, y: (ox + x * S, bottom - y * S)
    img = background()
    part = poly_mask([P(0, 0), P(L, 0), P(L, bv.W), P(0, bv.W)])
    shadow = cv2.GaussianBlur(np.roll(np.roll(part, 9, 0), 7, 1), (0, 0), 9).astype(np.float32) / 255
    img = img * (1 - 0.55 * shadow)
    img = blend(img, brushed((N, N)), part)

    flange_h = bv.T if abs(v.bend_deg - 90) <= bv.BEND_TOL else bv.T + bv.H * math.sin(math.radians(v.bend_deg - 90))
    flange = poly_mask([P(0, 0), P(L, 0), P(L, flange_h), P(0, flange_h)])
    img = blend(img, np.full((N, N), 212.0) + rng.normal(0, 2, (N, N)), flange)
    cv2.line(img, tuple(map(int, P(0, bv.R_OUT))), tuple(map(int, P(L, bv.R_OUT))), 150, 1, cv2.LINE_AA)  # bend line
    edge = np.clip(part.astype(np.float32) - cv2.erode(part, np.ones((3, 3), np.uint8)).astype(np.float32), 0, 255) / 255
    img = img + 14 * edge

    defects = []
    for x, y, d in v.base_holes:
        cx, cy = P(x, y)
        hole = circle_mask(cx, cy, d / 2 * S)
        rim = cv2.subtract(circle_mask(cx, cy, d / 2 * S + 2.4), hole)
        img = blend(img, np.full((N, N), 205.0), rim)
        img = blend(img, background() * 0.6, hole)
    # size-mismatch markers (ground truth for the dimensional check)
    for (nx, ny), (x, y, d) in zip(bv.BASE_HOLES, v.base_holes):
        if abs(d - bv.HOLE_D) > bv.HOLE_TOL or math.hypot(x - nx, y - ny) > bv.LINEAR_TOL:
            cx, cy = P(x, y)
            defects.append(defect_entry("size_mismatch", Point(cx, cy).buffer(d / 2 * S), pad=8)
                           | dict(note=f"hole dia {d:.2f} at ({x:.1f},{y:.1f}) vs nominal {bv.HOLE_D:.2f} at ({nx:.0f},{ny:.0f})"))
    if abs(L - bv.NOMINAL_L) > bv.LINEAR_TOL:
        x1, y1 = P(L, 0); x2, y2 = P(L, bv.W)
        defects.append(defect_entry("size_mismatch", LineString([(x1, y1), (x2, y2)]).buffer(6), pad=2)
                       | dict(note=f"length {L:.2f} vs nominal {bv.NOMINAL_L:.2f}"))

    for c in v.cracks:
        if c["plane"] != "base":
            continue
        pts = [P(x, y) for x, y in c["pts"]]
        ov = img.copy()
        cv2.polylines(ov, [np.round(np.array(pts)).astype(np.int32)], False, 205, 4, cv2.LINE_AA)   # lifted edges
        cv2.polylines(ov, [np.round(np.array(pts)).astype(np.int32)], False, 14, 2, cv2.LINE_AA)    # dark fissure
        img = ov
        defects.append(defect_entry("crack", LineString(pts).buffer(3)))
    for d in v.dents:
        cx, cy = P(d["x"], d["y"])
        r = d["r"] * S * 1.25
        yy, xx = np.mgrid[0:N, 0:N]
        rr = np.hypot(xx - cx, yy - cy) / r
        prof = np.exp(-(rr ** 2) * 2.2)
        shade = -70 * prof * ((xx - cx) / (r + 1e-6)) - 45 * prof * ((yy - cy) / (r + 1e-6))
        img = img + shade * (rr < 1.4)
        defects.append(defect_entry("dent", Point(cx, cy).buffer(r * 0.9), pad=4))
    for sc in v.scratches:
        pts = np.round(np.array([P(x, y) for x, y in sc["pts"]])).astype(np.int32)
        cv2.polylines(img, [pts + np.array([0, 1])], False, 112, 2, cv2.LINE_AA)
        cv2.polylines(img, [pts], False, 232, 2, cv2.LINE_AA)
        defects.append(defect_entry("scratch", LineString(pts).buffer(3), pad=3))
    if abs(v.bend_deg - 90) > bv.BEND_TOL:
        x1, y1 = P(0, 0); x2, y2 = P(L, flange_h)
        defects.append(defect_entry("deformation", LineString([(x1, y1 - 2), (x2, y1 - 2)]).buffer(11), pad=2)
                       | dict(note=f"bend angle {v.bend_deg:.1f} vs 90.0 +/-{bv.BEND_TOL}"))
    return img, defects


# ---- Front view (flange face) ---------------------------------------------------------
def front_frame(v: bv.Variant):
    L = v.length
    ox, bottom = (N - bv.NOMINAL_L * S) / 2, N / 2 + bv.H * S / 2
    P = lambda x, z: (ox + x * S, bottom - z * S)
    img = background()
    part = poly_mask([P(0, 0), P(L, 0), P(L, bv.H), P(0, bv.H)])
    shadow = cv2.GaussianBlur(np.roll(np.roll(part, 9, 0), 7, 1), (0, 0), 9).astype(np.float32) / 255
    img = img * (1 - 0.55 * shadow)
    img = blend(img, brushed((N, N), level=160), part)
    base_edge = poly_mask([P(0, 0), P(L, 0), P(L, bv.R_OUT), P(0, bv.R_OUT)])
    img = blend(img, brushed((N, N), level=185, amp=6), base_edge)                       # bend radius highlight
    edge = np.clip(part.astype(np.float32) - cv2.erode(part, np.ones((3, 3), np.uint8)).astype(np.float32), 0, 255) / 255
    img = img + 14 * edge

    defects = []
    for x, z, d in v.flange_holes:
        cx, cy = P(x, z)
        hole = circle_mask(cx, cy, d / 2 * S)
        rim = cv2.subtract(circle_mask(cx, cy, d / 2 * S + 2.4), hole)
        img = blend(img, np.full((N, N), 205.0), rim)
        img = blend(img, background() * 0.6, hole)
    for (nx, nz), (x, z, d) in zip(bv.FLANGE_HOLES, v.flange_holes):
        if abs(d - bv.HOLE_D) > bv.HOLE_TOL or math.hypot(x - nx, z - nz) > bv.LINEAR_TOL:
            cx, cy = P(x, z)
            defects.append(defect_entry("size_mismatch", Point(cx, cy).buffer(d / 2 * S), pad=8)
                           | dict(note=f"hole at ({x:.1f},{z:.1f}) vs nominal ({nx:.0f},{nz:.0f})"))
    if abs(L - bv.NOMINAL_L) > bv.LINEAR_TOL:
        x1, y1 = P(L, 0); x2, y2 = P(L, bv.H)
        defects.append(defect_entry("size_mismatch", LineString([(x1, y1), (x2, y2)]).buffer(6), pad=2)
                       | dict(note=f"length {L:.2f} vs nominal {bv.NOMINAL_L:.2f}"))
    for c in v.cracks:
        if c["plane"] != "flange":
            continue
        pts = [P(x, z) for x, z in c["pts"]]
        arr = np.round(np.array(pts)).astype(np.int32)
        cv2.polylines(img, [arr], False, 205, 4, cv2.LINE_AA)
        cv2.polylines(img, [arr], False, 14, 2, cv2.LINE_AA)
        defects.append(defect_entry("crack", LineString(pts).buffer(3)))
    return img, defects


FRAMES = [
    ("clean_bracket_good_top", "good", top_frame),
    ("clean_bracket_good_front", "good", front_frame),
    ("defect_bracket_surface_top", "defect", top_frame),
    ("defect_bracket_crack_top", "crack", top_frame),
    ("defect_bracket_crack_front", "crack", front_frame),
    ("defect_bracket_size_top", "size_mismatch", top_frame),
    ("defect_bracket_size_front", "size_mismatch", front_frame),
]


def main():
    variants = bv.make_variants()
    for name, vname, fn in FRAMES:
        img, _ = fn(variants[vname])
        finish(img, SAMPLES / f"{name}.jpg")
        print("wrote", name)


if __name__ == "__main__":
    main()
