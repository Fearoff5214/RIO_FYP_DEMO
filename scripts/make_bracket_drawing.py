"""Generate the OEM engineering drawing for bracket MS-4505-001.

Third-angle projection, A3 landscape, millimetres. Writes PNG, PDF and SVG to
docs/drawings/. Run: py scripts/make_bracket_drawing.py
"""
from __future__ import annotations

import math
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "drawings"
BASENAME = "MS-4505-001_bracket"

# ---- Part definition (mm) -------------------------------------------------
L, W, H, T = 120.0, 80.0, 50.0, 2.0      # base length (X), base width (Y), flange height (Z), thickness
R_IN = 3.0                               # inside bend radius
R_OUT = R_IN + T
HOLE_D, HOLE_TOL = 12.0, 0.05
BASE_HOLES = [(15.0, 15.0), (105.0, 15.0), (15.0, 65.0), (105.0, 65.0)]   # (X, Y), axis // Z
FLANGE_HOLES = [(30.0, 30.0), (90.0, 30.0)]                                # (X, Z), axis // Y
R = HOLE_D / 2

LINE, HID, CEN, DIM = 0.9, 0.5, 0.4, 0.4
FONT = 7.0


# ---- Drawing helpers ------------------------------------------------------
def line(ax, pts, lw=LINE, ls="-", color="k", z=3):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, lw=lw, ls=ls, color=color, solid_capstyle="butt", zorder=z)


def hidden(ax, pts):
    line(ax, pts, HID, (0, (4, 2)))


def center(ax, pts):
    line(ax, pts, CEN, (0, (8, 2, 1.5, 2)), color="#c0392b")


def text(ax, x, y, s, size=FONT, ha="center", va="center", rot=0, weight="normal", color="k"):
    ax.text(x, y, s, fontsize=size, ha=ha, va=va, rotation=rot, fontweight=weight, color=color, zorder=6)


def arrow(ax, p, q, both=True, color="k", lw=DIM, ms=6):
    style = "<|-|>" if both else "-|>"
    ax.annotate("", xy=q, xytext=p, zorder=5,
                arrowprops=dict(arrowstyle=style, lw=lw, color=color, mutation_scale=ms, shrinkA=0, shrinkB=0))


def hdim(ax, x1, x2, y_ref, off, label, gap=1.0):
    """Horizontal dimension between x1 and x2 measured at y_ref; line drawn at y_ref+off."""
    y = y_ref + off
    s = 1 if off > 0 else -1
    for x in (x1, x2):
        line(ax, [(x, y_ref + s * gap), (x, y + s * 1.5)], DIM)
    arrow(ax, (x1, y), (x2, y))
    text(ax, (x1 + x2) / 2, y + s * 2.4, label)


def vdim(ax, y1, y2, x_ref, off, label, gap=1.0):
    x = x_ref + off
    s = 1 if off > 0 else -1
    for y in (y1, y2):
        line(ax, [(x_ref + s * gap, y), (x + s * 1.5, y)], DIM)
    arrow(ax, (x, y1), (x, y2))
    text(ax, x + s * 2.6, (y1 + y2) / 2, label, rot=90)


def leader(ax, p_from, p_text, label, ha="left"):
    line(ax, [p_from, p_text], DIM)
    text(ax, p_text[0] + (1.5 if ha == "left" else -1.5), p_text[1], label, ha=ha)


def datum(ax, x, y, letter, up=True):
    tri = [(x - 2.2, y), (x + 2.2, y), (x, y + (3.8 if up else -3.8))]
    ax.add_patch(Polygon(tri, closed=True, fc="k", ec="k", zorder=5))
    ax.add_patch(plt.Rectangle((x - 3, y + (4.5 if up else -10.5)), 6, 6, fc="w", ec="k", lw=0.6, zorder=5))
    text(ax, x, y + (7.5 if up else -7.5), letter, size=7, weight="bold")


def circle(ax, cx, cy, r=R):
    ax.add_patch(Circle((cx, cy), r, fc="w", ec="k", lw=LINE, zorder=3))
    center(ax, [(cx - r - 3, cy), (cx + r + 3, cy)])
    center(ax, [(cx, cy - r - 3), (cx, cy + r + 3)])


