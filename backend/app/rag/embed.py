"""Text embedding using sentence-transformers."""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _get_model():
    try:
        from sentence_transformers import SentenceTransformer
        from app.core.config import get_config
        cfg = get_config()
        model_name = cfg.get("embeddings", "model") or "sentence-transformers/all-MiniLM-L6-v2"
        return SentenceTransformer(model_name)
    except (ImportError, Exception):
        return None


async def embed_text(text: str) -> list[float]:
    """Embed a text string. Returns a list of floats."""
    model = _get_model()
    if model is None:
        # Fallback: return a fixed-length zero vector
        return [0.0] * 384

    import asyncio
    loop = asyncio.get_event_loop()
    embedding = await loop.run_in_executor(None, lambda: model.encode(text).tolist())
    return embedding


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts."""
    model = _get_model()
    if model is None:
        return [[0.0] * 384 for _ in texts]

    import asyncio
    loop = asyncio.get_event_loop()
    embeddings = await loop.run_in_executor(None, lambda: model.encode(texts).tolist())
    return embeddings
