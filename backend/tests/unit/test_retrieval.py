"""Unit tests for RAG retrieval."""
import pytest


def test_cosine_sim_identical():
    from app.rag.retrieve import _cosine_sim
    v = [1.0, 0.0, 0.5]
    assert _cosine_sim(v, v) == pytest.approx(1.0, abs=0.001)


def test_cosine_sim_orthogonal():
    from app.rag.retrieve import _cosine_sim
    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]
    assert _cosine_sim(v1, v2) == pytest.approx(0.0, abs=0.001)


def test_rrf_single_list():
    from app.rag.retrieve import _rrf
    ranking = ["a", "b", "c"]
    scores = _rrf([ranking])
    assert scores["a"] > scores["b"] > scores["c"]


def test_seed_chunks_return_all_causes():
    from app.rag.retrieve import _get_seed_chunks
    chunks = _get_seed_chunks()
    causes = {c.get("cause") for c in chunks}
    assert "Improper Bending Force / Over Bending" in causes
    assert "Material Inconsistency / Hardness Variation" in causes
    assert "Tool Wear / Die Damage" in causes


@pytest.mark.asyncio
async def test_hybrid_retrieve_seed():
    from app.rag.retrieve import hybrid_retrieve

    query = {
        "text": "deformation bending force sheet metal",
        "embedding": None,
        "defect_types": ["deformation"],
        "filters_applied": [],
        "dense_top_k": 10,
        "keyword_top_k": 10,
    }
    results = await hybrid_retrieve(query, db=None)
    assert len(results) > 0
    # Top result should be about bending force
    top = results[0]
    assert top.get("text") is not None