# ---- Views ----------------------------------------------------------------
def profile_yz():
    """L-profile in (Y, Z) with inside/outside bend radii, as a closed outline."""
    pts = [(0, H)]
    for a in range(0, 91, 6):                    # outer arc, centre (R_OUT, R_OUT)
        t = math.radians(180 + a)
        pts.append((R_OUT + R_OUT * math.cos(t), R_OUT + R_OUT * math.sin(t)))
    pts += [(W, 0), (W, T)]
    for a in range(90, -1, -6):                  # inner arc, centre (R_OUT, R_OUT)
        t = math.radians(180 + a)
        pts.append((R_OUT + R_IN * math.cos(t), R_OUT + R_IN * math.sin(t)))
    pts += [(T, H)]
    return pts + [pts[0]]


def top_view(ax, ox, oy):
    X = lambda x: ox + x
    Y = lambda y: oy + y
    line(ax, [(X(0), Y(0)), (X(L), Y(0)), (X(L), Y(W)), (X(0), Y(W)), (X(0), Y(0))])
    line(ax, [(X(0), Y(T)), (X(L), Y(T))])                       # flange inner face
    line(ax, [(X(0), Y(R_OUT)), (X(L), Y(R_OUT))], DIM)          # bend tangent line
    for hx, _ in FLANGE_HOLES:                                   # hidden flange holes
        for s in (-R, R):
            hidden(ax, [(X(hx + s), Y(0)), (X(hx + s), Y(T))])
    for hx, hy in BASE_HOLES:
        circle(ax, X(hx), Y(hy))
    text(ax, X(L / 2), Y(W) + 17, "TOP VIEW", size=8, weight="bold")
    # dimensions
    hdim(ax, X(0), X(L), Y(W), 8, f"{L:.2f}")
    vdim(ax, Y(0), Y(W), X(0), -10, f"{W:.2f}")
    # hole pitch / edge dims (placed below the part, outside the outline)
    hdim(ax, X(0), X(15), Y(0), -6, "15.00")
    hdim(ax, X(15), X(105), Y(0), -6, "90.00")
    hdim(ax, X(105), X(L), Y(0), -6, "15.00")
    vdim(ax, Y(0), Y(15), X(L), 8, "15.00")
    vdim(ax, Y(15), Y(65), X(L), 8, "50.00")
    vdim(ax, Y(65), Y(W), X(L), 8, "15.00")
    leader(ax, (X(15) + R * 0.7, Y(65) + R * 0.7), (X(15) + 14, Y(65) + 12),
           f"4× Ø{HOLE_D:.2f} ±{HOLE_TOL:.2f} THRU")


def front_view(ax, ox, oy):
    X = lambda x: ox + x
    Z = lambda z: oy + z
    line(ax, [(X(0), Z(0)), (X(L), Z(0)), (X(L), Z(H)), (X(0), Z(H)), (X(0), Z(0))])
    line(ax, [(X(0), Z(R_OUT)), (X(L), Z(R_OUT))], DIM)          # bend tangent line
    for hx, _ in BASE_HOLES[:2]:                                 # hidden base holes (same X as rear pair)
        for s in (-R, R):
            hidden(ax, [(X(hx + s), Z(0)), (X(hx + s), Z(T))])
    for hx, hz in FLANGE_HOLES:
        circle(ax, X(hx), Z(hz))
    text(ax, X(L / 2), Z(H) + 7, "FRONT VIEW (A)", size=8, weight="bold")
    vdim(ax, Z(0), Z(H), X(0), -10, f"{H:.2f}")
    vdim(ax, Z(0), Z(30), X(L), 8, "30.00")
    hdim(ax, X(0), X(30), Z(0), -6, "30.00")
    hdim(ax, X(30), X(90), Z(0), -6, "60.00")
    hdim(ax, X(90), X(L), Z(0), -6, "30.00")
    leader(ax, (X(30) + R * 0.7, Z(30) + R * 0.7), (X(30) + 10, Z(H) - 6),
           f"2× Ø{HOLE_D:.2f} ±{HOLE_TOL:.2f} THRU")
    datum(ax, X(L / 2), Z(0), "A", up=True)


