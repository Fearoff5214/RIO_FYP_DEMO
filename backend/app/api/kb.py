"""Knowledge Base API endpoints."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_role
from app.db.session import get_db

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form("rca"),
    title: str = Form(""),
    part: str = Form(None),
    material: str = Form(None),
    process: str = Form(None),
    defect_type: str = Form(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "expert")),
):
    """Upload and ingest a document into the knowledge base."""
    from app.rag.ingest.pipeline import ingest_document

    # Save uploaded file temporarily
    suffix = Path(file.filename).suffix if file.filename else ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    meta = {
        k: v for k, v in {
            "part": part,
            "material": material,
            "process": process,
            "defect_type": defect_type,
        }.items() if v
    }

    result = await ingest_document(
        file_path=tmp_path,
        doc_type=doc_type,
        title=title or file.filename or "Untitled",
        meta=meta,
        db=db,
    )

    return result


@router.get("/documents")
async def list_documents(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all knowledge base documents."""
    from sqlalchemy import select
    from app.db.models import KBDocument

    result = await db.execute(select(KBDocument).order_by(KBDocument.ingested_at.desc()))
    docs = result.scalars().all()

    return [
        {
            "doc_id": d.doc_id,
            "title": d.title,
            "doc_type": d.doc_type,
            "source_uri": d.source_uri,
            "ingested_at": d.ingested_at.isoformat(),
            "version": d.version,
        }
        for d in docs
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Delete a KB document and its chunks."""
    from sqlalchemy import delete
    from app.db.models import KBDocument, KBChunk

    await db.execute(delete(KBChunk).where(KBChunk.doc_id == doc_id))
    await db.execute(delete(KBDocument).where(KBDocument.doc_id == doc_id))
    await db.commit()
    return {"deleted": doc_id}


@router.post("/reindex")
async def reindex(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Trigger full re-indexing of all KB documents."""
    from sqlalchemy import select
    from app.db.models import KBDocument, KBChunk
    from app.rag.embed import embed_text

    result = await db.execute(select(KBChunk).where(KBChunk.embedding.is_(None)))
    chunks = result.scalars().all()

    updated = 0
    for chunk in chunks:
        emb = await embed_text(chunk.text)
        chunk.embedding = emb
        db.add(chunk)
        updated += 1

    await db.commit()
    return {"status": "reindexed", "chunks_updated": updated}


@router.get("/search")
async def search_kb(
    q: str,
    defect_type: str | None = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Test search against the knowledge base."""
    from app.rag.retrieve import hybrid_retrieve
    from app.rag.rerank import rerank_chunks
    from app.rag.embed import embed_text

    embedding = await embed_text(q)
    query = {
        "text": q,
        "embedding": embedding,
        "defect_types": [defect_type] if defect_type else [],
        "filters_applied": [],
        "dense_top_k": limit * 2,
        "keyword_top_k": limit * 2,
    }

    retrieved = await hybrid_retrieve(query, db=db)
    reranked = await rerank_chunks(q, retrieved, keep=limit)

    return {
        "query": q,
        "results": [
            {
                "chunk_id": r.get("chunk_id"),
                "text": r.get("text", "")[:300],
                "score": r.get("score"),
                "defect_type": r.get("defect_type"),
                "cause": r.get("cause"),
            }
            for r in reranked
        ],
    }
