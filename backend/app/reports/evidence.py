"""Evidence pictures for the RCA report: a point-cloud heat map or an annotated camera frame.

Every report carries one picture of the part. With defects it shows them circled and labelled; for a
good part it shows the clean part under a "NO DEFECT" banner.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

COLORS = {"crack": "#e11d48", "dent": "#f97316", "scratch": "#eab308", "deformation": "#0ea5e9", "size_mismatch": "#a855f7"}
_BGR = {k: tuple(int(v[i:i + 2], 16) for i in (5, 3, 1)) for k, v in COLORS.items()}
MAX_PLOT_POINTS = 60_000


NO_PICTURE_TEXT = "No picture of the part was available for this report."


def report_images(report: dict) -> list[dict]:
    """The report's evidence pictures that exist on disk. Every report renderer goes through this, so a
    new report type gets the picture by calling it; a missing picture is logged and shown as a note."""
    found = [i for i in (report.get("evidence_images") or []) if i.get("path") and Path(i["path"]).is_file()]
    if not found:
        from app.core.logging import get_logger

        get_logger(__name__).warning('"report":"%s","evidence_image":"missing"', report.get("job_id", ""))
    return found


def _color(kind: str) -> str:
    return COLORS.get(kind, "#e11d48")


def render_pointcloud_evidence(result: dict, path: Path, part_label: str = "MS-4505-001") -> Path:
    """Draw an isometric and a top view of the scan coloured by surface deviation, defects circled."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    pts, dev, defects = result["points"], result["deviation"], result["defects"]
    sel = np.random.default_rng(0).choice(len(pts), min(len(pts), MAX_PLOT_POINTS), replace=False)
    p, d = pts[sel], np.clip(dev[sel], 0, 1.0)
    cmap = LinearSegmentedColormap.from_list("dev", ["#16a34a", "#84cc16", "#facc15", "#dc2626"])
    ok = not defects

    fig = plt.figure(figsize=(11, 5.6), dpi=130)
    ax3 = fig.add_axes((0.0, 0.12, 0.5, 0.78), projection="3d")
    ax3.scatter(p[:, 0], p[:, 1], p[:, 2], c=d, cmap=cmap, vmin=0, vmax=1.0, s=0.8, linewidths=0, depthshade=False)
    ax3.set_box_aspect((120, 80, 50))
    ax3.view_init(elev=26, azim=-60)
    ax3.tick_params(labelsize=7, pad=-2)
    ax3.set_xlabel("X mm", fontsize=8, labelpad=-6), ax3.set_ylabel("Y mm", fontsize=8, labelpad=-6)
    ax3.set_zlabel("Z mm", fontsize=8, labelpad=-8)
    ax2 = fig.add_axes((0.55, 0.16, 0.36, 0.66))
    top = p[:, 2] <= p[:, 2].max()
    ax2.scatter(p[top, 0], p[top, 1], c=d[top], cmap=cmap, vmin=0, vmax=1.0, s=0.7, linewidths=0)
    ax2.set_aspect("equal"), ax2.set_xlabel("X mm"), ax2.set_ylabel("Y mm"), ax2.set_title("Top view", fontsize=9)

    for i, df in enumerate(defects, 1):
        x, y, z = df["center"]
        col = _color(df["defect_type"])
        ax3.scatter([x], [y], [z], s=90, facecolors="none", edgecolors=col, linewidths=1.6)
        ax2.add_patch(plt.Circle((x, y), min(12.0, max(4.0, (df.get("size_mm") or 8.0) / 2 + 2)), fill=False, ec=col, lw=1.6))
        ax2.annotate(str(i), (x, y), xytext=(4, 4), textcoords="offset points", color=col, fontsize=9, weight="bold")
    if defects:
        fig.suptitle(f"{part_label}  -  {len(defects)} defect(s) found", color="#b91c1c", fontsize=12, weight="bold")
        legend = [plt.Line2D([], [], marker="o", ls="", mfc="none", mec=_color(df["defect_type"]),
                             label=f"{i}  {df['defect_type']}: {df.get('note') or ''}"[:70]) for i, df in enumerate(defects[:8], 1)]
        fig.legend(handles=legend, loc="lower center", ncol=2, fontsize=7, frameon=False)
    else:
        fig.suptitle(f"{part_label}  -  NO DEFECT, part conforms", color="#15803d", fontsize=12, weight="bold")
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1.0))
    fig.colorbar(sm, cax=fig.add_axes((0.93, 0.2, 0.015, 0.55)), label="surface deviation (mm)")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def render_frame_evidence(frame, defects: list[dict], path: Path) -> Path:
    """Annotate a camera frame (BGR ndarray): defect outlines + labels, or a NO DEFECT banner."""
    import cv2

    img = frame.copy()
    h, w = img.shape[:2]
    scale = max(1.0, w / 640)
    for i, d in enumerate(defects, 1):
        col = _BGR.get(d.get("defect_type"), (45, 45, 225))
        poly = d.get("polygon")
        if poly:
            cv2.polylines(img, [np.array(poly, np.int32).reshape(-1, 1, 2)], True, col, max(2, int(2 * scale)))
        b = d.get("bbox") or {}
        if b:
            x1, y1 = int(b["x1"]), int(b["y1"])
            cv2.putText(img, f"{i} {d['defect_type']}", (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * scale, col, max(1, int(scale)))
    banner = (f"{len(defects)} DEFECT(S) FOUND" if defects else "NO DEFECT"), ((30, 30, 190) if defects else (60, 140, 30))
    cv2.rectangle(img, (0, 0), (w, int(28 * scale)), banner[1], -1)
    cv2.putText(img, banner[0], (8, int(20 * scale)), cv2.FONT_HERSHEY_SIMPLEX, 0.65 * scale, (255, 255, 255), max(1, int(scale)))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
    return path
