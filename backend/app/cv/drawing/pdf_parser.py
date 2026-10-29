"""PDF drawing parser using pdfplumber with OCR fallback."""
from __future__ import annotations

import re
from pathlib import Path


_DIM_PATTERN = re.compile(
    r"(Ø|R|⌀)?\s*(\d+\.?\d*)\s*(?:\(\s*([+-]?\d+\.?\d*)\s*\)|\+(\d+\.?\d*)/-(\d+\.?\d*))?",
    re.IGNORECASE,
)


def parse_pdf(drawing_uri: str) -> dict:
    """
    Parse a PDF drawing: extract dimension text via vector extraction or OCR.
    Falls back to synthetic if file missing or parsing fails.
    """
    path = Path(drawing_uri)
    if not path.exists():
        from app.cv.drawing.synthetic import generate_synthetic_drawing
        return generate_synthetic_drawing("UNKNOWN")

    try:
        import pdfplumber

        features = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                features.extend(_extract_dims_from_text(text))

        if not features:
            # OCR fallback: rasterize and run Tesseract
            features = _ocr_fallback(path)

        return {
            "part_number": path.stem,
            "format": "pdf",
            "features": features,
            "drawing_uri": drawing_uri,
            "detected_features": [],
            "parse_confidence": 0.8 if features else 0.3,
        }

    except Exception as e:
        from app.cv.drawing.synthetic import generate_synthetic_drawing
        return {**generate_synthetic_drawing("UNKNOWN"), "parse_error": str(e)}


def _extract_dims_from_text(text: str) -> list[dict]:
    """Extract dimensional values from text using regex."""
    features = []
    for i, m in enumerate(_DIM_PATTERN.finditer(text)):
        prefix, value, sym_tol, tol_plus, tol_minus = m.groups()
        try:
            nominal = float(value)
            if sym_tol:
                t = abs(float(sym_tol))
                tp, tm = t, t
            elif tol_plus and tol_minus:
                tp, tm = float(tol_plus), float(tol_minus)
            else:
                tp, tm = 0.10, 0.10

            ftype = "hole" if prefix in ("Ø", "⌀", "R") else "edge"
            features.append({
                "feature_id": f"D{i+1}",
                "feature_type": ftype,
                "nominal": nominal,
                "tol_plus": tp,
                "tol_minus": tm,
            })
        except (ValueError, TypeError):
            continue
    return features


def _ocr_fallback(path: Path) -> list[dict]:
    """OCR fallback using Tesseract via pytesseract (if installed)."""
    try:
        import pytesseract
        from PIL import Image as PILImage

        # rasterize first page via pdf2image if available
        try:
            from pdf2image import convert_from_path
            pages = convert_from_path(str(path), dpi=200, first_page=1, last_page=1)
            if pages:
                text = pytesseract.image_to_string(pages[0])
                return _extract_dims_from_text(text)
        except ImportError:
            pass
        return []
    except ImportError:
        return []
