"""Export 3D (STL/GLB) and 2D (DXF) models, renders and comparison sheets for the bracket variants.

Run: py scripts/make_bracket_models.py   ->  docs/models/bracket/
"""
from __future__ import annotations

import math
import sys
import textwrap
from pathlib import Path

import ezdxf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from matplotlib.patches import Circle, Rectangle
from mpl_toolkits.mplot3d import proj3d
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bracket_variants as bv  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "models" / "bracket"
PN = "MS-4505-001"
COLORS = {"crack": "#e11d48", "dent": "#f97316", "scratch": "#eab308", "deformation": "#0ea5e9"}


# ---- 3D renders -----------------------------------------------------------
def render_3d(ax, mesh, v, elev=28, azim=45, labels=True, max_edge=2.5):
    fine = mesh.copy()
    fine.vertices, fine.faces = trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces, max_edge=max_edge)
    fine = trimesh.Trimesh(fine.vertices, fine.faces, process=True)
    # view direction (from the part toward the camera) for back-face culling
    e, a = math.radians(elev), math.radians(azim)
    view = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    front = fine.face_normals @ view > -0.02
    tris = fine.triangles[front]
    normals = fine.face_normals[front]
    light = np.array([0.45, 0.35, 0.82])
    light /= np.linalg.norm(light)
    shade = np.clip(normals @ light, 0, 1) * 0.6 + 0.4
    cols = np.clip(shade[:, None] * np.array([0.70, 0.73, 0.78]), 0, 1)
    ax.computed_zorder = False
    coll = Poly3DCollection(tris, facecolors=cols, edgecolors=cols, linewidths=0.2, zorder=1)
    ax.add_collection3d(coll)
    ax.set_xlim(0, 120); ax.set_ylim(-5, 80); ax.set_zlim(0, 50)
    ax.set_box_aspect((120, 85, 50))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    if labels:
        for i, d in enumerate(bv.defect_anchors(v)):
            x, y, z = d["p"]
            col = COLORS[d["kind"]]
            ax.plot([x], [y], [z], marker="o", ms=16, mfc="none", mec=col, mew=2, ls="", zorder=10)
            ax.text(x + 4, y + 4, z + 9 + 5 * (i % 2), d["label"], fontsize=8, fontweight="bold", color=col, zorder=11,
                    bbox=dict(boxstyle="round,pad=0.2", fc="w", ec=col, lw=0.8))


def make_3d(variants, meshes):
    for name, v in variants.items():
        fig = plt.figure(figsize=(7, 5.2), dpi=170)
        ax = fig.add_subplot(111, projection="3d")
        render_3d(ax, meshes[name], v)
        fig.suptitle(f"{PN} — {v.title}", fontsize=10, fontweight="bold", y=0.96)
        fig.savefig(OUT / f"{PN}_{name}_3d.png", facecolor="w")
        plt.close(fig)
    fig = plt.figure(figsize=(13, 9.5), dpi=150)
    for i, (name, v) in enumerate(variants.items(), 1):
        ax = fig.add_subplot(2, 2, i, projection="3d")
        render_3d(ax, meshes[name], v)
        ax.set_title(v.title, fontsize=9.5, fontweight="bold")
    fig.suptitle(f"{PN} — 3D model comparison", fontsize=13, fontweight="bold")
    fig.savefig(OUT / f"{PN}_3d_comparison.png", facecolor="w")
    plt.close(fig)


