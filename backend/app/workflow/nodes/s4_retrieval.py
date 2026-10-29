"""Stage 4 — Root-Cause Knowledge Retrieval nodes."""
from __future__ import annotations

from app.core.config import get_config
from app.core.logging import get_logger
from app.workflow.state import InspectionState

logger = get_logger(__name__)


async def build_query(state: InspectionState) -> dict:
    """Build retrieval query from defects, deviations, part, material, process."""
    defects = state.get("defects", []) or []
    measurements = state.get("measurements", []) or []
    part_master = state.get("part_master", {}) or {}

    defect_types = list({d.get("defect_type", "") for d in defects if d.get("defect_type")})
    out_of_tol = [m for m in measurements if not m.get("within_tolerance", True)]

    query_text = (
        f"Defects: {', '.join(defect_types)}. "
        f"Material: {part_master.get('material', 'sheet metal')}. "
        f"Process: {part_master.get('process', 'bending')}. "
        f"Part: {part_master.get('part_number', '')}. "
    )
    if out_of_tol:
        tol_desc = ", ".join(
            f"{m['feature_id']}: {m.get('deviation', 0):+.2f}mm" for m in out_of_tol[:3]
        )
        query_text += f"Out-of-tolerance: {tol_desc}."

    query = {
        "text": query_text,
        "defect_types": defect_types,
        "part_number": part_master.get("part_number"),
        "material": part_master.get("material"),
        "process": part_master.get("process"),
        "filters_applied": ["part", "material", "process", "defect_type"],
        "relaxation_level": state.get("loops", {}).get("L4", 0),
    }

    logger.info('"node":"build_query","defects":%s', defect_types)
    return {"query": query, "status": "RETRIEVAL"}


async def apply_filters(state: InspectionState) -> dict:
    """Apply (or relax) metadata filters for retrieval."""
    cfg = get_config()
    relax_order = cfg.get("retrieval", "filter_relax_order") or ["part", "process", "material"]
    query = dict(state.get("query", {}) or {})
    loops = state.get("loops", {}) or {}
    relaxation_level = loops.get("L4", 0)

    # Progressively drop filters
    active_filters = list(relax_order)
    for i in range(min(relaxation_level, len(relax_order))):
        if relax_order[i] in active_filters:
            active_filters.remove(relax_order[i])
            logger.info('"node":"apply_filters","dropped_filter":"%s"', relax_order[i])

    query["filters_applied"] = active_filters
    return {"query": query}


async def embed_query(state: InspectionState) -> dict:
    """Embed query text for dense retrieval."""
    from app.rag.embed import embed_text

    query = state.get("query", {}) or {}
    text = query.get("text", "")
    embedding = await embed_text(text)
    return {"query": {**query, "embedding": embedding}}


async def graph_expand(state: InspectionState) -> dict:
    """Expand query via knowledge graph edges (defect→cause→action)."""
    from app.rag.retrieve import graph_expand as _expand

    query = state.get("query", {}) or {}
    defect_types = query.get("defect_types", [])
    graph_context = await _expand(defect_types)
    return {"query": {**query, "graph_context": graph_context}}


async def set_limits(state: InspectionState) -> dict:
    """Set retrieval top-k limits from config."""
    cfg = get_config()
    query = dict(state.get("query", {}) or {})
    query["dense_top_k"] = cfg.get("retrieval", "dense_top_k") or 30
    query["keyword_top_k"] = cfg.get("retrieval", "keyword_top_k") or 30
    return {"query": query}


async def hybrid_retrieve(state: InspectionState, *, db=None) -> dict:
    """Hybrid dense + keyword retrieval with Reciprocal Rank Fusion."""
    from app.rag.retrieve import hybrid_retrieve as _retrieve

    query = state.get("query", {}) or {}
    logger.info('"node":"hybrid_retrieve","query_len":%d', len(query.get("text", "")))

    retrieved = await _retrieve(query, db=db)
    return {"retrieved": retrieved}


async def rerank(state: InspectionState) -> dict:
    """Cross-encoder reranking of retrieved chunks."""
    from app.rag.rerank import rerank_chunks

    retrieved = state.get("retrieved", []) or []
    query = state.get("query", {}) or {}
    cfg = get_config()
    keep = cfg.get("retrieval", "rerank_keep") or 8

    reranked = await rerank_chunks(query.get("text", ""), retrieved, keep=keep)

    # Sufficiency check
    threshold = float(cfg.get("retrieval", "similarity_threshold") or 0.55)
    min_chunks = int(cfg.get("retrieval", "min_chunks") or 3)
    max_score = max((r.get("score", 0.0) for r in reranked), default=0.0)
    sufficient = max_score >= threshold and len(reranked) >= min_chunks

    logger.info('"node":"rerank","n_reranked":%d,"max_score":%.3f,"sufficient":%s', len(reranked), max_score, sufficient)
    return {"reranked": reranked, "evidence_sufficient": sufficient}


async def assemble_evidence(state: InspectionState) -> dict:
    """Assemble evidence pack for Stage 5."""
    reranked = state.get("reranked", []) or []
    query = state.get("query", {}) or {}

    causes = [r.get("cause") for r in reranked if r.get("cause")]
    corrective = [r.get("corrective") for r in reranked if r.get("corrective")]
    preventive = [r.get("preventive") for r in reranked if r.get("preventive")]
    precautions = [r.get("precautions") for r in reranked if r.get("precautions")]
    sources = [
        {
            "doc_id": r.get("doc_id", ""),
            "chunk_id": r.get("chunk_id", ""),
            "score": r.get("score", 0.0),
            "uri": r.get("uri", ""),
            "text_excerpt": r.get("text", "")[:200],
        }
        for r in reranked
    ]

    evidence_pack = {
        "causes": list(set(filter(None, causes))),
        "corrective": list(set(filter(None, corrective))),
        "preventive": list(set(filter(None, preventive))),
        "precautions": list(set(filter(None, precautions))),
        "sources": sources,
        "defect_types": query.get("defect_types", []),
        "material": query.get("material"),
        "process": query.get("process"),
        "query_text": query.get("text", ""),
    }

    logger.info('"node":"assemble_evidence","n_sources":%d', len(sources))
    return {"evidence_pack": evidence_pack, "status": "PREDICTION"}
