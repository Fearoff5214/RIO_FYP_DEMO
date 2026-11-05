"""Standalone root cause analysis: stages 4 and 5 without the human gates.

Runs the same nodes as the inspection workflow (query -> retrieval -> re-rank -> evidence -> LLM ->
scoring -> top 3 -> calibration -> validation) on a list of defects, so detections from the demo or
any other source can be analysed and turned into an RCA document straight away.
"""
from __future__ import annotations

from app.workflow.nodes import s4_retrieval as s4
from app.workflow.nodes import s5_prediction as s5

SEVERITY = {"crack": "critical", "deformation": "major", "dent": "major", "size_mismatch": "major", "scratch": "minor"}


async def _apply(state: dict, step, **kwargs) -> None:
    state.update(await step(state, **kwargs))


async def run_rca(state: dict, db=None) -> dict:
    """Run the analysis on `state` (part_master, defects, measurements) and return the updated state.
    A part with no defects has nothing to analyse: the state is returned unchanged (a "no defect" report)."""
    if not state.get("defects"):
        return state
    state.setdefault("loops", {})
    state.setdefault("flags", [])
    for d in state.get("defects", []):
        if not d.get("severity"):
            d["severity"] = SEVERITY.get(d.get("defect_type", ""), "minor")

    await _apply(state, s4.build_query)
    for attempt in range(4):                                   # loop L4: relax the filters (part, process, material) if evidence is thin
        state["loops"]["L4"] = attempt
        for step in (s4.apply_filters, s4.embed_query, s4.graph_expand, s4.set_limits):
            await _apply(state, step)
        await _apply(state, s4.hybrid_retrieve, db=db)
        if not state.get("retrieved"):                         # empty knowledge base: use the built-in seed evidence
            await _apply(state, s4.hybrid_retrieve, db=None)
        await _apply(state, s4.rerank)
        if state.get("evidence_sufficient"):
            break
    if not state.get("evidence_sufficient"):
        state["flags"].append("low_evidence")
    await _apply(state, s4.assemble_evidence)

    for attempt in range(2):                                   # loop L5: one regeneration if the output is invalid
        for step in (s5.assemble_context, s5.llm_reason, s5.score_conf, s5.rank_top3, s5.calibrate, s5.format_top3):
            await _apply(state, step)
        if state.get("output_valid"):
            break
        if "low_confidence" not in state["flags"]:
            state["flags"].append("low_confidence")
    return state


def build_report(state: dict) -> dict:
    """Turn the analysed state into the report dict the RCA document renderer expects."""
    from datetime import datetime, timezone

    top3 = state.get("top3", []) or []
    primary = top3[0] if top3 else {}
    defects = state.get("defects", [])
    return {
        "evidence_images": state.get("evidence_images") or [],
        "verdict": "DEFECT" if defects else "NO_DEFECT",
        "job_id": state.get("job_id", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "part": {k: (state.get("part_master") or {}).get(k, "") for k in ("part_number", "part_name", "drawing_rev", "material", "process")},
        "defects": defects,
        "measurements": state.get("measurements", []),
        "root_cause": None if not defects else {
            "cause": primary.get("cause", ""),
            "effect": primary.get("effect", ""),
            "rationale": primary.get("rationale", ""),
            "corrective_actions": primary.get("corrective_actions") or [],
            "preventive_actions": primary.get("preventive_actions") or [],
            "precautions": primary.get("precautions") or [],
            "verification": primary.get("verification"),
            "citations": primary.get("citations") or [],
            "confidence": primary.get("confidence_cal"),
            "model_version": primary.get("model_version"),
            "edited": False,
        },
        "rca": None if not defects else {"ranked": top3, "evidence": (state.get("evidence_pack") or {}).get("sources", [])},
    }