# ---- 2D drawings ----------------------------------------------------------
def make_dxf(v):
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    for name, color in (("OUTLINE", 7), ("HIDDEN", 8), ("CENTER", 1), ("DEFECT", 1), ("TEXT", 7)):
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    L = v.length
    # top view at origin (X right, Y up)
    msp.add_lwpolyline([(0, 0), (L, 0), (L, bv.W), (0, bv.W)], close=True, dxfattribs={"layer": "OUTLINE"})
    msp.add_line((0, bv.T), (L, bv.T), dxfattribs={"layer": "OUTLINE"})
    msp.add_line((0, bv.R_OUT), (L, bv.R_OUT), dxfattribs={"layer": "HIDDEN"})
    for x, y, d in v.base_holes:
        msp.add_circle((x, y), d / 2, dxfattribs={"layer": "OUTLINE"})
        msp.add_line((x - d / 2 - 3, y), (x + d / 2 + 3, y), dxfattribs={"layer": "CENTER"})
        msp.add_line((x, y - d / 2 - 3), (x, y + d / 2 + 3), dxfattribs={"layer": "CENTER"})
    # front view below (X right, Z up)
    fy = -bv.H - 25
    msp.add_lwpolyline([(0, fy), (L, fy), (L, fy + bv.H), (0, fy + bv.H)], close=True, dxfattribs={"layer": "OUTLINE"})
    for x, z, d in v.flange_holes:
        msp.add_circle((x, fy + z), d / 2, dxfattribs={"layer": "OUTLINE"})
        msp.add_line((x - d / 2 - 3, fy + z), (x + d / 2 + 3, fy + z), dxfattribs={"layer": "CENTER"})
        msp.add_line((x, fy + z - d / 2 - 3), (x, fy + z + d / 2 + 3), dxfattribs={"layer": "CENTER"})
    # side view to the right (Y right, Z up)
    sx = L + 30
    prof = [(sx + y, fy + z) for y, z in bv._profile(v.bend_deg).exterior.coords]
    msp.add_lwpolyline(prof, close=True, dxfattribs={"layer": "OUTLINE"})
    # defects
    for c in v.cracks:
        if c["plane"] == "base":
            msp.add_lwpolyline(c["pts"], dxfattribs={"layer": "DEFECT"})
        else:
            msp.add_lwpolyline([(x, fy + z) for x, z in c["pts"]], dxfattribs={"layer": "DEFECT"})
    for d in v.dents:
        msp.add_circle((d["x"], d["y"]), d["r"], dxfattribs={"layer": "DEFECT"})
    for sc in v.scratches:
        msp.add_lwpolyline(sc["pts"], dxfattribs={"layer": "DEFECT"})
    # annotations
    msp.add_text(f"{PN} {v.name}  L={v.length:.2f} W={bv.W:.2f} H={bv.H:.2f}  bend={v.bend_deg:.1f} deg",
                 dxfattribs={"layer": "TEXT", "height": 3, "insert": (0, bv.W + 8)})
    for i, (x, y, d) in enumerate(v.base_holes, 1):
        msp.add_text(f"B{i} d{d:.2f} @({x:.2f},{y:.2f})", dxfattribs={"layer": "TEXT", "height": 2, "insert": (x - 10, y - d / 2 - 7)})
    for i, (x, z, d) in enumerate(v.flange_holes, 1):
        msp.add_text(f"F{i} d{d:.2f} @({x:.2f},{z:.2f})", dxfattribs={"layer": "TEXT", "height": 2, "insert": (x - 10, fy + z - d / 2 - 7)})
    doc.saveas(OUT / f"{PN}_{v.name}.dxf")


