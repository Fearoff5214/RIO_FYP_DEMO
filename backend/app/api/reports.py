"""Reports API endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{job_id}")
async def get_report(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get report metadata for a job."""
    from sqlalchemy import select
    from app.db.models import Report

    result = await db.execute(
        select(Report).where(Report.job_id == job_id).order_by(Report.version.desc())
    )
    report = result.scalars().first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "report_id": report.report_id,
        "job_id": report.job_id,
        "version": report.version,
        "status": report.status,
        "pdf_uri": report.pdf_uri,
        "xlsx_uri": report.xlsx_uri,
        "docx_uri": report.docx_uri,
        "rca_docx_uri": report.rca_docx_uri,
        "rca_pdf_uri": report.rca_pdf_uri,
        "rca_md_uri": report.rca_md_uri,
        "approved_by": report.approved_by,
        "approved_at": report.approved_at.isoformat() if report.approved_at else None,
        "created_at": report.created_at.isoformat(),
    }


@router.get("/{job_id}/rca")
async def download_rca(
    job_id: str,
    fmt: str = "docx",
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Download the root cause analysis document (docx, pdf or md) generated for a job."""
    import re

    from app.reports.rca_document import REPORTS_DIR

    if fmt not in ("docx", "pdf", "md") or not re.fullmatch(r"[\w\-]+", job_id):
        raise HTTPException(status_code=400, detail="fmt must be docx, pdf or md")
    from sqlalchemy import select

    from app.db.models import Report

    path = REPORTS_DIR / f"{job_id}_rca.{fmt}"
    row = (await db.execute(select(Report).where(Report.job_id == job_id).order_by(Report.version.desc()))).scalars().first()
    recorded = getattr(row, f"rca_{fmt}_uri", None) if row else None      # the path recorded in the database wins
    if recorded and Path(recorded).exists():
        path = Path(recorded)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No RCA document for this job yet")
    media = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "pdf": "application/pdf", "md": "text/markdown"}[fmt]
    return FileResponse(path=str(path), media_type=media, filename=f"novaliseo_rca_{job_id}.{fmt}")


@router.get("/{job_id}/download")
async def download_report(
    job_id: str,
    fmt: str = "pdf",
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Download report in specified format (pdf, xlsx, docx)."""
    from sqlalchemy import select
    from app.db.models import Report

    result = await db.execute(
        select(Report).where(Report.job_id == job_id).order_by(Report.version.desc())
    )
    report = result.scalars().first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    uri_map = {"pdf": report.pdf_uri, "xlsx": report.xlsx_uri, "docx": report.docx_uri}
    uri = uri_map.get(fmt)

    if not uri:
        raise HTTPException(status_code=404, detail=f"Format {fmt} not available")

    path = Path(uri)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Report file not found at {uri}")

    media_types = {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    return FileResponse(
        path=str(path),
        media_type=media_types.get(fmt, "application/octet-stream"),
        filename=f"novaliseo_report_{job_id}.{fmt}",
    )
