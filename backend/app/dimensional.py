"""Stage 2: parse the DXF drawing, measure the part in the image, compare with tolerance.

Calibration is a pixel-per-mm scale from the part master (or an engineer override on
re-measure). The measured features are the part's outer width/height and circular holes.
"""
from pathlib import Path

import cv2
import numpy as np


def parse_drawing(dxf_path: Path) -> dict:
    """Nominal features from the DXF: outer bbox (mm) and circle diameters."""
    import ezdxf
    msp = ezdxf.readfile(str(dxf_path)).modelspace()
    xs, ys, holes = [], [], []
    for e in msp:
        t = e.dxftype()
        if t == "LINE":
            xs += [float(e.dxf.start.x), float(e.dxf.end.x)]
            ys += [float(e.dxf.start.y), float(e.dxf.end.y)]
        elif t == "LWPOLYLINE":
            for x, y, *_ in e.get_points():
                xs.append(float(x))
                ys.append(float(y))
        elif t == "CIRCLE":
            holes.append(round(2 * float(e.dxf.radius), 3))
    if not xs:
        return {"width": None, "height": None, "holes": sorted(holes)}
    return {"width": round(max(xs) - min(xs), 3), "height": round(max(ys) - min(ys), 3),
            "holes": sorted(holes)}


def measure_image(img: np.ndarray, px_per_mm: float) -> dict:
    """Largest contour's rotated bbox plus Hough circles, converted to mm."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if th[0, 0] == 255:  # background should be dark
        th = cv2.bitwise_not(th)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return {"width": None, "height": None, "holes": []}
    (_, _), (w, h), _ = cv2.minAreaRect(max(cnts, key=cv2.contourArea))
    width, height = sorted((w, h), reverse=True)
    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=20, param1=100, param2=30,
                               minRadius=3, maxRadius=int(min(img.shape[:2]) // 4))
    holes = [] if circles is None else sorted(round(2 * float(c[2]) / px_per_mm, 3) for c in circles[0])
    return {"width": round(width / px_per_mm, 3), "height": round(height / px_per_mm, 3), "holes": holes}


def compare(nominal: dict, measured: dict, tol_mm: float) -> dict:
    """Per-feature deviation vs tolerance. Width/height are matched by long/short side."""
    rows = []
    nom_dims = sorted([v for v in (nominal.get("width"), nominal.get("height")) if v], reverse=True)
    mea_dims = sorted([v for v in (measured.get("width"), measured.get("height")) if v], reverse=True)
    for label, n, m in zip(("length", "width"), nom_dims, mea_dims):
        rows.append(_row(label, n, m, tol_mm))
    for i, (n, m) in enumerate(zip(nominal.get("holes", []), measured.get("holes", []))):
        rows.append(_row(f"hole_{i + 1}_dia", n, m, tol_mm))
    out = [r for r in rows if not r["pass"]]
    return {"status": "FAIL" if out else "PASS", "features": rows, "out_of_tolerance": out}


def _row(name: str, nominal: float, measured: float, tol: float) -> dict:
    dev = round(measured - nominal, 3)
    return {"feature": name, "nominal": nominal, "measured": measured, "deviation": dev,
            "tolerance": tol, "pass": abs(dev) <= tol}
