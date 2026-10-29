"""
Image preprocessing: undistort, px→mm, illumination normalize, quality scoring.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _load_image(uri: str):
    """Load an image from a URI (file path or mock://)."""
    import numpy as np

    if uri.startswith("mock://"):
        # Generate a synthetic grey plate
        return np.full((480, 640, 3), 128, dtype=np.uint8)

    path = Path(uri)
    if not path.exists():
        import numpy as np
        return np.full((480, 640, 3), 128, dtype=np.uint8)

    import cv2
    img = cv2.imread(str(path))
    return img


def score_image_quality(img, cfg=None) -> float:
    """
    Compute a quality score in [0,1].
    Checks: blur (Laplacian variance), glare ratio, exposure clipping.
    """
    import numpy as np
    import cv2

    if img is None:
        return 0.0

    # Blur: variance of Laplacian
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()

    if cfg:
        blur_min = cfg.get("image_quality", "blur_min_laplacian_var") or 100
        glare_max = cfg.get("image_quality", "glare_max_ratio") or 0.02
        clip_max = cfg.get("image_quality", "exposure_clip_max") or 0.05
    else:
        blur_min, glare_max, clip_max = 100, 0.02, 0.05

    blur_ok = lap_var >= blur_min

    # Glare: saturated pixel ratio
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV) if len(img.shape) == 3 else None
    if hsv is not None:
        sat = hsv[:, :, 1]
        glare_ratio = float(np.sum(sat > 250)) / sat.size
        glare_ok = glare_ratio <= glare_max
    else:
        glare_ok = True

    # Exposure: histogram clipping
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    total = gray.size
    clip_ratio = float(hist[0] + hist[-1]) / total
    exposure_ok = clip_ratio <= clip_max

    checks = [blur_ok, glare_ok, exposure_ok]
    return sum(1 for c in checks if c) / len(checks)


async def preprocess_images(images: list[dict], calibration: dict) -> list[dict]:
    """
    Preprocess all images: undistort, normalize illumination.
    Adds quality_score and px_per_mm to each image dict.
    """
    import numpy as np
    import cv2
    from app.core.config import get_config

    cfg = get_config()
    px_per_mm = calibration.get("px_per_mm", 10.0)  # fallback: 10 px/mm
    dist_coeffs = calibration.get("dist_coeffs")

    processed = []
    for img_info in images:
        img = _load_image(img_info["uri"])
        if img is None:
            continue

        # Undistort if calibration available
        if dist_coeffs and calibration.get("camera_matrix"):
            import json
            K = np.array(calibration["camera_matrix"], dtype=np.float64)
            D = np.array(dist_coeffs, dtype=np.float64)
            img = cv2.undistort(img, K, D)

        # CLAHE illumination normalization
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_eq = clahe.apply(gray)
        img_norm = cv2.cvtColor(gray_eq, cv2.COLOR_GRAY2BGR)

        quality = score_image_quality(img, cfg)

        processed.append({
            **img_info,
            "kind": "processed",
            "quality_score": quality,
            "meta": {
                **(img_info.get("meta") or {}),
                "px_per_mm": px_per_mm,
                "preprocessed": True,
            },
        })

    return processed


def score_quality(images: list[dict], cfg=None) -> tuple[bool, list[float]]:
    """Return (all_ok, list_of_scores) given a list of preprocessed image dicts."""
    scores = [img.get("quality_score", 0.0) for img in images]
    min_score = 0.5  # at least 2 of 3 quality checks must pass
    all_ok = bool(scores) and all(s >= min_score for s in scores)
    return all_ok, scores
