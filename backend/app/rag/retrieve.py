"""
Hybrid retrieval: dense vector + keyword BM25 with Reciprocal Rank Fusion.
Falls back to in-memory search when pgvector is not available (SQLite mode).
"""
from __future__ import annotations

import math
from typing import Any


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion over multiple ranked lists of chunk IDs."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (k + rank)
    return scores


async def hybrid_retrieve(query: dict, db=None) -> list[dict]:
    """
    Perform hybrid (dense + keyword) retrieval.
    In SQLite/no-pgvector mode: cosine sim on stored embeddings + simple keyword match.
    """
    from app.rag.embed import embed_text

    query_text = query.get("text", "")
    filters = query.get("filters_applied", [])
    dense_k = int(query.get("dense_top_k", 30))
    keyword_k = int(query.get("keyword_top_k", 30))

    query_embedding = query.get("embedding") or await embed_text(query_text)

    # Fetch chunks from DB
    chunks = await _fetch_chunks(db, query, filters)

    if not chunks:
        return []

    # Dense ranking
    def dense_score(chunk: dict) -> float:
        emb = chunk.get("embedding")
        if emb and isinstance(emb, list):
            return _cosine_sim(query_embedding, emb)
        return 0.0

    # Keyword ranking (simple term overlap)
    query_terms = set(query_text.lower().split())

    def keyword_score(chunk: dict) -> float:
        text = (chunk.get("text") or "").lower()
        hits = sum(1 for t in query_terms if t in text)
        return hits / max(len(query_terms), 1)

    dense_ranked = sorted(chunks, key=dense_score, reverse=True)[:dense_k]
    keyword_ranked = sorted(chunks, key=keyword_score, reverse=True)[:keyword_k]

    dense_ids = [c["chunk_id"] for c in dense_ranked]
    keyword_ids = [c["chunk_id"] for c in keyword_ranked]

    rrf_scores = _rrf([dense_ids, keyword_ids])
    chunk_map = {c["chunk_id"]: c for c in chunks}

    result = sorted(
        [
            {**chunk_map[cid], "score": score}
            for cid, score in rrf_scores.items()
            if cid in chunk_map
        ],
        key=lambda x: x["score"],
        reverse=True,
    )

    return result


async def _fetch_chunks(db, query: dict, filters: list[str]) -> list[dict]:
    """Fetch chunks from DB with optional metadata filters."""
    if db is None:
        # In-memory fallback: return seed KB
        return _get_seed_chunks()

    try:
        from sqlalchemy import select
        from app.db.models import KBChunk

        stmt = select(KBChunk)

        # Apply filters
        part = query.get("part_number")
        material = query.get("material")
        process = query.get("process")
        defect_types = query.get("defect_types", [])

        if "part" in filters and part:
            stmt = stmt.where(KBChunk.part == part)
        if "material" in filters and material:
            stmt = stmt.where(KBChunk.material == material)
        if "process" in filters and process:
            stmt = stmt.where(KBChunk.process == process)
        if defect_types:
            stmt = stmt.where(KBChunk.defect_type.in_(defect_types))

        result = await db.execute(stmt)
        rows = result.scalars().all()

        return [
            {
                "chunk_id": r.chunk_id,
                "doc_id": r.doc_id,
                "text": r.text,
                "embedding": r.embedding,
                "defect_type": r.defect_type,
                "cause": r.cause,
                "part": r.part,
                "material": r.material,
                "process": r.process,
                "score": 0.0,
                "uri": f"kb://chunk/{r.chunk_id}",
            }
            for r in rows
        ]
    except Exception:
        return _get_seed_chunks()


async def graph_expand(defect_types: list[str]) -> list[dict]:
    """Expand defect types to causes via knowledge graph (simple lookup)."""
    GRAPH = {
        "scratch": ["Improper handling", "Tool wear", "Abrasive particles"],
        "dent": ["Improper Bending Force", "Fixture defect", "Tooling damage"],
        "crack": ["Material Inconsistency", "Excessive stress", "Hardness variation"],
        "deformation": ["Improper Bending Force", "Springback", "Tool Wear/Die Damage"],
    }

    nodes = []
    for dtype in defect_types:
        for cause in GRAPH.get(dtype.lower(), []):
            nodes.append({"src": dtype, "rel": "causes", "dst": cause, "weight": 1.0})
    return nodes


def _get_seed_chunks() -> list[dict]:
    """Return hardcoded seed chunks matching the infographic scenario."""
    return [
        {
            "chunk_id": "seed-001",
            "doc_id": "seed-doc-001",
            "text": "Improper Bending Force or Over Bending causes deformation and dimensional inaccuracy. "
                    "Precautions: optimize bending parameters, use proper tooling, calibrate machines regularly.",
            "embedding": None,
            "defect_type": "deformation",
            "cause": "Improper Bending Force / Over Bending",
            "part": None,
            "material": "sheet metal",
            "process": "bending",
            "score": 0.85,
            "uri": "kb://seed/001",
        },
        {
            "chunk_id": "seed-002",
            "doc_id": "seed-doc-002",
            "text": "Material Inconsistency and Hardness Variation lead to unpredictable deformation and cracking. "
                    "Corrective actions: verify material certificates, incoming material inspection, supplier audit.",
            "embedding": None,
            "defect_type": "crack",
            "cause": "Material Inconsistency / Hardness Variation",
            "part": None,
            "material": "sheet metal",
            "process": "bending",
            "score": 0.72,
            "uri": "kb://seed/002",
        },
        {
            "chunk_id": "seed-003",
            "doc_id": "seed-doc-003",
            "text": "Tool Wear and Die Damage cause scratches, dents and dimensional variations. "
                    "Preventive actions: regular tooling inspection, preventive maintenance schedule, die regrinding.",
            "embedding": None,
            "defect_type": "scratch",
            "cause": "Tool Wear / Die Damage",
            "part": None,
            "material": "sheet metal",
            "process": "bending",
            "score": 0.65,
            "uri": "kb://seed/003",
        },
        {
            "chunk_id": "seed-004",
            "doc_id": "seed-doc-004",
            "text": "Springback in sheet metal bending causes dimensional inaccuracy. "
                    "Overbend compensation and material property testing are required.",
            "embedding": None,
            "defect_type": "deformation",
            "cause": "Springback",
            "part": None,
            "material": "sheet metal",
            "process": "bending",
            "score": 0.60,
            "uri": "kb://seed/004",
        },
    ]
