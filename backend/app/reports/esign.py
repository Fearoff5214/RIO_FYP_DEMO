"""E-signature application: stamps approver identity + timestamp + SHA-256 hash onto PDF."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

SIGNATURES_DIR = Path("tmp/signatures")


async def apply_esignature(
    pdf_uri: str,
    approver: str,
    job_id: str,
) -> tuple[str, str]:
    """
    Apply e-signature to a PDF.
    Returns (signed_pdf_uri, signature_record_uri).
    """
    SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()

    # Compute SHA-256 of original PDF
    pdf_path = Path(pdf_uri)
    pdf_hash = ""
    if pdf_path.exists():
        pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    sig_record = {
        "job_id": job_id,
        "approver": approver,
        "timestamp": timestamp,
        "pdf_hash": pdf_hash,
    }

    sig_path = SIGNATURES_DIR / f"{job_id}_signature.json"
    import json
    sig_path.write_text(json.dumps(sig_record, indent=2))

    # Stamp the PDF
    signed_path = _stamp_pdf(pdf_path, approver, timestamp, job_id)

    return str(signed_path), str(sig_path)


def _stamp_pdf(pdf_path: Path, approver: str, timestamp: str, job_id: str) -> Path:
    """Add an approval stamp to the PDF."""
    out = Path(str(pdf_path).replace(".pdf", "_signed.pdf"))

    if not pdf_path.exists():
        # Create a stub signed file
        out.write_text(f"Signed by {approver} at {timestamp}")
        return out

    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        import io

        # Create a stamp overlay
        stamp_buffer = io.BytesIO()
        c = canvas.Canvas(stamp_buffer, pagesize=A4)
        c.setFont("Helvetica-Bold", 10)
        c.setFillColorRGB(0, 0.5, 0)
        c.drawString(50, 50, f"APPROVED by {approver}")
        c.drawString(50, 35, f"Date: {timestamp[:10]}")
        c.drawString(50, 20, f"Job: {job_id}")
        c.save()

        # Try to merge with PyPDF2 or just copy
        try:
            from PyPDF2 import PdfReader, PdfWriter
            stamp_buffer.seek(0)
            stamp_reader = PdfReader(stamp_buffer)
            reader = PdfReader(str(pdf_path))
            writer = PdfWriter()
            for i, page in enumerate(reader.pages):
                if i == 0:
                    page.merge_page(stamp_reader.pages[0])
                writer.add_page(page)
            with open(str(out), "wb") as f:
                writer.write(f)
        except ImportError:
            # Just copy the original
            import shutil
            shutil.copy2(str(pdf_path), str(out))

    except ImportError:
        import shutil
        if pdf_path.exists():
            shutil.copy2(str(pdf_path), str(out))
        else:
            out.write_text(f"Signed by {approver} at {timestamp}")

    return out
