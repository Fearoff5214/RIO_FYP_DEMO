"""Audit log API."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_role
from app.db.session import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def get_audit(
    job_id: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "auditor")),
):
    """Get audit log entries."""
    from sqlalchemy import select
    from app.db.models import AuditLog

    stmt = select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit)
    if job_id:
        stmt = stmt.where(AuditLog.job_id == job_id)

    result = await db.execute(stmt)
    entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "job_id": e.job_id,
            "actor": e.actor,
            "actor_role": e.actor_role,
            "node": e.node,
            "event": e.event,
            "state_hash": e.state_hash,
            "ts": e.ts.isoformat(),
        }
        for e in entries
    ]
