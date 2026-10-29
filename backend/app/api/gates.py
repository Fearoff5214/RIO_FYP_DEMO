"""Human Gate API endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_role
from app.db.session import get_db

router = APIRouter(prefix="/gates", tags=["gates"])


# ── Gate 1 — Dimensional Review ───────────────────────────────────────────────

class Gate1Request(BaseModel):
    decision: str  # confirm | reject | override
    reason_code: str | None = None
    comments: str | None = None
    overrides: list[dict] = []


@router.get("/1/{job_id}")
async def get_gate1(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("engineer", "admin")),
):
    """Get dimensional results for Gate 1 review."""
    from sqlalchemy import select
    from app.db.models import DimensionResult, ImageAsset

    dim_result = await db.execute(select(DimensionResult).where(DimensionResult.job_id == job_id))
    dims = dim_result.scalars().all()

    overlay_result = await db.execute(
        select(ImageAsset).where(ImageAsset.job_id == job_id, ImageAsset.kind == "overlay")
    )
    overlays = overlay_result.scalars().all()

    return {
        "job_id": job_id,
        "gate": "GATE1",
        "measurements": [
            {
                "feature_id": d.feature_id,
                "feature_type": d.feature_type,
                "nominal": d.nominal,
                "measured": d.measured,
                "deviation": d.deviation,
                "tol_plus": d.tol_plus,
                "tol_minus": d.tol_minus,
                "within_tolerance": d.within_tolerance,
            }
            for d in dims
        ],
        "overlay_uri": overlays[0].uri if overlays else None,
        "instructions": "Review dimensional deviations. Confirm, reject for re-measurement, or override with reason.",
    }


@router.post("/1/{job_id}")
async def submit_gate1(
    job_id: str,
    req: Gate1Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("engineer", "admin")),
):
    """Submit Gate 1 decision."""
    if req.decision == "override" and not req.reason_code:
        raise HTTPException(status_code=422, detail="Override requires a reason_code")

    decision_payload = {
        "decision": req.decision,
        "reviewer_id": user.get("sub"),
        "reason_code": req.reason_code,
        "comments": req.comments,
        "overrides": req.overrides,
    }

    await _resume_gate(job_id, "GATE1", decision_payload)
    return {"job_id": job_id, "gate": "GATE1", "decision": req.decision}


# ── Label Review Gate ─────────────────────────────────────────────────────────

class LabelReviewRequest(BaseModel):
    corrections: list[dict] = []  # [{defect_id, defect_type}]
    reviewer_id: str | None = None


@router.get("/label/{job_id}")
async def get_label_review(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("engineer", "admin")),
):
    """Get low-confidence detections for label review."""
    from sqlalchemy import select
    from app.db.models import Defect

    result = await db.execute(select(Defect).where(Defect.job_id == job_id))
    defects = result.scalars().all()

    return {
        "job_id": job_id,
        "gate": "LABEL",
        "defects": [
            {
                "defect_id": d.defect_id,
                "defect_type": d.defect_type,
                "confidence": d.confidence,
                "severity": d.severity,
                "bbox": d.bbox,
            }
            for d in defects
        ],
        "instructions": "Review and correct defect labels for low-confidence detections.",
    }


@router.post("/label/{job_id}")
async def submit_label_review(
    job_id: str,
    req: LabelReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("engineer", "admin")),
):
    """Submit label corrections."""
    decision = {
        "corrections": req.corrections,
        "reviewer_id": req.reviewer_id or user.get("sub"),
    }
    await _resume_gate(job_id, "LABEL", decision)
    return {"job_id": job_id, "gate": "LABEL", "n_corrections": len(req.corrections)}


# ── Gate 2 — Expert RCA Review ────────────────────────────────────────────────

class Gate2Request(BaseModel):
    decision: str  # accept | edit | reject_all
    selected_rank: int = 1
    edited_cause: str | None = None
    reason: str | None = None
    corrective: list[str] = []
    preventive: list[str] = []
    next: str = "reinspect"  # reinspect | manual_rca
    manual_cause: str | None = None
    manual_effect: str | None = None


@router.get("/2/{job_id}")
async def get_gate2(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("expert", "admin")),
):
    """Get top-3 root cause predictions for Gate 2 review."""
    from sqlalchemy import select
    from app.db.models import RootCausePrediction

    result = await db.execute(
        select(RootCausePrediction)
        .where(RootCausePrediction.job_id == job_id)
        .order_by(RootCausePrediction.rank)
    )
    preds = result.scalars().all()

    return {
        "job_id": job_id,
        "gate": "GATE2",
        "top3": [
            {
                "rank": p.rank,
                "cause": p.cause,
                "effect": p.effect,
                "precautions": p.precautions,
                "confidence_raw": p.confidence_raw,
                "confidence_cal": p.confidence_cal,
                "evidence": p.evidence,
            }
            for p in preds
        ],
        "instructions": "Select or edit the final root cause. Provide corrective and preventive actions.",
    }


@router.post("/2/{job_id}")
async def submit_gate2(
    job_id: str,
    req: Gate2Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("expert", "admin")),
):
    """Submit Gate 2 expert decision."""
    if req.decision == "edit" and not req.edited_cause:
        raise HTTPException(status_code=422, detail="Edit decision requires edited_cause")

    decision = {
        "decision": req.decision,
        "selected_rank": req.selected_rank,
        "edited_cause": req.edited_cause,
        "reason": req.reason,
        "corrective": req.corrective,
        "preventive": req.preventive,
        "next": req.next,
        "manual_cause": req.manual_cause,
        "manual_effect": req.manual_effect,
        "reviewer_id": user.get("sub"),
    }
    await _resume_gate(job_id, "GATE2", decision)
    return {"job_id": job_id, "gate": "GATE2", "decision": req.decision}


# ── Gate 3 — Approver ─────────────────────────────────────────────────────────

class Gate3Request(BaseModel):
    decision: str  # approve | reject
    comments: str | None = None


@router.get("/3/{job_id}")
async def get_gate3(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("approver", "admin")),
):
    """Get report details for Gate 3 approval."""
    from sqlalchemy import select
    from app.db.models import Report

    result = await db.execute(
        select(Report).where(Report.job_id == job_id).order_by(Report.version.desc())
    )
    report = result.scalars().first()

    return {
        "job_id": job_id,
        "gate": "GATE3",
        "report": {
            "version": report.version if report else None,
            "pdf_uri": report.pdf_uri if report else None,
            "xlsx_uri": report.xlsx_uri if report else None,
            "docx_uri": report.docx_uri if report else None,
        } if report else None,
        "instructions": "Review and approve or reject the quality report.",
    }


@router.post("/3/{job_id}")
async def submit_gate3(
    job_id: str,
    req: Gate3Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("approver", "admin")),
):
    """Submit Gate 3 approval decision."""
    decision = {
        "decision": req.decision,
        "approved_by": user.get("sub"),
        "comments": req.comments,
    }
    await _resume_gate(job_id, "GATE3", decision)
    return {"job_id": job_id, "gate": "GATE3", "decision": req.decision}


# ── Helper ────────────────────────────────────────────────────────────────────

async def _resume_gate(job_id: str, gate: str, decision: dict) -> None:
    """Resume the LangGraph workflow from a human gate."""
    from app.workflow.graph import get_compiled_graph
    from app.workflow.gates import resume_gate
    from app.api.jobs import _graph_runs

    thread_id = f"thread-{job_id}"
    app = get_compiled_graph()

    try:
        result = await resume_gate(app, thread_id, gate, decision)
        _graph_runs[thread_id] = {"status": "resumed", "state": result}
    except Exception as e:
        from app.core.logging import get_logger
        get_logger(__name__).error('"gate_resume_error":"%s","gate":"%s"', str(e), gate)
        # Store decision for manual resume
        _graph_runs[thread_id] = {
            "status": "gate_pending",
            "pending_gate": gate,
            "pending_decision": decision,
        }
