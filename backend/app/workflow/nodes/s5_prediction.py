"""Stage 5 — AI Prediction & Recommendation nodes."""
from __future__ import annotations

from app.core.config import get_config
from app.core.logging import get_logger
from app.workflow.state import InspectionState

logger = get_logger(__name__)


async def assemble_context(state: InspectionState) -> dict:
    """Assemble the full LLM prompt context from defects, deviations, and evidence."""
    defects = state.get("defects", []) or []
    measurements = state.get("measurements", []) or []
    evidence_pack = state.get("evidence_pack", {}) or {}
    part_master = state.get("part_master", {}) or {}

    out_of_tol = [m for m in measurements if not m.get("within_tolerance", True)]

    context = {
        "part_number": part_master.get("part_number", ""),
        "part_name": part_master.get("part_name", ""),
        "material": part_master.get("material", "sheet metal"),
        "process": part_master.get("process", "bending"),
        "defects": [
            {
                "type": d.get("defect_type"),
                "severity": d.get("severity"),
                "size_mm2": d.get("size_mm2"),
                "confidence": d.get("confidence"),
            }
            for d in defects
        ],
        "out_of_tolerance": out_of_tol[:5],
        "evidence": evidence_pack,
    }

    return {"query": {**(state.get("query") or {}), "llm_context": context}}


async def llm_reason(state: InspectionState) -> dict:
    """Call the LLM to generate candidate root causes."""
    from app.llm.factory import get_llm_provider

    cfg = get_config()
    evidence_pack = state.get("evidence_pack", {}) or {}
    query = state.get("query", {}) or {}
    flags = state.get("flags", []) or []

    logger.info('"node":"llm_reason","job_id":"%s"', state.get("job_id"))

    provider = get_llm_provider(cfg)
    candidates = await provider.generate_root_causes(
        context=query.get("llm_context", {}),
        evidence=evidence_pack,
        regenerate="low_confidence" in flags,
    )

    return {"candidates": candidates}


async def score_conf(state: InspectionState) -> dict:
    """Score confidence for each candidate using retrieval + history + detection."""
    from app.scoring.confidence import score_candidates

    candidates = state.get("candidates", []) or []
    reranked = state.get("reranked", []) or []
    defects = state.get("defects", []) or []
    cfg = get_config()
    weights = cfg.get("prediction", "confidence_weights") or {
        "retrieval": 0.5,
        "history": 0.3,
        "detection": 0.2,
    }

    scored = score_candidates(candidates, reranked, defects, weights)
    return {"candidates": scored}


async def rank_top3(state: InspectionState) -> dict:
    """Sort by score and take top 3."""
    candidates = state.get("candidates", []) or []
    sorted_cands = sorted(candidates, key=lambda c: c.get("confidence_raw", 0), reverse=True)
    top3 = sorted_cands[:3]

    # Assign ranks
    for i, c in enumerate(top3):
        c["rank"] = i + 1

    return {"top3": top3}


async def calibrate(state: InspectionState) -> dict:
    """Apply calibration to confidence scores."""
    from app.scoring.calibration import calibrate_scores

    top3 = state.get("top3", []) or []
    top3_cal = await calibrate_scores(top3)
    return {"top3": top3_cal}


async def format_top3(state: InspectionState) -> dict:
    """Validate and format top-3 output; set output_valid flag."""
    from app.llm.validators import validate_top3

    top3 = state.get("top3", []) or []
    reranked = state.get("reranked", []) or []

    valid, issues = validate_top3(top3, reranked)

    if not valid:
        logger.warning('"node":"format_top3","issues":"%s"', issues)
    else:
        logger.info('"node":"format_top3","confidences":%s',
                    [round(c.get("confidence_cal", 0), 2) for c in top3])

    return {"output_valid": valid}


async def save_ranked(state: InspectionState, *, db=None) -> dict:
    """Persist root_cause_prediction rows."""
    top3 = state.get("top3", []) or []
    job_id = state.get("job_id", "")

    if db is not None:
        from app.db.models import RootCausePrediction

        for c in top3:
            row = RootCausePrediction(
                job_id=job_id,
                rank=c.get("rank", 0),
                cause=c.get("cause", ""),
                effect=c.get("effect", ""),
                precautions=c.get("precautions", []),
                confidence_raw=c.get("confidence_raw", 0.0),
                confidence_cal=c.get("confidence_cal", 0.0),
                evidence=c.get("citations", []),
                model_version=c.get("model_version"),
            )
            db.add(row)
        await db.commit()

    return {"status": "AWAIT_GATE2"}
