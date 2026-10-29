"""Dashboard KPIs API."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kpis")
async def get_kpis(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Return key performance indicators for the dashboard."""
    from sqlalchemy import select, func
    from app.db.models import InspectionJob, Defect

    # Total jobs
    total_result = await db.execute(select(func.count()).select_from(InspectionJob))
    total = total_result.scalar_one() or 0

    # Passed (no defect found)
    pass_result = await db.execute(
        select(func.count()).select_from(InspectionJob).where(InspectionJob.defect_found == False)
    )
    passed = pass_result.scalar_one() or 0

    # Defect type distribution
    defect_result = await db.execute(
        select(Defect.defect_type, func.count()).group_by(Defect.defect_type)
    )
    defect_dist = {row[0]: row[1] for row in defect_result.all()}

    # Gate backlog
    backlog_result = await db.execute(
        select(InspectionJob.status, func.count()).group_by(InspectionJob.status)
    )
    status_dist = {row[0]: row[1] for row in backlog_result.all()}

    pass_rate = round(passed / total, 3) if total > 0 else 0.0
    gate_backlog = sum(
        v for k, v in status_dist.items()
        if k.startswith("AWAIT_")
    )

    return {
        "total_jobs": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": pass_rate,
        "defect_distribution": defect_dist,
        "status_distribution": status_dist,
        "gate_backlog": gate_backlog,
    }
