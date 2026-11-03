"""Standalone root cause analysis API (AI analysis of a list of defects + document download)."""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.core.security import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/rca", tags=["rca"])


class DefectIn(BaseModel):
    defect_type: str
    severity: str | None = None
    confidence: float = 0.8
    size_mm2: float | None = None
    note: str | None = None


class AnalyzeRequest(BaseModel):
    part_number: str = "MS-4505-001"
    part_name: str = "Sheet Metal Bracket"
    material: str = "SPCC Steel"
    process: str = "bending"
    defects: list[DefectIn] = Field(min_length=1, max_length=20)
    measurements: list[dict] = []


@router.get("/status")
async def rca_status(user: dict = Depends(get_current_user)):
    """Which LLM provider RCA will use (never returns the key)."""
    from app.llm.factory import resolve_provider_name

    cfg = get_config()
    provider = resolve_provider_name(cfg)
    return {
        "provider": provider,
        "model": cfg.settings.gemini_model if provider == "gemini" else None,
        "gemini_key_configured": bool((cfg.settings.gemini_api_key or "").strip()),
        "ai_enabled": provider != "fake",
    }


@router.post("/analyze")
async def analyze(
    req: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Analyse defects: retrieve evidence, ask the LLM for the top 3 causes, write the RCA document."""
    from app.reports.rca_document import render_rca_documents
    from app.workflow.rca_pipeline import build_report, run_rca

    rca_id = uuid.uuid4().hex
    state = {
        "job_id": f"rca_{rca_id}",
        "part_master": {"part_number": req.part_number, "part_name": req.part_name, "material": req.material, "process": req.process},
        "defects": [d.model_dump() for d in req.defects],
        "measurements": req.measurements,
    }
    try:
        state = await run_rca(state, db=db)
    except Exception as exc:                                         # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Root cause analysis failed: {type(exc).__name__}") from exc

    report = build_report(state)
    docs = await render_rca_documents(report, stem=f"rca_{rca_id}")
    top3 = state.get("top3", [])
    model = (top3[0].get("model_version") if top3 else None) or "unknown"
    return {
        "rca_id": rca_id,
        "model": model,
        "ai_used": model.startswith("gemini:"),
        "flags": state.get("flags", []),
        "output_valid": state.get("output_valid"),
        "root_cause": report["root_cause"],
        "top3": top3,
        "evidence": report["rca"]["evidence"],
        "documents": {fmt: f"/api/v1/rca/{rca_id}/download?fmt={fmt}" for fmt in docs},
    }


@router.get("/{rca_id}/download")
async def download(rca_id: str, fmt: str = "docx", user: dict = Depends(get_current_user)):
    from app.reports.rca_document import REPORTS_DIR

    if not re.fullmatch(r"[0-9a-f]{32}", rca_id) or fmt not in ("docx", "pdf", "md"):
        raise HTTPException(status_code=400, detail="Invalid id or format (docx, pdf, md)")
    path = REPORTS_DIR / f"rca_{rca_id}.{fmt}"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    media = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "pdf": "application/pdf", "md": "text/markdown"}[fmt]
    return FileResponse(path=str(path), media_type=media, filename=f"novaliseo_rca.{fmt}")