def side_view(ax, ox, oy):
    pts = [(ox + y, oy + z) for y, z in profile_yz()]
    line(ax, pts)
    Yv = lambda y: ox + y
    Zv = lambda z: oy + z
    for _, hy in BASE_HOLES:                                      # hidden base holes
        for s in (-R, R):
            hidden(ax, [(Yv(hy + s), Zv(0)), (Yv(hy + s), Zv(T))])
    for _, hz in FLANGE_HOLES[:1]:                                # hidden flange holes
        for s in (-R, R):
            hidden(ax, [(Yv(0), Zv(hz + s)), (Yv(T), Zv(hz + s))])
    # hole axes
    for _, hy in BASE_HOLES[:1] + BASE_HOLES[2:3]:
        center(ax, [(Yv(hy), Zv(-5)), (Yv(hy), Zv(T + 5))])
    center(ax, [(Yv(-5), Zv(30)), (Yv(T + 5), Zv(30))])
    text(ax, Yv(W / 2), Zv(H) + 7, "RIGHT SIDE VIEW", size=8, weight="bold")
    vdim(ax, Zv(0), Zv(H), Yv(W), 8, f"{H:.2f}")
    hdim(ax, Yv(0), Yv(W), Zv(0), -6, f"{W:.2f}")
    hdim(ax, Yv(0), Yv(T), Zv(H), 6, f"{T:.2f}")
    # hole positions in this view
    hdim(ax, Yv(0), Yv(15), Zv(0), -14, "15.00")
    hdim(ax, Yv(15), Yv(65), Zv(0), -14, "50.00")
    hdim(ax, Yv(65), Yv(W), Zv(0), -14, "15.00")
    # bend angle: arc between flange and base, drawn inside the corner
    # arc centred on the virtual sharp corner of the inside faces, radius 16
    corner = (Yv(T), Zv(T))
    arc = [(corner[0] + 16 * math.cos(math.radians(a)), corner[1] + 16 * math.sin(math.radians(a)))
           for a in range(0, 91, 5)]
    line(ax, arc, DIM)
    arrow(ax, arc[-2], arc[-1], both=False)
    arrow(ax, arc[1], arc[0], both=False)
    text(ax, corner[0] + 20, corner[1] + 20, "90° ±0.5°", size=FONT)
    # radii
    rc = (Yv(R_OUT), Zv(R_OUT))
    a = math.radians(225)
    leader(ax, (rc[0] + R_OUT * math.cos(a), rc[1] + R_OUT * math.sin(a)), (Yv(-8), Zv(-4)),
           f"R{R_OUT:.1f} OUTSIDE", ha="right")
    leader(ax, (Yv(R_OUT - R_IN * 0.7), Zv(R_OUT - R_IN * 0.7)), (Yv(-8), Zv(H / 2 - 8)),
           f"R{R_IN:.1f} INSIDE", ha="right")


# ---- Axis annotation (side view) -----------------------------------------
def axis_arrows(ax, ox, oy):
    Yv = lambda y: ox + y
    Zv = lambda z: oy + z
    arrow(ax, (Yv(65), Zv(T + 7)), (Yv(65), Zv(T + 20)), both=False, color="#c0392b", lw=0.9, ms=8)
    text(ax, Yv(65) + 7, Zv(T + 14), "A1 ∥ Z", color="#c0392b", weight="bold")
    arrow(ax, (Yv(T + 7), Zv(30)), (Yv(T + 20), Zv(30)), both=False, color="#c0392b", lw=0.9, ms=8)
    text(ax, Yv(T + 14), Zv(30) + 4, "A2 ∥ Y", color="#c0392b", weight="bold")


# ---- Isometric ------------------------------------------------------------
S3, S6 = math.sqrt(2), math.sqrt(6)


def iso(p, k, o):
    x, y, z = p
    return (o[0] + k * (x - y) / S3, o[1] + k * (-x - y + 2 * z) / S6)


