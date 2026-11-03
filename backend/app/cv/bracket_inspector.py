"""Image-based inspection of bracket MS-4505-001 from a single camera frame.

Detects, from pixels only: size mismatch (part length/width/height, hole diameter and
position), cracks, scratches, dents and flange bend (top view). Returns None when the frame
does not show the bracket, so the caller can fall back to the general YOLO detector.

Calibration: frames are assumed to come from a fixed camera at PX_PER_MM_640 px/mm for a
640 px wide frame (scaled with frame width), as set in the part's camera calibration.
"""
from __future__ import annotations

import math
import uuid

import cv2
import numpy as np

NOMINAL_L, NOMINAL_W, NOMINAL_H, T = 120.0, 80.0, 50.0, 2.0
HOLE_D = 12.0
BASE_HOLES = [(15.0, 15.0), (105.0, 15.0), (15.0, 65.0), (105.0, 65.0)]   # (X from left, Y from flange edge)
FLANGE_HOLES = [(30.0, 30.0), (90.0, 30.0)]                                # (X from left, Z from bottom)
PX_PER_MM_640 = 4.6

# Drawing tolerances (mm / deg) and a small guard for measurement noise. Sizes are measured at
# sub-pixel precision (gradient-peak edges, circle fits) so deviations down to the tolerance are caught.
LINEAR_TOL_MM, HOLE_DIA_TOL_MM, HOLE_POS_TOL_MM, BEND_TOL_DEG = 0.10, 0.05, 0.10, 0.5
GUARD_MM, GUARD_DEG = 0.04, 0.2


def _odd(n: float) -> int:
    n = max(3, int(round(n)))
    return n if n % 2 else n + 1


def _poly(contour, eps=1.5):
    c = cv2.approxPolyDP(contour, eps, True).reshape(-1, 2)
    return [[float(x), float(y)] for x, y in c]


def _circle_poly(cx, cy, r, n=28):
    return [[cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)] for i in range(n)]


def _entry(kind, poly, conf, note=None):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return {
        "defect_id": str(uuid.uuid4()),
        "defect_type": kind,
        "confidence": float(max(0.05, min(0.99, conf))),
        "bbox": {"x1": min(xs), "y1": min(ys), "x2": max(xs), "y2": max(ys)},
        "polygon": poly,
        "note": note,
    }


def _components(mask, min_area):
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    return [(labels == i, stats[i]) for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area]


def _elongation(comp_mask):
    pts = cv2.findNonZero(comp_mask.astype(np.uint8))
    (_, _), (w, h), _ = cv2.minAreaRect(pts)
    return max(w, h), max(1.0, min(w, h))


def _parabolic(values: np.ndarray, i: int) -> float:
    if i <= 0 or i >= len(values) - 1:
        return 0.0
    a, b, c = values[i - 1], values[i], values[i + 1]
    den = a - 2 * b + c
    return 0.0 if abs(den) < 1e-9 else 0.5 * (a - c) / den


def _edge(profile: np.ndarray, guess: int, inward: int, k: float, window: float = 10.0) -> float:
    """Sub-pixel edge position (continuous pixel coordinates) = steepest step of the smoothed
    profile, rising toward the inside of the part."""
    kernel = np.exp(-0.5 * (np.arange(-4, 5) / 1.0) ** 2)
    sm = np.convolve(np.pad(profile, 4, mode="edge"), kernel / kernel.sum(), mode="valid")
    grad = np.gradient(sm) * inward
    w = int(round(window * k)) + 3
    lo, hi = max(1, guess - w), min(len(grad) - 2, guess + w)
    i = lo + int(np.argmax(grad[lo:hi + 1]))
    return i + 0.5 + _parabolic(grad, i)


def _fit_circle(pts: np.ndarray):
    x, y = pts[:, 0], pts[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones(len(x))]
    sol, *_ = np.linalg.lstsq(A, x ** 2 + y ** 2, rcond=None)
    cx, cy = sol[0], sol[1]
    return cx, cy, math.sqrt(max(sol[2] + cx ** 2 + cy ** 2, 0))