def draw_2d(ax, v, marked=True):
    """2D views of a variant. marked=False draws plain geometry only (no red highlights, no surface defects)."""
    L = v.length
    ghost = dict(fc="none", ec="#9ca3af", ls="--", lw=0.9)
    ax.add_patch(Rectangle((0, 0), bv.NOMINAL_L, bv.W, **ghost))
    for x, y in bv.BASE_HOLES:
        ax.add_patch(Circle((x, y), bv.HOLE_D / 2, **ghost))
    ax.add_patch(Rectangle((0, 0), L, bv.W, fc="#eef1f5", ec="k", lw=1.4))
    ax.plot([0, L], [bv.T, bv.T], "k", lw=0.8)
    for i, ((nx, ny), (x, y, d)) in enumerate(zip(bv.BASE_HOLES, v.base_holes), 1):
        bad = marked and (abs(d - bv.HOLE_D) > bv.HOLE_TOL or math.hypot(x - nx, y - ny) > bv.LINEAR_TOL)
        ax.add_patch(Circle((x, y), d / 2, fc="w", ec="#e11d48" if bad else "k", lw=1.6 if bad else 1.1))
        if bad:
            ax.annotate(f"Ø{d:.2f}\n@({x:.1f},{y:.1f})", (x, y), (x + (9 if x < 60 else -30), y - 14), fontsize=6.5, color="#e11d48",
                        arrowprops=dict(arrowstyle="-", color="#e11d48", lw=0.7))
    for c in v.cracks:
        if c["plane"] == "base":
            xs, ys = zip(*c["pts"])
            ax.plot(xs, ys, color="#e11d48" if marked else "k", lw=2 if marked else 1.4)
    for d in v.dents:
        if marked:
            ax.add_patch(Circle((d["x"], d["y"]), d["r"], fc="#f97316", alpha=0.35, ec="#f97316", lw=1.2))
    for sc in v.scratches:
        if marked:
            xs, ys = zip(*sc["pts"])
            ax.plot(xs, ys, color="#eab308", lw=2)
    # front view stacked below
    oy = -bv.H - 14
    ax.add_patch(Rectangle((0, oy), bv.NOMINAL_L, bv.H, **ghost))
    for x, z in bv.FLANGE_HOLES:
        ax.add_patch(Circle((x, oy + z), bv.HOLE_D / 2, **ghost))
    ax.add_patch(Rectangle((0, oy), L, bv.H, fc="#eef1f5", ec="k", lw=1.4))
    for i, ((nx, nz), (x, z, d)) in enumerate(zip(bv.FLANGE_HOLES, v.flange_holes), 1):
        bad = marked and (abs(d - bv.HOLE_D) > bv.HOLE_TOL or math.hypot(x - nx, z - nz) > bv.LINEAR_TOL)
        ax.add_patch(Circle((x, oy + z), d / 2, fc="w", ec="#e11d48" if bad else "k", lw=1.6 if bad else 1.1))
        if bad:
            ax.annotate(f"Ø{d:.2f}\n@({x:.1f},{z:.1f})", (x, oy + z), (x + (9 if x < 60 else -30), oy + z + 14), fontsize=6.5, color="#e11d48",
                        arrowprops=dict(arrowstyle="-", color="#e11d48", lw=0.7))
    for c in v.cracks:
        if c["plane"] == "flange":
            xs, zs = zip(*c["pts"])
            ax.plot(xs, [oy + z for z in zs], color="#e11d48" if marked else "k", lw=2 if marked else 1.4)
    ax.text(0, bv.W + 3, "TOP VIEW", fontsize=7, fontweight="bold")
    ax.text(0, oy + bv.H + 3, "FRONT VIEW", fontsize=7, fontweight="bold")
    ax.set_xlim(-6, 130); ax.set_ylim(oy - 6, bv.W + 10)
    ax.set_aspect("equal"); ax.axis("off")


def make_2d_sheet(variants):
    fig = plt.figure(figsize=(15, 12), dpi=140)
    gs = fig.add_gridspec(2, 2, left=0.02, right=0.98, top=0.9, bottom=0.03, wspace=0.05, hspace=0.12)
    for i, (name, v) in enumerate(variants.items()):
        ax = fig.add_subplot(gs[i // 2, i % 2])
        draw_2d(ax, v)
        rows = bv.measurements(v)
        fails = [r for r in rows if not r["ok"]]
        verdict = "PASS" if not v.cracks and not v.dents and not v.scratches and not fails else "FAIL"
        notes = []
        if v.cracks: notes.append(f"{len(v.cracks)} crack(s)")
        if v.dents: notes.append("dent")
        if v.scratches: notes.append("scratch")
        notes += [f"{r['name']}: {r['actual']:.2f} (nom {r['nominal']:.2f} ±{r['tol']:.2f})" for r in fails]
        ax.set_title(f"{v.title}  —  {verdict}", fontsize=10.5, fontweight="bold",
                     color="#15803d" if verdict == "PASS" else "#b91c1c")
        ax.text(60, ax.get_ylim()[0] - 1, textwrap.fill("; ".join(notes) if notes else "All dimensions within tolerance", 95),
                fontsize=6.8, ha="center", va="top", color="#374151")
    fig.suptitle(f"{PN} — 2D model comparison (dashed grey = nominal, red = out of tolerance / defect)",
                 fontsize=13, fontweight="bold")
    fig.savefig(OUT / f"{PN}_2d_comparison.png", facecolor="w")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    variants = bv.make_variants()
    meshes = {n: bv.build_mesh(v) for n, v in variants.items()}
    for n, m in meshes.items():
        m.visual.face_colors = [180, 186, 198, 255]
        m.export(OUT / f"{PN}_{n}.stl")
        m.export(OUT / f"{PN}_{n}.glb")
        make_dxf(variants[n])
    make_3d(variants, meshes)
    make_2d_sheet(variants)
    for p in sorted(OUT.iterdir()):
        print(p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
