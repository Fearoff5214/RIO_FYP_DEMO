"""Simulated camera inputs served from the repo's samples/ folder."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.core.config import get_config
from app.core.security import get_current_user

router = APIRouter(prefix="/demo", tags=["demo"])
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def _samples():
    folder = get_config().project_root / "samples"
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in _IMAGE_SUFFIXES)


@router.get("/samples")
async def list_samples(user: dict = Depends(get_current_user)):
    return [{"name": p.name, "has_defect": p.name.startswith("defect")} for p in _samples()]


@router.get("/samples/{name}")
async def get_sample(name: str, user: dict = Depends(get_current_user)):
    match = next((p for p in _samples() if p.name == name), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return FileResponse(match)
