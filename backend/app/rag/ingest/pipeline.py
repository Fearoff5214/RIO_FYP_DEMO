"""
Knowledge base ingestion pipeline:
parse → chunk → tag → embed → index (vector + keyword + graph)
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any


async def ingest_document(
    file_path: str | Path,
    doc_type: str,
    title: str,
    meta: dict | None = None,
    db=None,
) -> dict:
    """
    Ingest a single document into the knowledge base.
    Idempotent: re-ingesting the same content is a no-op.
    Returns {doc_id, n_chunks, status}.
    """
    from app.core.logging import get_logger
    logger = get_logger(__name__)

    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    content = path.read_bytes()
    content_hash = hashlib.sha256(content).hexdigest()

    # Idempotency check
    if db is not None:
        from sqlalchemy import select
        from app.db.models import KBDocument
        existing = await db.execute(
            select(KBDocument).where(KBDocument.content_hash == content_hash)
        )
        if existing.scalar_one_or_none():
            logger.info('"ingest":"skip_duplicate","path":"%s"', path.name)
            return {"status": "skipped", "message": "Duplicate content"}

    # Parse text from document
    text = _parse_document(path)

    # Chunk the text
    chunks_text = _chunk_text(text, chunk_size=500, overlap=50)

    # Tag chunks
    tagged_chunks = [_tag_chunk(c, meta or {}) for c in chunks_text]

    # Embed chunks
    from app.rag.embed import embed_batch
    texts = [c["text"] for c in tagged_chunks]
    embeddings = await embed_batch(texts)

    doc_id = str(uuid.uuid4())

    if db is not None:
        from app.db.models import KBDocument, KBChunk
        doc_row = KBDocument(
            doc_id=doc_id,
            source_uri=str(path),
            doc_type=doc_type,
            title=title,
            meta=meta,
            content_hash=content_hash,
            version=1,
        )
        db.add(doc_row)

        for chunk_data, emb in zip(tagged_chunks, embeddings):
            chunk_row = KBChunk(
                chunk_id=str(uuid.uuid4()),
                doc_id=doc_id,
                text=chunk_data["text"],
                embedding=emb,
                defect_type=chunk_data.get("defect_type"),
                cause=chunk_data.get("cause"),
                part=chunk_data.get("part"),
                material=chunk_data.get("material"),
                process=chunk_data.get("process"),
                section=chunk_data.get("section"),
            )
            db.add(chunk_row)

        await db.commit()

    logger.info('"ingest":"complete","doc_id":"%s","n_chunks":%d', doc_id, len(tagged_chunks))
    return {"doc_id": doc_id, "n_chunks": len(tagged_chunks), "status": "ok"}


def _parse_document(path: Path) -> str:
    """Extract text from PDF, DOCX, XLSX, or plain text."""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _parse_pdf(path)
    elif suffix == ".docx":
        return _parse_docx(path)
    elif suffix in (".xlsx", ".xls"):
        return _parse_xlsx(path)
    else:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""


def _parse_pdf(path: Path) -> str:
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n".join(text_parts)
    except Exception:
        return ""


def _parse_docx(path: Path) -> str:
    try:
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""


def _parse_xlsx(path: Path) -> str:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        parts = []
        for sheet in wb.worksheets:
            headers = []
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if i == 0:
                    headers = [str(c or "") for c in row]
                else:
                    row_text = " | ".join(f"{h}:{v}" for h, v in zip(headers, row) if v is not None)
                    if row_text.strip():
                        parts.append(row_text)
        return "\n".join(parts)
    except Exception:
        return ""


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks by word count."""
    words = text.split()
    chunks = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks or [text[:2000]] if text else []


def _tag_chunk(text: str, meta: dict) -> dict:
    """Tag a chunk with metadata using rules + meta dict."""
    tags = {
        "text": text,
        "defect_type": meta.get("defect_type"),
        "cause": None,
        "part": meta.get("part"),
        "material": meta.get("material"),
        "process": meta.get("process"),
        "section": None,
    }

    text_lower = text.lower()

    # Simple rule-based tagger
    for dtype in ["scratch", "dent", "crack", "deformation"]:
        if dtype in text_lower:
            tags["defect_type"] = dtype
            break

    for cause_kw in [
        ("bending force", "Improper Bending Force"),
        ("over bending", "Improper Bending Force"),
        ("material inconsistency", "Material Inconsistency"),
        ("hardness variation", "Material Inconsistency"),
        ("tool wear", "Tool Wear / Die Damage"),
        ("die damage", "Tool Wear / Die Damage"),
        ("springback", "Springback"),
        ("lubrication", "Inadequate Lubrication"),
    ]:
        if cause_kw[0] in text_lower:
            tags["cause"] = cause_kw[1]
            break

    for mat in ["spcc", "steel", "aluminium", "aluminum", "stainless"]:
        if mat in text_lower:
            tags["material"] = mat
            break

    for proc in ["bending", "stamping", "welding", "cutting", "forming"]:
        if proc in text_lower:
            tags["process"] = proc
            break

    return tags
