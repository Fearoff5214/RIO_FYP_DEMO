"""Synthetic defect-free brushed-metal plates, for demoing the anomaly model.

Real use: put 20-50 photos of known-good parts in data/good/<part_number>/ (or default/),
taken with the same camera and lighting as production, then POST /api/anomaly/fit.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

SIZE = 200


def plate(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.normal(150, 8, (SIZE, SIZE)).astype(np.float32)
    streaked = cv2.GaussianBlur(cv2.GaussianBlur(base, (1, 15), 0), (9, 1), 0)
    return cv2.cvtColor(np.clip(streaked, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/good/default")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    out.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        cv2.imwrite(str(out / f"good_{i:02d}.png"), plate(100 + i))
    print(f"wrote {n} images to {out}")