def iso_view(ax, ox, oy, k=0.85):
    o = (ox, oy)
    P = lambda *p: iso(p, k, o)

    def face(pts3, fc):
        ax.add_patch(Polygon([P(*p) for p in pts3], closed=True, fc=fc, ec="k", lw=LINE, zorder=2))

    face([(0, T, T), (L, T, T), (L, W, T), (0, W, T)], "#f1f1f1")        # base top
    face([(0, T, T), (L, T, T), (L, T, H), (0, T, H)], "#dcdcdc")                          # flange inner face
    face([(0, 0, H), (L, 0, H), (L, T, H), (0, T, H)], "#f7f7f7")                          # flange top
    face([(L, 0, 0), (L, W, 0), (L, W, T), (L, T, T), (L, T, H), (L, 0, H)], "#c8c8c8")    # end face x=L
    face([(0, W, 0), (L, W, 0), (L, W, T), (0, W, T)], "#d6d6d6")                          # front edge y=W

    def hole(plane, c):
        for level, fill in ((0, "#6f6f6f"), (T, "w")):
            pts = []
            for a in range(0, 361, 10):
                t = math.radians(a)
                if plane == "z":
                    pts.append(P(c[0] + R * math.cos(t), c[1] + R * math.sin(t), level))
                else:
                    pts.append(P(c[0] + R * math.cos(t), T - level, c[1] + R * math.sin(t)))
            ax.add_patch(Polygon(pts, closed=True, fc=fill, ec="k", lw=0.6, zorder=3 + (level > 0)))

    for hx, hy in BASE_HOLES:
        hole("z", (hx, hy))
    for hx, hz in FLANGE_HOLES:
        hole("y", (hx, hz))

    # hole axes
    def axis3(p, q, label, lab_off):
        a, b = P(*p), P(*q)
        arrow(ax, a, b, both=False, color="#c0392b", lw=0.9, ms=8)
        text(ax, b[0] + lab_off[0], b[1] + lab_off[1], label, color="#c0392b", weight="bold", size=6.5)

    axis3((105, 65, T), (105, 65, T + 22), "A1 ∥ Z", (8, 3))
    axis3((90, T, 30), (90, T + 25, 30), "A2 ∥ Y", (9, -3))

    # overall dimensions
    def dim3(p, q, off, label):
        a, b = P(*p), P(*q)
        a2 = P(*[p[i] + off[i] for i in range(3)])
        b2 = P(*[q[i] + off[i] for i in range(3)])
        line(ax, [a, a2], DIM)
        line(ax, [b, b2], DIM)
        arrow(ax, a2, b2)
        text(ax, (a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2 + 3, label, size=6.5)

    dim3((0, W, 0), (L, W, 0), (0, 12, 0), f"{L:.0f}")
    dim3((L, 0, 0), (L, W, 0), (12, 0, 0), f"{W:.0f}")
    dim3((L, 0, 0), (L, 0, H), (12, 0, 0), f"{H:.0f}")

    # datum triad
    t0 = P(-12, W + 6, 0)
    for vec, lab in (((14, 0, 0), "X"), ((0, -14, 0), "Y"), ((0, 0, 14), "Z")):
        t1 = P(-12 + vec[0], W + 6 + vec[1], vec[2])
        arrow(ax, t0, t1, both=False, color="#1f4e79", lw=0.8, ms=7)
        text(ax, t1[0] + (t1[0] - t0[0]) * 0.25, t1[1] + (t1[1] - t0[1]) * 0.25, lab, color="#1f4e79", weight="bold")
    cx = (P(0, 0, 0)[0] + P(L, W, 0)[0]) / 2
    text(ax, cx, P(0, 0, H)[1] + 22, "ISOMETRIC VIEW (NOT TO SCALE)", size=8, weight="bold")


# ---- Tables / title block -------------------------------------------------
def table(ax, x0, y0, widths, rows, row_h=5.2, header=True, size=6.2):
    total = sum(widths)
    for r, row in enumerate(rows):
        y = y0 - (r + 1) * row_h
        if r == 0 and header:
            ax.add_patch(plt.Rectangle((x0, y), total, row_h, fc="#e8edf2", ec="k", lw=0.5, zorder=1))
        x = x0
        for w, cell in zip(widths, row):
            ax.add_patch(plt.Rectangle((x, y), w, row_h, fc="none", ec="k", lw=0.5, zorder=2))
            text(ax, x + w / 2, y + row_h / 2, cell, size=size, weight="bold" if r == 0 and header else "normal")
            x += w


def title_block(ax, x0, y0):
    w, h = 165.0, 44.0
    ax.add_patch(plt.Rectangle((x0, y0), w, h, fc="w", ec="k", lw=1.0, zorder=1))
    line(ax, [(x0, y0 + 30), (x0 + w, y0 + 30)], 0.6)
    line(ax, [(x0, y0 + 15), (x0 + w, y0 + 15)], 0.6)
    line(ax, [(x0 + 100, y0), (x0 + 100, y0 + 30)], 0.6)
    line(ax, [(x0 + 132, y0), (x0 + 132, y0 + 15)], 0.6)
    text(ax, x0 + 3, y0 + 40, "TITLE", size=5.5, ha="left", color="#555")
    text(ax, x0 + w / 2, y0 + 35, "SHEET METAL BRACKET — L-BRACKET WITH 6 SCREW HOLES", size=9, weight="bold")
    text(ax, x0 + 3, y0 + 27, "PART No.", size=5.5, ha="left", color="#555")
    text(ax, x0 + 3, y0 + 21, "MS-4505-001", size=11, weight="bold", ha="left")
    text(ax, x0 + 103, y0 + 27, "MATERIAL / THICKNESS", size=5.5, ha="left", color="#555")
    text(ax, x0 + 103, y0 + 21, "SPCC steel, cold-rolled, 2.0 mm", size=7, ha="left")
    text(ax, x0 + 3, y0 + 12, "UNITS / PROJECTION", size=5.5, ha="left", color="#555")
    text(ax, x0 + 3, y0 + 6, "mm  |  Third angle", size=7, ha="left")
    text(ax, x0 + 103, y0 + 12, "REV", size=5.5, ha="left", color="#555")
    text(ax, x0 + 103, y0 + 6, "A", size=9, weight="bold", ha="left")
    text(ax, x0 + 135, y0 + 12, "SCALE / SHEET", size=5.5, ha="left", color="#555")
    text(ax, x0 + 135, y0 + 6, "1:1  |  1 of 1", size=7, ha="left")
    # projection symbol
    # (cone + circle, third angle)
    px, py = x0 + 80, y0 + 6
    ax.add_patch(Circle((px + 8, py), 3, fc="none", ec="k", lw=0.6, zorder=3))
    ax.add_patch(Circle((px + 8, py), 1.2, fc="none", ec="k", lw=0.5, zorder=3))
    line(ax, [(px - 6, py - 3), (px, py - 1.5), (px, py + 1.5), (px - 6, py + 3), (px - 6, py - 3)], 0.6)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(420 / 25.4, 297 / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 420)
    ax.set_ylim(0, 297)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.add_patch(plt.Rectangle((8, 8), 404, 281, fc="w", ec="k", lw=1.4, zorder=0))       # sheet border
    ax.add_patch(plt.Rectangle((12, 12), 396, 273, fc="none", ec="k", lw=0.5, zorder=0))

    top_view(ax, 50, 160)
    front_view(ax, 50, 78)
    side_view(ax, 235, 78)
    axis_arrows(ax, 235, 78)
    iso_view(ax, 300, 222, k=0.68)

    # notes
    nx, ny = 335, 148
    text(ax, nx, ny, "NOTES", size=8, ha="left", weight="bold")
    notes = [
        "1. Material: SPCC cold-rolled steel, 2.0 mm sheet.",
        "2. Unspecified linear tolerance ±0.10 mm.",
        "3. Hole diameter tolerance ±0.05 mm.",
        "4. Bend angle 90° ±0.5°; inside radius R3.0.",
        "5. Break sharp edges 0.2 mm max; deburr holes.",
        "6. Datum A: base underside (marked on front view).",
        "7. Hole axes: A1 (base holes) ∥ Z, A2 (flange holes) ∥ Y.",
    ]
    y = ny - 7
    for n in notes:
        for j, part in enumerate(textwrap.wrap(n, 42)):
            text(ax, nx + (0 if j == 0 else 3), y, part, size=6.3, ha="left")
            y -= 4.6
        y -= 1.5

    # hole & axis schedule
    text(ax, 14, 59, "HOLE AND AXIS SCHEDULE", size=8, ha="left", weight="bold")
    widths = [14, 10, 24, 20, 38, 30, 30, 30, 28]
    rows = [
        ("HOLE", "QTY", "Ø (mm)", "TOL", "CENTRE X, Y, Z (mm)", "AXIS DIRECTION", "∠ TO BASE PLANE", "∠ TO FLANGE PLANE", "TYPE"),
        ("H1", "4", f"{HOLE_D:.2f}", f"±{HOLE_TOL:.2f}", "15/105, 15/65, 0–2", "A1 = (0, 0, 1)  ∥ Z", "90°", "0°", "THRU, base"),
        ("H2", "2", f"{HOLE_D:.2f}", f"±{HOLE_TOL:.2f}", "30/90, 0–2, 30", "A2 = (0, 1, 0)  ∥ Y", "0°", "90°", "THRU, flange"),
        ("BEND", "1", "—", "±0.5°", f"line Y={T:.0f}…{R_OUT:.0f}, along X", "axis ∥ X", "90° included", "", f"R{R_IN:.1f} in / R{R_OUT:.1f} out"),
    ]
    table(ax, 14, 56, widths, rows, row_h=7.5, size=5.8)

    title_block(ax, 243, 13)

    for ext in ("png", "pdf", "svg"):
        path = OUT_DIR / f"{BASENAME}.{ext}"
        fig.savefig(path, dpi=200 if ext == "png" else None, facecolor="w")
        print("wrote", path)


if __name__ == "__main__":
    main()
