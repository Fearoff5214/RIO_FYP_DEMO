"""Sample simulated 3D-scanner point clouds (PLY) from the bracket variant meshes.

Run: py scripts/make_bracket_pointclouds.py   ->  docs/demo/pointclouds/MS-4505-001_<variant>.ply
Each cloud gets ~0.03 mm of Gaussian scanner noise and a random offset so the inspector's alignment is exercised.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bracket_variants as bv  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "demo" / "pointclouds"
SPACING_MM = 0.2


def sample_cloud(mesh: trimesh.Trimesh, spacing: float = SPACING_MM, noise: float = 0.03, seed: int = 7) -> np.ndarray:
    n = int(mesh.area / spacing ** 2)
    pts, _ = trimesh.sample.sample_surface_even(mesh, n, seed=seed)
    rng = np.random.default_rng(seed)
    return pts + rng.normal(0, noise, pts.shape) + rng.uniform(-30, 30, 3)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, variant in bv.make_variants().items():
        cloud = sample_cloud(bv.build_mesh(variant))
        path = OUT / f"MS-4505-001_{name}.ply"
        trimesh.PointCloud(cloud).export(path)
        print(f"{path.name}: {len(cloud):,} points")


if __name__ == "__main__":
    main()
