"""Geometric inspection of bracket MS-4505-001 from a 3D point cloud.

The scan is assumed to be in millimetres and registered to the part frame used by the drawing:
X = length, Y = width (flange at Y = 0), Z = up. `register` translates the cloud onto the part
frame using flat-face positions, so a scan that is only translated (not rotated) is accepted as is.

Checks: overall length / width / height, flange bend angle, hole diameter and position, through
cracks (slot walls seen as mid-thickness points away from holes and edges) and dents / scratches
(local deviation from the fitted face plane). Returns the same defect dict shape as
`bracket_inspector`, plus a 3D `center` per defect and a per-point `deviation` for the heat map.

Limits: cracks are only found when the scan captured the slot walls; a rotated scan must be
registered to the part frame first.
"""
from __future__ import annotations

import io
import math
import uuid
from pathlib import Path

import numpy as np
from scipy import ndimage

T, NOMINAL_L, NOMINAL_W, NOMINAL_H = 2.0, 120.0, 80.0, 50.0
R_IN, HOLE_D = 3.0, 12.0
R_OUT = R_IN + T
BASE_HOLES = [(15.0, 15.0), (105.0, 15.0), (15.0, 65.0), (105.0, 65.0)]   # (X, Y)
FLANGE_HOLES = [(30.0, 30.0), (90.0, 30.0)]                                # (X, Z)
LINEAR_TOL, HOLE_DIA_TOL, HOLE_POS_TOL, BEND_TOL = 0.10, 0.05, 0.10, 0.5
DENT_MIN_MM = 0.25                                                         # smallest surface deviation reported
MIN_POINTS = 2000
MAX_POINTS = 3_000_000


class PointCloudError(ValueError):
    """The upload is not a usable point cloud."""


# ---- loading ------------------------------------------------------------------------------
def load_point_cloud(data: bytes, filename: str = "") -> np.ndarray:
    """Read PLY / PCD(ascii) / XYZ / PTS / CSV / NPY into an (N, 3) float array."""
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".npy":
            pts = np.load(io.BytesIO(data), allow_pickle=False)
        elif ext == ".ply":
            import trimesh

            loaded = trimesh.load(io.BytesIO(data), file_type="ply")
            pts = np.asarray(getattr(loaded, "vertices", loaded))
        elif ext == ".pcd":
            _, _, body = data.decode("ascii", "ignore").partition("DATA ascii")
            if not body:
                raise PointCloudError("Only ASCII .pcd files are supported; export as .ply or .xyz.")
            pts = np.loadtxt(io.StringIO(body), usecols=(0, 1, 2))
        else:                                                      # .xyz .pts .txt .csv: x y z per line
            text = data.decode("utf-8", "ignore").replace(",", " ").replace(";", " ")
            rows = [ln.split()[:3] for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith(("#", "//"))]
            pts = np.array([[float(v) for v in r] for r in rows if len(r) == 3 and _is_num(r)])
    except PointCloudError:
        raise
    except Exception as exc:                                       # noqa: BLE001
        raise PointCloudError(f"Could not read the point cloud ({type(exc).__name__}).") from exc
    pts = np.asarray(pts, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise PointCloudError("Point cloud must contain x, y, z coordinates.")
    pts = pts[:, :3]
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) < MIN_POINTS:
        raise PointCloudError(f"Point cloud has only {len(pts)} points; at least {MIN_POINTS} are needed.")
    if len(pts) > MAX_POINTS:
        pts = pts[np.random.default_rng(0).choice(len(pts), MAX_POINTS, replace=False)]
    return pts


def _is_num(row) -> bool:
    try:
        [float(v) for v in row]
        return True
    except ValueError:
        return False


# ---- helpers ------------------------------------------------------------------------------
def _entry(kind: str, center, conf: float, note: str, size_mm: float | None = None) -> dict:
    return {
        "defect_id": str(uuid.uuid4()),
        "defect_type": kind,
        "confidence": float(max(0.05, min(0.99, conf))),
        "center": [float(c) for c in center],
        "size_mm": size_mm,
        "note": note,
    }


