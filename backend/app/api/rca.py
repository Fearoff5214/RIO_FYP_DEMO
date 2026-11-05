"""Standalone root cause analysis API (AI analysis of a list of defects + document download)."""
from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.core.security import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/rca", tags=["rca"])

_MAX_FRAME_BYTES = 12 * 1024 * 1024
_MAX_CLOUD_BYTES = 150 * 1024 * 1024
EVIDENCE_DIR = Path("tmp/evidence")


class DefectIn(BaseModel):
    defect_type: str
    severity: str | None = None
    confidence: float = 0.8
    size_mm2: float | None = None
    note: str | None = None
    bbox: dict | None = None                    # pixel box and outline, used to mark the defect on the evidence picture
    polygon: list[list[float]] | None = None


class AnalyzeRequest(BaseModel):
    part_number: str = "MS-4505-001"
    part_name: str = "Sheet Metal Bracket"
    material: str = "SPCC Steel"
    process: str = "bending"
    defects: list[DefectIn] = Field(default=[], max_length=20)     # empty = good part: a "no defect" report
    measurements: list[dict] = []
    evidence_image: str | None = None            # base64 JPEG/PNG of the inspected part, embedded in the report


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


async def _finish(rca_id: str, state: dict, db: AsyncSession) -> dict:
    """Run the root cause analysis (skipped for a good part), write the documents, shape the response."""
    from app.reports.rca_document import render_rca_documents
    from app.workflow.rca_pipeline import build_report, run_rca

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
        "status": report["verdict"],
        "model": model,
        "ai_used": model.startswith("gemini:"),
        "flags": state.get("flags", []),
        "output_valid": state.get("output_valid"),
        "defects": report["defects"],
        "measurements": report["measurements"],
        "root_cause": report["root_cause"],
        "top3": top3,
        "evidence": (report["rca"] or {}).get("evidence", []),
        "image_url": f"/api/v1/rca/{rca_id}/image" if state.get("evidence_images") else None,
        "documents": {fmt: f"/api/v1/rca/{rca_id}/download?fmt={fmt}" for fmt in docs},
    }


def _decode_frame(b64: str) -> np.ndarray:
    try:
        raw = base64.b64decode(b64.split(",")[-1])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="evidence_image is not valid base64.") from exc
    if not raw or len(raw) > _MAX_FRAME_BYTES:
        raise HTTPException(status_code=422, detail="evidence_image is empty or larger than 12 MB.")
    frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=422, detail="evidence_image must be a JPEG or PNG image.")
    return frame


@router.post("/analyze")
async def analyze(
    req: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Analyse defects: retrieve evidence, ask the LLM for the top 3 causes, write the RCA document.
    With no defects it writes a "no defect found" report instead. The picture of the part goes in the document."""
    from app.reports.evidence import render_frame_evidence

    rca_id = uuid.uuid4().hex
    defects = [d.model_dump(exclude_none=True) for d in req.defects]
    state = {
        "job_id": f"rca_{rca_id}",
        "part_master": {"part_number": req.part_number, "part_name": req.part_name, "material": req.material, "process": req.process},
        "defects": defects,
        "measurements": req.measurements,
    }
    if req.evidence_image:
        frame = _decode_frame(req.evidence_image)
        picture = await run_in_threadpool(render_frame_evidence, frame, defects, EVIDENCE_DIR / f"{rca_id}.png")
        state["evidence_images"] = [{"path": str(picture), "caption": (
            f"Part with {len(defects)} defect(s) marked" if defects else "Good part: no defect found")}]
    return await _finish(rca_id, state, db)


@router.post("/pointcloud")
async def analyze_pointcloud(
    scan: UploadFile = File(...),
    part_number: str = Form("MS-4505-001"),
    part_name: str = Form("Sheet Metal Bracket"),
    material: str = Form("SPCC Steel"),
    process: str = Form("bending"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Inspect a 3D point-cloud scan of the bracket (PLY / ASCII PCD / XYZ / NPY, in mm). Defects found go
    through the root cause analysis; a clean scan gets a "no defect found" report. Either way the report
    carries a deviation heat-map picture of the scanned part."""
    from app.cv.pointcloud_inspector import PointCloudError, inspect_pointcloud, load_point_cloud
    from app.reports.evidence import render_pointcloud_evidence

    data = await scan.read(_MAX_CLOUD_BYTES + 1)
    if not data or len(data) > _MAX_CLOUD_BYTES:
        raise HTTPException(status_code=413, detail="Point cloud file is empty or larger than 150 MB.")
    rca_id = uuid.uuid4().hex

    def work():
        result = inspect_pointcloud(load_point_cloud(data, scan.filename or ""))
        return result, render_pointcloud_evidence(result, EVIDENCE_DIR / f"{rca_id}.png", part_label=part_number)

    try:
        result, picture = await run_in_threadpool(work)
    except PointCloudError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    defects = result["defects"]
    state = {
        "job_id": f"rca_{rca_id}",
        "part_master": {"part_number": part_number, "part_name": part_name, "material": material, "process": process},
        "defects": defects,
        "measurements": result["measurements"],
        "evidence_images": [{"path": str(picture), "caption": (
            f"Point-cloud scan, deviation heat map: {len(defects)} defect(s) circled" if defects
            else "Point-cloud scan of the good part: no defect found")}],
    }
    response = await _finish(rca_id, state, db)
    response["scan"] = {"points": int(len(result["points"])), "spacing_mm": round(result["spacing_mm"], 3)}
    return response


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


@router.get("/{rca_id}/image")
async def evidence_image(rca_id: str, user: dict = Depends(get_current_user)):
    """The picture of the part that is embedded in the report."""
    from app.reports.rca_document import REPORTS_DIR

    if not re.fullmatch(r"[0-9a-f]{32}", rca_id):
        raise HTTPException(status_code=400, detail="Invalid id")
    path = REPORTS_DIR / f"rca_{rca_id}_evidence1.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path=str(path), media_type="image/png")
