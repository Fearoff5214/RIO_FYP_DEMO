"""Cross-encoder reranking of retrieved chunks."""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _get_reranker():
    try:
        from sentence_transformers import CrossEncoder
        return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    except (ImportError, Exception):
        return None


async def rerank_chunks(
    query: str,
    chunks: list[dict],
    keep: int = 8,
) -> list[dict]:
    """
    Rerank chunks using cross-encoder. Falls back to RRF score if model unavailable.
    """
    if not chunks:
        return []

    reranker = _get_reranker()

    if reranker is None:
        # Fallback: use existing RRF score
        sorted_chunks = sorted(chunks, key=lambda c: c.get("score", 0.0), reverse=True)
        return sorted_chunks[:keep]

    try:
        import asyncio
        pairs = [(query, c.get("text", "")) for c in chunks]
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(None, lambda: reranker.predict(pairs))

        reranked = sorted(
            [{**c, "score": float(s)} for c, s in zip(chunks, scores)],
            key=lambda x: x["score"],
            reverse=True,
        )
        return reranked[:keep]

    except Exception:
        sorted_chunks = sorted(chunks, key=lambda c: c.get("score", 0.0), reverse=True)
        return sorted_chunks[:keep]
