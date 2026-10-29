"""Stage 8 — Final Output, Actions & Continuous Learning nodes."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.logging import get_logger
from app.workflow.state import InspectionState

logger = get_logger(__name__)


async def final_output(state: InspectionState) -> dict:
    """Compose the final quality intelligence output payload."""
    defects = state.get("defects", []) or []
    final_rca = state.get("final_rca", {}) or {}
    fast_path = state.get("fast_path", False)

    output = {
        "job_id": state.get("job_id"),
        "dimensional_status": state.get("dimensional_status", "PASS"),
        "defects_found": len(defects),
        "defect_summary": [
            {"type": d.get("defect_type"), "severity": d.get("severity"), "size_mm2": d.get("size_mm2")}
            for d in defects
        ],
        "root_cause": final_rca.get("cause") if not fast_path else None,
        "effect_impact": final_rca.get("effect") if not fast_path else None,
        "corrective_actions": final_rca.get("corrective_actions", []) if not fast_path else [],
        "preventive_actions": final_rca.get("preventive_actions", []) if not fast_path else [],
        "approval_status": "AI + Human Approved",
        "flags": state.get("flags", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info('"node":"final_output","job_id":"%s"', state.get("job_id"))
    return {"dispatched": False, "status": "OUTPUT"}


async def dispatch_results(state: InspectionState) -> dict:
    """Dispatch final output to dashboard, MES, QMS, ERP."""
    from app.notifications.dispatcher import dispatch_final_output

    await dispatch_final_output(state)
    return {"dispatched": True}


async def track_actions(state: InspectionState, *, db=None) -> dict:
    """Create corrective_action rows in DB."""
    if db is None:
        return {}

    from app.db.models import CorrectiveAction

    job_id = state.get("job_id", "")
    final_rca = state.get("final_rca", {}) or {}
    actions = final_rca.get("corrective_actions", []) + final_rca.get("preventive_actions", [])

    for action_desc in actions:
        if isinstance(action_desc, str):
            row = CorrectiveAction(
                job_id=job_id,
                description=action_desc,
                status="OPEN",
            )
            db.add(row)

    await db.commit()
    return {}


async def close_case(state: InspectionState, *, db=None) -> dict:
    """Mark job as CLOSED."""
    job_id = state.get("job_id", "")
    logger.info('"node":"close_case","job_id":"%s"', job_id)

    if db is not None:
        from sqlalchemy import select, update
        from app.db.models import InspectionJob
        from app.db.audit import write_audit

        await db.execute(
            update(InspectionJob)
            .where(InspectionJob.job_id == job_id)
            .values(status="CLOSED", updated_at=datetime.now(timezone.utc))
        )
        await db.commit()
        await write_audit(db, "case_closed", job_id=job_id, node="close_case")

    return {"case_closed": True, "status": "CLOSED"}


async def learning_hub(state: InspectionState) -> dict:
    """Trigger background learning jobs (L10, L11, L12)."""
    from app.learning.hub import trigger_learning

    job_id = state.get("job_id", "")
    logger.info('"node":"learning_hub","job_id":"%s"', job_id)
    await trigger_learning(job_id, state)
    return {}
