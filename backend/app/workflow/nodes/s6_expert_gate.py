"""Stage 6 — Human Gate 2: Expert Final Decision nodes."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.logging import get_logger
from app.workflow.state import InspectionState

logger = get_logger(__name__)


async def gate2_expert(state: InspectionState) -> dict:
    """Human Gate 2 — interrupt for quality expert review."""
    from langgraph.types import interrupt

    top3 = state.get("top3", []) or []
    reranked = state.get("reranked", []) or []
    job_id = state.get("job_id", "")

    logger.info('"node":"gate2_expert","job_id":"%s"', job_id)

    payload = {
        "gate": "GATE2",
        "job_id": job_id,
        "top3": top3,
        "evidence_sources": [r.get("text_excerpt", "") for r in reranked[:3]],
        "flags": state.get("flags", []),
        "message": "Please review the top-3 root cause predictions and select or edit the final cause.",
    }

    decision = interrupt(payload)
    return {"gate2": decision, "status": "GATE2_DECIDED"}


async def finalize_actions(state: InspectionState) -> dict:
    """Finalize corrective and preventive actions from gate2 decision."""
    gate2 = state.get("gate2", {}) or {}
    top3 = state.get("top3", []) or []

    selected_rank = gate2.get("selected_rank", 1)
    selected = next((c for c in top3 if c.get("rank") == selected_rank), top3[0] if top3 else {})

    cause = gate2.get("edited_cause") or selected.get("cause", "")
    effect = selected.get("effect", "")
    precautions = selected.get("precautions", [])

    corrective = gate2.get("corrective", []) or precautions[:2]
    preventive = gate2.get("preventive", []) or precautions[2:]

    final_rca = {
        "job_id": state.get("job_id"),
        "selected_rank": selected_rank,
        "cause": cause,
        "effect": effect,
        "corrective_actions": corrective,
        "preventive_actions": preventive,
        "edited": bool(gate2.get("edited_cause")),
        "reviewer_id": gate2.get("reviewer_id"),
        "finalized_at": datetime.now(timezone.utc).isoformat(),
    }

    return {"final_rca": final_rca}


async def save_decision(state: InspectionState, *, db=None) -> dict:
    """Persist final_rca and gate_decision."""
    if db is None:
        return {}

    from app.db.models import FinalRCA, GateDecision

    job_id = state.get("job_id", "")
    final_rca = state.get("final_rca", {}) or {}
    gate2 = state.get("gate2", {}) or {}

    rca_row = FinalRCA(
        job_id=job_id,
        selected_rank=final_rca.get("selected_rank"),
        cause=final_rca.get("cause", ""),
        effect=final_rca.get("effect", ""),
        corrective_actions=final_rca.get("corrective_actions", []),
        preventive_actions=final_rca.get("preventive_actions", []),
        edited=final_rca.get("edited", False),
        reviewer_id=final_rca.get("reviewer_id"),
        finalized_at=datetime.now(timezone.utc),
    )
    db.add(rca_row)

    gd = GateDecision(
        job_id=job_id,
        gate="GATE2",
        reviewer_id=gate2.get("reviewer_id"),
        decision=gate2.get("decision"),
        reason_code=gate2.get("reason"),
        payload=gate2,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(gd)
    await db.commit()
    return {}


async def record_feedback(state: InspectionState, *, db=None) -> dict:
    """Record expert choice vs AI rank for L12 recalibration."""
    if db is None:
        return {}

    from app.db.models import Feedback

    job_id = state.get("job_id", "")
    gate2 = state.get("gate2", {}) or {}
    top3 = state.get("top3", []) or []

    fb = Feedback(
        job_id=job_id,
        kind="rca_choice",
        ai_value={"top3": top3},
        human_value={
            "selected_rank": gate2.get("selected_rank"),
            "edited": bool(gate2.get("edited_cause")),
            "decision": gate2.get("decision"),
        },
    )
    db.add(fb)
    await db.commit()
    return {}


async def mark_rca_final(state: InspectionState) -> dict:
    """Mark RCA as final — state checkpoint."""
    logger.info('"node":"mark_rca_final","job_id":"%s"', state.get("job_id"))
    return {"status": "REPORTING"}


async def manual_rca(state: InspectionState) -> dict:
    """Expert entered manual RCA (gate2 reject_all + manual)."""
    gate2 = state.get("gate2", {}) or {}
    manual_cause = gate2.get("manual_cause", "Manual RCA required")
    final_rca = {
        "job_id": state.get("job_id"),
        "selected_rank": None,
        "cause": manual_cause,
        "effect": gate2.get("manual_effect", ""),
        "corrective_actions": gate2.get("corrective", []),
        "preventive_actions": gate2.get("preventive", []),
        "edited": True,
        "reviewer_id": gate2.get("reviewer_id"),
        "finalized_at": datetime.now(timezone.utc).isoformat(),
    }
    flags = list(state.get("flags", []) or [])
    if "manual_rca" not in flags:
        flags.append("manual_rca")
    return {"final_rca": final_rca, "flags": flags, "status": "REPORTING"}
