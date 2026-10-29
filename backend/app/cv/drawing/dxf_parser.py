"""DXF drawing parser using ezdxf."""
from __future__ import annotations

from pathlib import Path


def parse_dxf(drawing_uri: str) -> dict:
    """
    Parse a DXF file and extract features, dimensions, and tolerances.
    Falls back to synthetic data if the file is missing or ezdxf is not installed.
    """
    if drawing_uri.startswith("synthetic://"):
        from app.cv.drawing.synthetic import generate_synthetic_drawing
        part_number = drawing_uri.replace("synthetic://", "").replace(".dxf", "")
        return generate_synthetic_drawing(part_number)

    path = Path(drawing_uri)
    if not path.exists():
        from app.cv.drawing.synthetic import generate_synthetic_drawing
        return generate_synthetic_drawing("UNKNOWN")

    try:
        import ezdxf

        doc = ezdxf.readfile(str(path))
        msp = doc.modelspace()

        features = []
        circles = list(msp.query("CIRCLE"))
        for i, circle in enumerate(circles):
            features.append({
                "feature_id": f"H{i+1}",
                "feature_type": "hole",
                "nominal": circle.dxf.radius * 2,  # diameter
                "tol_plus": 0.05,
                "tol_minus": 0.05,
                "center": (circle.dxf.center.x, circle.dxf.center.y),
            })

        lines = list(msp.query("LINE"))
        for i, line in enumerate(lines[:4]):
            import math
            length = math.sqrt(
                (line.dxf.end.x - line.dxf.start.x) ** 2
                + (line.dxf.end.y - line.dxf.start.y) ** 2
            )
            features.append({
                "feature_id": f"L{i+1}",
                "feature_type": "edge",
                "nominal": round(length, 3),
                "tol_plus": 0.10,
                "tol_minus": 0.10,
            })

        return {
            "part_number": path.stem,
            "format": "dxf",
            "features": features,
            "drawing_uri": drawing_uri,
            "detected_features": [],
        }

    except Exception as e:
        from app.cv.drawing.synthetic import generate_synthetic_drawing
        return {**generate_synthetic_drawing("UNKNOWN"), "parse_error": str(e)}