def _fit_circle(x: np.ndarray, y: np.ndarray):
    A = np.c_[2 * x, 2 * y, np.ones(len(x))]
    sol, *_ = np.linalg.lstsq(A, x ** 2 + y ** 2, rcond=None)
    return sol[0], sol[1], math.sqrt(max(sol[2] + sol[0] ** 2 + sol[1] ** 2, 0.0))


def _spacing(pts: np.ndarray) -> float:
    """Typical distance between neighbouring points (mm), from a sample."""
    from scipy.spatial import cKDTree

    sample = pts[np.random.default_rng(1).choice(len(pts), min(len(pts), 4000), replace=False)]
    d, _ = cKDTree(pts).query(sample, k=2)
    return float(np.median(d[:, 1]))


def _clusters(u, v, cell, closing=1, min_cells=3):
    """Group 2D points into connected blobs on a grid; yields (u_points, v_points, index mask) per blob."""
    iu = ((u - u.min()) / cell).astype(int)
    iv = ((v - v.min()) / cell).astype(int)
    grid = np.zeros((iu.max() + 1, iv.max() + 1), bool)
    grid[iu, iv] = True
    grid = ndimage.binary_closing(grid, structure=np.ones((3, 3)), iterations=closing)
    lab, n = ndimage.label(grid, structure=np.ones((3, 3)))
    ids = lab[iu, iv]
    sizes = ndimage.sum(grid, lab, range(1, n + 1))
    for k in range(1, n + 1):
        sel = ids == k
        if sizes[k - 1] >= min_cells and sel.sum() >= 3:
            yield u[sel], v[sel], sel


def _extent(u, v):
    """Major / minor extent (mm) of a 2D point set along its principal axes."""
    c = np.c_[u - u.mean(), v - v.mean()]
    _, vec = np.linalg.eigh(np.cov(c.T))
    span = np.ptp(c @ vec, axis=0)
    return float(span.max()), float(span.min())


def _away_from(U, V, holes, radius, mask):
    """`mask` restricted to points farther than `radius` from every hole centre."""
    ok = np.asarray(mask).copy()
    for hx, hy in holes:
        ok &= np.hypot(U - hx, V - hy) > radius
    return ok


# ---- registration -------------------------------------------------------------------------
def _face(values: np.ndarray, side: int, bin_mm: float) -> float:
    """Position of the outermost flat face along one axis = peak of a fine histogram of the last mm.
    Immune to scanner noise, which inflates a plain min/max by several sigma."""
    e = values.max() if side > 0 else values.min()
    win = values[(values > e - 1.0) if side > 0 else (values < e + 1.0)]
    edges = np.arange(win.min(), win.max() + bin_mm, bin_mm)
    hist, edges = np.histogram(win, bins=edges)
    k = int(np.argmax(np.convolve(hist, np.ones(3), mode="same")))
    c = 0.5 * (edges[k] + edges[k + 1])
    near = win[np.abs(win - c) < 2 * bin_mm]
    return float(np.median(near)) if len(near) else float(c)


def _flange_line(pts: np.ndarray):
    """Fit the outer flange face Y = a + b*Z; `pts` must have its minimum corner near the origin."""
    flat = pts[(pts[:, 2] > R_OUT + 8) & (pts[:, 1] < R_OUT + 16)]
    if len(flat) < 200:
        return None
    zb = np.round(flat[:, 2]).astype(int)
    zs, ys = [], []
    for z in np.unique(zb):                                        # outer face per 1 mm slice: median of the lowest-Y points
        y = flat[zb == z, 1]
        face = y[y < y.min() + 1.0]
        if len(face) >= 20:
            zs.append(float(z))
            ys.append(float(np.median(face)))
    if len(zs) < 8:
        return None
    b, a = np.polyfit(zs, ys, 1)
    return a, b