def _refine_hole(gray: np.ndarray, cx: float, cy: float, r: float):
    """Sub-pixel circle fit of a dark hole on brighter metal: steepest rise along many rays."""
    n_ang = 120
    ang = np.linspace(0, 2 * math.pi, n_ang, endpoint=False)
    radii = np.arange(max(2.0, 0.6 * r), 1.4 * r, 0.25)
    mx = (cx + np.outer(np.cos(ang), radii)).astype(np.float32)
    my = (cy + np.outer(np.sin(ang), radii)).astype(np.float32)
    prof = cv2.remap(gray.astype(np.float32), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    prof = cv2.GaussianBlur(prof, (0, 0), sigmaX=1.5, sigmaY=0.1)
    grad = np.gradient(prof, axis=1)
    idx = np.argmax(grad, axis=1)
    pts = []
    for a_i, i in enumerate(idx):
        if 0 < i < len(radii) - 1:
            rr = radii[i] + _parabolic(grad[a_i], i) * 0.25
            pts.append((cx + rr * math.cos(ang[a_i]), cy + rr * math.sin(ang[a_i])))
    pts = np.array(pts)
    if len(pts) < 20:
        return None
    for _ in range(3):                       # drop rays disturbed by a crack / scratch, then refit
        fx, fy, fr = _fit_circle(pts)
        res = np.abs(np.hypot(pts[:, 0] - fx, pts[:, 1] - fy) - fr)
        keep = res < max(0.35, 2.5 * float(np.median(res)))
        if keep.all() or keep.sum() < 20:
            break
        pts = pts[keep]
    return _fit_circle(pts)


def _smooth_masked(img, mask, sigma):
    """Gaussian blur that ignores pixels outside mask (no leakage from holes/background)."""
    m = mask.astype(np.float32)
    num = cv2.GaussianBlur(img * m, (0, 0), sigma)
    den = cv2.GaussianBlur(m, (0, 0), sigma)
    return num / np.maximum(den, 1e-3)


def inspect_bracket(frame: np.ndarray) -> list[dict] | None:
    h_img, w_img = frame.shape[:2]
    k = w_img / 640.0                                   # scale vs the 640 px reference
    s = PX_PER_MM_640 * k                               # px per mm
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (0, 0), 1.2)

    # ---- part segmentation -----------------------------------------------------------
    _, part_bin = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    part_bin = cv2.morphologyEx(part_bin, cv2.MORPH_CLOSE, np.ones((_odd(7 * k), _odd(7 * k)), np.uint8))
    cnts, _ = cv2.findContours(part_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    outer = max(cnts, key=cv2.contourArea)
    x0, y0, bw, bh = cv2.boundingRect(outer)
    if cv2.contourArea(outer) < 0.08 * w_img * h_img or cv2.contourArea(outer) / (bw * bh) < 0.93:
        return None
    ext_guess_mm = bh / s
    if abs(ext_guess_mm - NOMINAL_W) < 8:
        view = "top"
    elif abs(ext_guess_mm - NOMINAL_H) < 6:
        view = "front"
    else:
        return None
    if abs(bw / s - NOMINAL_L) > 6:
        return None

    row_band = (slice(int(y0 + 0.42 * bh), int(y0 + 0.58 * bh)) if view == "top"
                else slice(int(y0 + 0.62 * bh), int(y0 + 0.80 * bh)))     # clear of the holes
    col_band = slice(int(x0 + 0.42 * bw), int(x0 + 0.58 * bw))
    row_profile = gray[row_band, :].astype(np.float32).mean(axis=0)
    col_profile = gray[:, col_band].astype(np.float32).mean(axis=1)
    x_l = _edge(row_profile, x0, +1, k)
    x_r = _edge(row_profile, x0 + bw, -1, k)
    y_t = _edge(col_profile, y0, +1, k)
    y_b = _edge(col_profile, y0 + bh, -1, k)
    len_mm, ext_mm = (x_r - x_l) / s, (y_b - y_t) / s
    x0, y0, bw, bh = int(round(x_l)), int(round(y_t)), int(round(x_r - x_l)), int(round(y_b - y_t))
    left_f, bottom_f = x_l, y_b                          # keep the sub-pixel reference for measurements

    part = np.zeros_like(gray)
    cv2.drawContours(part, [outer], -1, 255, -1)
    metal = (part > 0) & (blur > 100)
    holes_dark = ((part > 0) & (blur < 90)).astype(np.uint8) * 255
    holes_open = cv2.morphologyEx(holes_dark, cv2.MORPH_OPEN,
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_odd(8 * k), _odd(8 * k))))

    defects: list[dict] = []
    bottom = y0 + bh

    def to_mm(px, py):
        return (px - left_f) / s, (bottom_f - py) / s

    # ---- size: overall length / extent ------------------------------------------------
    if abs(len_mm - NOMINAL_L) > LINEAR_TOL_MM + GUARD_MM:
        poly = [[x0 + bw - 5 * k, y0], [x0 + bw + 5 * k, y0], [x0 + bw + 5 * k, bottom], [x0 + bw - 5 * k, bottom]]
        defects.append(_entry("size_mismatch", poly, 0.6 + min(0.39, abs(len_mm - NOMINAL_L) / 2),
                              f"length {len_mm:.2f} mm (nom {NOMINAL_L:.2f} ±{LINEAR_TOL_MM:.2f})"))
    nominal_ext = NOMINAL_W if view == "top" else NOMINAL_H
    if abs(ext_mm - nominal_ext) > LINEAR_TOL_MM + GUARD_MM:
        poly = [[x0, y0 - 5 * k], [x0 + bw, y0 - 5 * k], [x0 + bw, y0 + 5 * k], [x0, y0 + 5 * k]]
        defects.append(_entry("size_mismatch", poly, 0.6 + min(0.39, abs(ext_mm - nominal_ext) / 2),
                              f"{'width' if view == 'top' else 'height'} {ext_mm:.2f} mm (nom {nominal_ext:.2f} ±{LINEAR_TOL_MM:.2f})"))

    # ---- holes: diameter and position --------------------------------------------------
    nominal_holes = BASE_HOLES if view == "top" else FLANGE_HOLES
    hole_mask = np.zeros_like(gray)
    hcnts, _ = cv2.findContours(holes_open, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in hcnts:
        area = cv2.contourArea(c)
        per = cv2.arcLength(c, True)
        if area < math.pi * (3 * s) ** 2 or per == 0 or 4 * math.pi * area / per ** 2 < 0.8:
            continue
        (cx, cy), r0 = cv2.minEnclosingCircle(c)
        cv2.drawContours(hole_mask, [c], -1, 255, -1)
        fit = _refine_hole(gray, cx, cy, r0)
        if fit is not None:
            cx, cy, r_fit = fit[0] + 0.5, fit[1] + 0.5, fit[2]      # +0.5: pixel-centre -> continuous coordinates
            d_mm = 2 * r_fit / s
        else:
            d_mm = 2 * math.sqrt(area / math.pi) / s
        mx, my = to_mm(cx, cy)
        nearest = min(nominal_holes, key=lambda n: math.hypot(n[0] - mx, n[1] - my))
        pos_err = math.hypot(nearest[0] - mx, nearest[1] - my)
        if pos_err > 8:
            continue
        issues = []
        if abs(d_mm - HOLE_D) > HOLE_DIA_TOL_MM + GUARD_MM:
            issues.append(f"dia {d_mm:.2f} (nom {HOLE_D:.2f} ±{HOLE_DIA_TOL_MM:.2f})")
        if pos_err > HOLE_POS_TOL_MM + GUARD_MM:
            issues.append(f"position off {pos_err:.2f} mm (±{HOLE_POS_TOL_MM:.2f})")
        if issues:
            conf = 0.6 + min(0.39, max(abs(d_mm - HOLE_D) / 1.0, pos_err / 2))
            defects.append(_entry("size_mismatch", _circle_poly(cx, cy, d_mm / 2 * s + 3 * k), conf, "hole " + ", ".join(issues)))

    # analysis region: metal, away from the border and from holes (with a rim margin)
    border = cv2.erode(part, np.ones((_odd(7 * k), _odd(7 * k)), np.uint8))
    hole_zone = cv2.dilate(hole_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_odd(14 * k), _odd(14 * k))))
    strip = np.zeros_like(gray)
    strip[int(bottom - 8 * s): bottom + 1, :] = 255              # flange strip / bend-radius band (brighter)
    region = (border > 0) & (hole_zone == 0) & (strip == 0)

    # ---- cracks: thin, very dark ridges (also those touching a hole rim) ---------------
    kb = _odd(13 * k)
    black = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kb, kb)))
    crack_zone = (border > 0) & (cv2.dilate(hole_mask, np.ones((3, 3), np.uint8)) == 0) & ((strip == 0) | (view == 'front'))
    crack_bin = ((black > 78) & crack_zone).astype(np.uint8) * 255
    crack_bin = cv2.morphologyEx(crack_bin, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    crack_masks = []
    for comp, st in _components(crack_bin, max(10, 18 * k * k)):
        major, minor = _elongation(comp)
        if major < 9 * k or major / minor < 2.5:
            continue
        cm = comp.astype(np.uint8) * 255
        crack_masks.append(cm)
        cc, _ = cv2.findContours(cv2.dilate(cm, np.ones((5, 5), np.uint8)), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        peak = float(black[comp].max())
        defects.append(_entry("crack", _poly(max(cc, key=cv2.contourArea)), 0.55 + 0.4 * min(1.0, peak / 170),
                              f"{major / s:.1f} mm long"))

    # ---- scratches: thin bright lines ----------------------------------------------------
    white = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kb, kb)))
    scratch_zone = region & (cv2.dilate(hole_mask, np.ones((_odd(20 * k), _odd(20 * k)), np.uint8)) == 0)
    scratch_bin = ((white > 34) & scratch_zone).astype(np.uint8) * 255
    scratch_bin = cv2.morphologyEx(scratch_bin, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    scratch_masks = []
    for comp, st in _components(scratch_bin, max(25, 40 * k * k)):
        major, minor = _elongation(comp)
        if major < 12 * s or major / minor < 4:
            continue
        sm = comp.astype(np.uint8) * 255
        scratch_masks.append(sm)
        sc, _ = cv2.findContours(cv2.dilate(sm, np.ones((5, 5), np.uint8)), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        defects.append(_entry("scratch", _poly(max(sc, key=cv2.contourArea)), 0.55 + 0.4 * min(1.0, float(white[comp].max()) / 90),
                              f"{major / s:.1f} mm long"))

    # ---- dents: smooth shading anomalies (dark/bright lobe pairs) -------------------------
    valid = region.copy()
    for m in crack_masks + scratch_masks:
        valid &= cv2.dilate(m, np.ones((_odd(26 * k), _odd(26 * k)), np.uint8)) == 0
    g = gray.astype(np.float32)
    band = _smooth_masked(g, valid, 5 * k) - _smooth_masked(g, valid, 26 * k)
    band[~valid] = 0
    lobes = (np.abs(band) > 8.5).astype(np.uint8) * 255
    lobes = cv2.dilate(lobes, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_odd(10 * k), _odd(10 * k))))
    lobes = cv2.morphologyEx(lobes, cv2.MORPH_OPEN, np.ones((_odd(5 * k), _odd(5 * k)), np.uint8))
    for comp, st in _components(lobes, math.pi * (3.5 * s) ** 2):
        cm = comp.astype(np.uint8) * 255
        dc, _ = cv2.findContours(cm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(dc, key=cv2.contourArea)
        if cv2.contourArea(c) > math.pi * (16 * s) ** 2:
            continue
        amp = float(np.abs(band[comp]).max())
        defects.append(_entry("dent", _poly(cv2.convexHull(c), 2.0), 0.5 + 0.45 * min(1.0, amp / 25),
                              f"~{2 * math.sqrt(cv2.contourArea(c) / math.pi) / s:.0f} mm"))

    # ---- flange bend (top view): visible flange strip is wider when the bend is off ------
    if view == "top":
        profile = gray[:, slice(int(x0 + 0.42 * bw), int(x0 + 0.58 * bw))].astype(np.float32).mean(axis=1)
        strip_level = float(np.median(profile[int(bottom - 4 * k): int(bottom - 1.5 * k) + 1]))
        metal_level = float(np.median(profile[int(bottom - 20 * s): int(bottom - 14 * s)]))
        # sub-pixel top edge of the bright flange strip (rises toward the bottom edge)
        guess = int(round(y_b - (T + 1.5) * s))
        strip_top = _edge(profile, guess, +1, k, window=8.0 * s / k)
        flange_mm = (y_b - strip_top) / s
        angle = 90 + math.degrees(math.asin(min(1.0, max(-1.0, (flange_mm - T) / NOMINAL_H))))
        if strip_level - metal_level > 15 and abs(angle - 90) > BEND_TOL_DEG + GUARD_DEG:
            top_px = y_b - flange_mm * s
            poly = [[x0, top_px - 3 * k], [x0 + bw, top_px - 3 * k], [x0 + bw, y_b + 2 * k], [x0, y_b + 2 * k]]
            defects.append(_entry("deformation", poly, 0.6 + min(0.39, abs(angle - 90) / 4),
                                  f"bend {angle:.1f}° (nom 90° ±{BEND_TOL_DEG:.1f})"))

    return defects
