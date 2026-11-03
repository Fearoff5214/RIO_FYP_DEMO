"""Shared geometry for bracket MS-4505-001 variants (good, defect, crack, size mismatch).

Axes: X = length, Y = width (flange at Y=0), Z = up. Units mm.
Each variant records its ground-truth geometry so the 3D models, 2D drawings and
demo camera frames all agree.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import trimesh
from shapely.geometry import LineString, Polygon

T, H, W = 2.0, 50.0, 80.0
R_IN = 3.0
R_OUT = R_IN + T
NOMINAL_L = 120.0
HOLE_D = 12.0
HOLE_TOL = 0.05
LINEAR_TOL = 0.10
BEND_TOL = 0.5
BASE_HOLES = [(15.0, 15.0), (105.0, 15.0), (15.0, 65.0), (105.0, 65.0)]   # (X, Y), axis // Z
FLANGE_HOLES = [(30.0, 30.0), (90.0, 30.0)]                                # (X, Z), axis // Y


@dataclass
class Variant:
    name: str
    title: str
    length: float = NOMINAL_L
    bend_deg: float = 90.0
    base_holes: list = field(default_factory=lambda: [list(h) + [HOLE_D] for h in BASE_HOLES])      # x, y, d
    flange_holes: list = field(default_factory=lambda: [list(h) + [HOLE_D] for h in FLANGE_HOLES])  # x, z, d
    cracks: list = field(default_factory=list)      # dict(plane, pts, label)
    dents: list = field(default_factory=list)       # dict(x, y, r, depth)
    scratches: list = field(default_factory=list)   # dict(pts, width)


def _jagged(p0, p1, n=7, amp=0.7, seed=1):
    """Jagged crack path between two points."""
    rng = np.random.default_rng(seed)
    p0, p1 = np.array(p0, float), np.array(p1, float)
    d = p1 - p0
    nrm = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-9)
    pts = [p0]
    for i in range(1, n):
        pts.append(p0 + d * i / n + nrm * rng.uniform(-amp, amp))
    pts.append(p1)
    return [tuple(p) for p in pts]


def make_variants() -> dict[str, Variant]:
    good = Variant("good", "Good part (nominal)")

    defect = Variant(
        "defect", "Surface defects: dent, scratch, bend springback 93°",
        bend_deg=93.0,
        dents=[dict(x=62.0, y=42.0, r=7.0, depth=1.0)],
        scratches=[dict(pts=[(28.0, 28.0), (52.0, 36.0), (74.0, 33.0)], width=0.9)],
    )

    crack = Variant(
        "crack", "Cracks at hole edges",
        cracks=[
            dict(plane="base", label="crack_base_hole",
                 pts=_jagged((15 - 5.4, 65 + 2.6), (4.5, 76.0), seed=3)),
            dict(plane="flange", label="crack_flange_hole",
                 pts=_jagged((90 + 1.0, 30 + 5.9), (97.0, 44.0), seed=5)),
        ],
    )

    mismatch = Variant(
        "size_mismatch", "Size mismatch: short length, oversize and shifted holes",
        length=118.4,
        base_holes=[[15.0, 15.0, 12.0], [105.0, 15.0, 12.0], [15.0, 65.0, 12.7], [106.4, 66.2, 12.0]],
        flange_holes=[[30.0, 30.0, 12.0], [92.0, 30.0, 12.0]],
    )
    return {v.name: v for v in (good, defect, crack, mismatch)}


# ---- 3D mesh -----------------------------------------------------------------
def _profile(bend_deg: float) -> Polygon:
    """L-profile in (Y, Z); flange tilted when the bend angle is not 90°."""
    pts = [(0.0, H)]
    for a in range(0, 91, 5):
        t = math.radians(180 + a)
        pts.append((R_OUT + R_OUT * math.cos(t), R_OUT + R_OUT * math.sin(t)))
    pts += [(W, 0.0), (W, T)]
    for a in range(90, -1, -5):
        t = math.radians(180 + a)
        pts.append((R_OUT + R_IN * math.cos(t), R_OUT + R_IN * math.sin(t)))
    pts += [(T, H)]
    tilt = math.radians(bend_deg - 90.0)
    c, s = math.cos(tilt), math.sin(tilt)
    out = []
    for y, z in pts:
        if z >= R_OUT - 1e-9 and y <= R_OUT + 1e-9:            # flange side of the bend
            dy, dz = y - R_OUT, z - R_OUT
            y, z = R_OUT + dy * c - dz * s, R_OUT + dy * s + dz * c
        out.append((y, z))
    return Polygon(out)


def _extrude(poly: Polygon, z0: float, z1: float) -> trimesh.Trimesh:
    m = trimesh.creation.extrude_polygon(poly, height=z1 - z0)
    m.apply_translation([0, 0, z0])
    return m


def _cyl(r, h, center, axis):
    m = trimesh.creation.cylinder(radius=r, height=h, sections=64)
    if axis == "y":
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    m.apply_translation(center)
    return m


def build_mesh(v: Variant) -> trimesh.Trimesh:
    body = _extrude(_profile(v.bend_deg), 0, v.length)            # (Y, Z) plane, extruded along X
    # remap (a=Y, b=Z, c=X) -> (X, Y, Z): cyclic permutation keeps orientation
    body.vertices = body.vertices[:, [2, 0, 1]]
    body.fix_normals()
    cutters = []
    for x, y, d in v.base_holes:
        cutters.append(_cyl(d / 2, T + 4, [x, y, T / 2], "z"))
    for x, z, d in v.flange_holes:
        cutters.append(_cyl(d / 2, T + 4, [x, T / 2, z], "y"))
    for c in v.cracks:
        line = LineString(c["pts"]).buffer(0.25, cap_style="flat", join_style="mitre")
        if c["plane"] == "base":                                  # through the base thickness
            cut = _extrude(line, -1, T + 1)
        else:                                                     # through the flange thickness
            cut = _extrude(line, -1, T + 1)                       # polygon in (X, Z), extrude along Y
            cut.vertices = cut.vertices[:, [0, 2, 1]]
            cut.invert()
        cutters.append(cut)
    for d in v.dents:
        s = trimesh.creation.icosphere(subdivisions=3, radius=d["r"])
        s.apply_translation([d["x"], d["y"], T + d["r"] - d["depth"]])
        cutters.append(s)
    for sc in v.scratches:
        line = LineString(sc["pts"]).buffer(sc["width"] / 2, cap_style="round")
        cutters.append(_extrude(line, T - 0.35, T + 0.5))
    mesh = body
    for cut in cutters:
        mesh = trimesh.boolean.difference([mesh, cut], engine="manifold")
    return mesh


def defect_anchors(v: Variant) -> list[dict]:
    """3D anchor points (and labels) of every defect, for highlighting in renders."""
    out = []
    for c in v.cracks:
        px, py = c["pts"][len(c["pts"]) // 2]
        out.append(dict(kind="crack", label="CRACK", p=(px, py, T) if c["plane"] == "base" else (px, T, py)))
    for d in v.dents:
        out.append(dict(kind="dent", label="DENT", p=(d["x"], d["y"], T)))
    for sc in v.scratches:
        px, py = sc["pts"][len(sc["pts"]) // 2]
        out.append(dict(kind="scratch", label="SCRATCH", p=(px, py, T)))
    if abs(v.bend_deg - 90) > BEND_TOL:
        out.append(dict(kind="deformation", label=f"BEND {v.bend_deg:.0f}°", p=(v.length / 2, R_OUT, H * 0.6)))
    return out


def measurements(v: Variant) -> list[dict]:
    """Nominal vs actual checks with tolerances and PASS/FAIL."""
    rows = []

    def add(name, nominal, actual, tol):
        rows.append(dict(name=name, nominal=nominal, actual=actual, tol=tol,
                         ok=abs(actual - nominal) <= tol + 1e-9))

    add("Length (X)", NOMINAL_L, v.length, LINEAR_TOL)
    add("Width (Y)", W, W, LINEAR_TOL)
    add("Height (Z)", H, H, LINEAR_TOL)
    add("Bend angle (deg)", 90.0, v.bend_deg, BEND_TOL)
    for i, ((nx, ny), (x, y, d)) in enumerate(zip(BASE_HOLES, v.base_holes), 1):
        add(f"Base hole {i} dia", HOLE_D, d, HOLE_TOL)
        add(f"Base hole {i} position", 0.0, math.hypot(x - nx, y - ny), LINEAR_TOL)
    for i, ((nx, nz), (x, z, d)) in enumerate(zip(FLANGE_HOLES, v.flange_holes), 1):
        add(f"Flange hole {i} dia", HOLE_D, d, HOLE_TOL)
        add(f"Flange hole {i} position", 0.0, math.hypot(x - nx, z - nz), LINEAR_TOL)
    return rows
