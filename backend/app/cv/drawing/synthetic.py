"""
Synthetic DXF drawing and part master generator for demo / CI.
Generates a sheet-metal bracket (MS-4505-001) with known features.
"""
from __future__ import annotations

from pathlib import Path


# Synthetic part master for MS-4505-001
DEMO_PART = {
    "part_number": "MS-4505-001",
    "part_name": "Sheet Metal Bracket",
    "drawing_rev": "A",
    "drawing_uri": "synthetic://MS-4505-001.dxf",
    "material": "SPCC Steel",
    "process": "Bending",
    "tolerances": {
        "default": {"plus": 0.10, "minus": 0.10},
        "hole": {"plus": 0.05, "minus": 0.05},
    },
    "camera_recipe": {
        "angles": ["top", "side_left"],
        "exposure": 50,
        "lighting": "diffuse",
        "resolution": "1920x1080",
    },
    "calibration": {
        "px_per_mm": 10.0,
        "camera_matrix": None,
        "dist_coeffs": None,
    },
}

# Synthetic dimensional features (from infographic)
DEMO_FEATURES = [
    {"feature_id": "L1", "feature_type": "edge", "nominal": 120.0, "tol_plus": 0.10, "tol_minus": 0.10},
    {"feature_id": "L2", "feature_type": "edge", "nominal": 80.0, "tol_plus": 0.10, "tol_minus": 0.10},
    {"feature_id": "H1", "feature_type": "hole", "nominal": 12.0, "tol_plus": 0.05, "tol_minus": 0.05},
    {"feature_id": "L3", "feature_type": "edge", "nominal": 50.0, "tol_plus": 0.10, "tol_minus": 0.10},
    {"feature_id": "T1", "feature_type": "thickness", "nominal": 2.0, "tol_plus": 0.10, "tol_minus": 0.10},
]


def generate_synthetic_part_master(part_number: str) -> dict:
    """Return a synthetic part master dict for the given PN."""
    master = dict(DEMO_PART)
    master["part_number"] = part_number
    return master


def generate_synthetic_drawing(part_number: str) -> dict:
    """Return a synthetic drawing dict with features and tolerances."""
    return {
        "part_number": part_number,
        "format": "synthetic",
        "features": DEMO_FEATURES,
        "drawing_uri": f"synthetic://{part_number}.dxf",
        "detected_features": [],
    }


def generate_synthetic_dxf(output_path: str | Path) -> Path:
    """Write a simple DXF file to disk for part MS-4505-001."""
    try:
        import ezdxf

        doc = ezdxf.new("R2010")
        msp = doc.modelspace()

        # Outer rectangle 120 × 80
        msp.add_lwpolyline(
            [(0, 0), (120, 0), (120, 80), (0, 80), (0, 0)],
            close=True,
        )
        # Hole circles at corners
        msp.add_circle((15, 15), radius=6.0)
        msp.add_circle((105, 15), radius=6.0)
        msp.add_circle((15, 65), radius=6.0)
        msp.add_circle((105, 65), radius=6.0)
        # Centre hole
        msp.add_circle((60, 40), radius=6.0)

        # Add DIMENSION entities
        dimstyle = doc.dimstyles.get("Standard")
        msp.add_linear_dim(
            base=(60, -15),
            p1=(0, 0),
            p2=(120, 0),
            dimstyle="Standard",
            override={"dimtxt": 3},
        )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(str(out))
        return out

    except ImportError:
        # ezdxf not installed; write a minimal text stub
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("# synthetic DXF stub (ezdxf not installed)")
        return out
