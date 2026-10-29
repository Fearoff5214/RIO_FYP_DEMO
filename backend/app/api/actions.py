"""Corrective Actions API."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_role
from app.db.session import get_db

router = APIRouter(prefix="/actions", tags=["actions"])


class ActionUpdateRequest(BaseModel):
    status: str | None = None
    effective: bool | None = None
    evidence_uri: str | None = None
    owner: str | None = None
    due_date: str | None = None


@router.get("")
async def list_actions(
    job_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List corrective actions, optionally filtered by job."""
    from sqlalchemy import select
    from app.db.models import CorrectiveAction

    stmt = select(CorrectiveAction).order_by(CorrectiveAction.created_at.desc())
    if job_id:
        stmt = stmt.where(CorrectiveAction.job_id == job_id)

    result = await db.execute(stmt)
    actions = result.scalars().all()

    return [
        {
            "action_id": a.action_id,
            "job_id": a.job_id,
            "description": a.description,
            "owner": a.owner,
            "due_date": a.due_date,
            "status": a.status,
            "effective": a.effective,
            "evidence_uri": a.evidence_uri,
            "created_at": a.created_at.isoformat(),
        }
        for a in actions
    ]


@router.patch("/{action_id}")
async def update_action(
    action_id: str,
    req: ActionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("engineer", "admin")),
):
    """Update action status, effectiveness, evidence."""
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.db.models import CorrectiveAction

    result = await db.execute(select(CorrectiveAction).where(CorrectiveAction.action_id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    if req.status is not None:
        action.status = req.status
    if req.effective is not None:
        action.effective = req.effective
        # L9: if not effective, reopen
        if not req.effective:
            action.status = "REOPENED"
    if req.evidence_uri is not None:
        action.evidence_uri = req.evidence_uri
    if req.owner is not None:
        action.owner = req.owner
    if req.due_date is not None:
        action.due_date = req.due_date

    db.add(action)
    await db.commit()
    return {"action_id": action_id, "status": action.status, "effective": action.effective}
