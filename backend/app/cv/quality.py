"""Image quality gate (Stage 1) and the auto-adjust used by loop L2."""
import cv2
import numpy as np

from .. import config


def assess(img: np.ndarray) -> dict:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    glare = float((gray >= 250).mean())
    exposure = float(gray.mean())
    problems = []
    if blur < config.BLUR_MIN:
        problems.append("blur")
    if glare > config.GLARE_MAX:
        problems.append("glare")
    lo, hi = config.EXPOSURE_RANGE
    if not lo <= exposure <= hi:
        problems.append("exposure")
    return {"blur": round(blur, 2), "glare": round(glare, 4), "exposure": round(exposure, 1),
            "ok": not problems, "problems": problems}


def auto_adjust(img: np.ndarray, problems: list[str]) -> np.ndarray:
    """Software stand-in for a camera recipe change: correct exposure/glare, sharpen."""
    out = img.copy()
    if "exposure" in problems or "glare" in problems:
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        lab[..., 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[..., 0])
        out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    if "blur" in problems:
        soft = cv2.GaussianBlur(out, (0, 0), 3)
        out = cv2.addWeighted(out, 1.8, soft, -0.8, 0)
    return out