def register(points: np.ndarray, sp: float):
    """Translate the cloud into the part frame. Returns (points, info)."""
    pts = points - points.min(axis=0)
    bin_mm = max(0.02, 0.4 * sp)
    x0, x1 = _face(pts[:, 0], -1, bin_mm), _face(pts[:, 0], +1, bin_mm)
    z0, z1 = _face(pts[:, 2], -1, bin_mm), _face(pts[:, 2], +1, bin_mm)
    y1 = _face(pts[:, 1], +1, bin_mm)
    shifted = pts - np.array([x0, 0.0, z0])
    line = _flange_line(shifted)
    y_ref = (line[0] + line[1] * R_OUT) if line else float(shifted[:, 1].min())   # outer flange face at the bend
    shifted[:, 1] -= y_ref
    info = {"length": x1 - x0, "width": y1 - y_ref, "height": z1 - z0,
            "angle": 90.0 - math.degrees(math.atan(line[1])) if line else None}
    if line:                                                       # straighten a bent flange for the hole / crack checks
        up = shifted[:, 2] > R_OUT
        shifted[up, 1] -= line[1] * (shifted[up, 2] - R_OUT)
    return shifted, info


# ---- holes --------------------------------------------------------------------------------
def _check_hole(name, u, v, w, face, nu, nv, measure, on_fail):
    """Fit the hole near its nominal centre (wall points if the scan has them, else the rim);
    record diameter and position, call on_fail when out of tolerance."""
    r_all = np.hypot(u - nu, v - nv)
    wall = (w > 0.3) & (w < T - 0.3) & (r_all > 3.0) & (r_all < 9.0)
    if wall.sum() >= 60:
        pu, pv = u[wall], v[wall]
    else:                                                          # rim fallback: innermost points per angular bin
        fu, fv, r = u[face], v[face], r_all[face]
        ring = (r > 3.0) & (r < 10.0)
        if ring.sum() < 40:
            return
        ang = np.arctan2(fv[ring] - nv, fu[ring] - nu)
        bins = np.floor((ang + math.pi) / (2 * math.pi) * 90).astype(int) % 90
        pu, pv = [], []
        for b in range(90):
            s = bins == b
            if s.sum() >= 2:
                j = np.argsort(r[ring][s])[: max(1, int(s.sum()) // 10)]
                pu.append(np.median(fu[ring][s][j]))
                pv.append(np.median(fv[ring][s][j]))
        pu, pv = np.array(pu), np.array(pv)
        if len(pu) < 30:
            return
    for _ in range(3):                                            # drop points disturbed by a crack, refit
        cx, cy, rad = _fit_circle(pu, pv)
        res = np.abs(np.hypot(pu - cx, pv - cy) - rad)
        keep = res < max(0.15, 3.0 * float(np.median(res)))
        if keep.all() or keep.sum() < 30:
            break
        pu, pv = pu[keep], pv[keep]
    d = 2 * rad
    pos = math.hypot(cx - nu, cy - nv)
    d_ok = measure(f"{name} dia", HOLE_D, d, HOLE_DIA_TOL)
    p_ok = measure(f"{name} position", 0.0, pos, HOLE_POS_TOL)
    if not (d_ok and p_ok):
        msgs = []
        if not d_ok:
            msgs.append(f"dia {d:.2f} (nom {HOLE_D:.2f} ±{HOLE_DIA_TOL:.2f})")
        if not p_ok:
            msgs.append(f"position off {pos:.2f} mm (±{HOLE_POS_TOL:.2f})")
        on_fail(cx, cy, d, f"{name.lower()}: " + ", ".join(msgs))


# ---- main ---------------------------------------------------------------------------------
def inspect_pointcloud(points: np.ndarray) -> dict:
    """Inspect a bracket scan. Returns {defects, measurements, deviation, points, spacing_mm, status}."""
    sp = _spacing(points)
    pts, info = register(np.asarray(points, float), sp)
    guard = min(0.5 * sp, 0.04)                                    # measurement noise allowance (mm)
    defects: list[dict] = []
    measurements: list[dict] = []

    def measure(name, nominal, actual, tol, unit="mm"):
        ok = abs(actual - nominal) <= tol + (guard if unit == "mm" else 0.2)
        measurements.append({"feature_id": name, "nominal": round(nominal, 3), "actual": round(float(actual), 3),
                             "tolerance": tol, "deviation": round(float(actual - nominal), 3),
                             "within_tolerance": bool(ok), "unit": unit})
        return ok

    length, width, height = info["length"], info["width"], info["height"]
    if abs(length - NOMINAL_L) > 12 or abs(width - NOMINAL_W) > 8 or abs(height - NOMINAL_H) > 8:
        raise PointCloudError(
            f"The scan is {length:.0f} x {width:.0f} x {height:.0f} mm, which is not bracket MS-4505-001 "
            f"({NOMINAL_L:.0f} x {NOMINAL_W:.0f} x {NOMINAL_H:.0f} mm). Check the part, the units (mm) and the orientation.")
    ext_y = float(pts[:, 1].max())

    # ---- overall size ----------------------------------------------------------------
    if not measure("Length (X)", NOMINAL_L, length, LINEAR_TOL):
        defects.append(_entry("size_mismatch", [length, ext_y / 2, T], 0.6 + min(0.39, abs(length - NOMINAL_L) / 2),
                              f"length {length:.2f} mm (nom {NOMINAL_L:.2f} ±{LINEAR_TOL:.2f})"))
    if not measure("Width (Y)", NOMINAL_W, width, LINEAR_TOL):
        defects.append(_entry("size_mismatch", [length / 2, width, T], 0.6 + min(0.39, abs(width - NOMINAL_W) / 2),
                              f"width {width:.2f} mm (nom {NOMINAL_W:.2f} ±{LINEAR_TOL:.2f})"))
    measure("Height (Z)", NOMINAL_H, height, LINEAR_TOL)             # informational: it moves with the bend angle
    if info["angle"] is not None:
        angle = info["angle"]
        if not measure("Flange bend angle", 90.0, angle, BEND_TOL, unit="deg"):
            defects.append(_entry("deformation", [length / 2, R_OUT, height * 0.6],
                                  0.6 + min(0.39, abs(angle - 90) / 4), f"bend {angle:.1f}° (nom 90° ±{BEND_TOL:.1f})"))

    # ---- holes ------------------------------------------------------------------------
    base_face = (pts[:, 2] <= T + 0.05) & (pts[:, 1] > R_OUT + 1.0)
    flange_face = (pts[:, 1] <= T + 0.4) & (pts[:, 2] > R_OUT + 3)
    for i, (nx, ny) in enumerate(BASE_HOLES, 1):
        _check_hole(f"Base hole {i}", pts[:, 0], pts[:, 1], pts[:, 2], base_face, nx, ny, measure,
                    lambda cx, cy, d, msg: defects.append(_entry("size_mismatch", [cx, cy, T], 0.6 + min(0.39, abs(d - HOLE_D)), msg)))
    for i, (nx, nz) in enumerate(FLANGE_HOLES, 1):
        _check_hole(f"Flange hole {i}", pts[:, 0], pts[:, 2], pts[:, 1], flange_face, nx, nz, measure,
                    lambda cx, cz, d, msg: defects.append(_entry("size_mismatch", [cx, T, cz], 0.6 + min(0.39, abs(d - HOLE_D)), msg)))

    # ---- cracks: slot walls = mid-thickness points that are not hole or edge walls ------------
    crack_sites = []
    faces = (
        ("base", pts[:, 0], pts[:, 1], pts[:, 2], pts[:, 1] > R_OUT + 1.5, BASE_HOLES, lambda a, b: [a, b, T], ext_y),
        ("flange", pts[:, 0], pts[:, 2], pts[:, 1], pts[:, 2] > R_OUT + 3, FLANGE_HOLES, lambda a, b: [a, T, b], height),
    )
    for name, u, v, w, region, holes, to3d, extent_v in faces:
        mid = region & (w > 0.4) & (w < T - 0.55) & (u > 1.5) & (u < length - 1.5) & (v < extent_v - 1.5)
        mid = _away_from(u, v, holes, HOLE_D / 2 + 2.0, mid)
        if mid.sum() < 5:
            continue
        for uu, vv, _ in _clusters(u[mid], v[mid], cell=0.6):
            major, minor = _extent(uu, vv)
            if major < 3.0 or major / max(minor, 0.6) < 2.5:
                continue
            cu, cv_ = float(uu.mean()), float(vv.mean())
            if name == "base":
                crack_sites.append((cu, cv_, major))
            defects.append(_entry("crack", to3d(cu, cv_), 0.7 + min(0.25, major / 40), f"{major:.1f} mm long, {name} face", size_mm=major))

    # ---- base face deviation: dents and scratches ---------------------------------------------
    deviation = np.zeros(len(pts), np.float32)
    top = (pts[:, 2] > T * 0.5) & (pts[:, 1] > R_OUT + 1.0)
    top_pts = pts[top]
    if len(top_pts) > 1000:
        z_face = float(np.percentile(top_pts[:, 2], 60))            # nominal face height (robust to dents)
        sel = np.abs(top_pts[:, 2] - z_face) < 3.0
        face = top_pts[sel]
        dev = face[:, 2] - z_face
        fu, fv = face[:, 0], face[:, 1]
        ok_region = _away_from(fu, fv, BASE_HOLES, HOLE_D / 2 + 2.5,
                               (fv > R_OUT + 3) & (fu > 1.5) & (fu < length - 1.5) & (fv < ext_y - 1.5))
        for cu, cv_, major in crack_sites:                          # slot walls are not dents
            ok_region &= np.hypot(fu - cu, fv - cv_) > major
        deviation[np.nonzero(top)[0][sel]] = dev
        bad = (np.abs(dev) > DENT_MIN_MM) & ok_region
        if bad.sum() >= 8:
            for uu, vv, sel_c in _clusters(fu[bad], fv[bad], cell=0.8, closing=1, min_cells=5):
                major, minor = _extent(uu, vv)
                cu, cv_ = float(uu.mean()), float(vv.mean())
                own = dev[bad][sel_c]
                peak = float(own[np.argmax(np.abs(own))])
                cells = len(np.unique(np.floor(uu / 0.8) * 100000 + np.floor(vv / 0.8)))
                fill = cells * 0.64 / max(major * minor, 1.0)       # a bent scratch fills little of its bounding box
                if major >= 8 and (major / max(minor, 0.5) >= 4 or fill < 0.35):
                    kind, note = "scratch", f"{major:.1f} mm long, {abs(peak):.2f} mm deep"
                else:
                    kind = "dent"
                    note = f"~{major:.0f} mm across, {abs(peak):.2f} mm {'deep' if peak < 0 else 'high'}"
                defects.append(_entry(kind, [cu, cv_, z_face], 0.55 + 0.4 * min(1.0, abs(peak) / 1.0), note, size_mm=float(major)))

    # ---- deviation colouring for the evidence image -----------------------------------------
    for d in defects:                                              # dents / scratches already carry their own deviation
        if d["defect_type"] in ("dent", "scratch"):
            continue
        near = np.linalg.norm(pts - np.array(d["center"]), axis=1) < min(5.0, max(3.0, (d.get("size_mm") or 6.0) / 3))
        deviation[near] = np.maximum(np.abs(deviation[near]), 1.0)

    return {"defects": defects, "measurements": measurements, "deviation": np.abs(deviation), "points": pts,
            "spacing_mm": sp, "status": "FAIL" if defects else "PASS"}
