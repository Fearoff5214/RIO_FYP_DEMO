"""Parts master API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_role
from app.db.session import get_db

router = APIRouter(prefix="/parts", tags=["parts"])


class PartRequest(BaseModel):
    part_number: str
    part_name: str
    drawing_rev: str
    drawing_uri: str
    material: str | None = None
    process: str | None = None
    tolerances: dict | None = None
    camera_recipe: dict | None = None
    calibration: dict | None = None


@router.get("")
async def list_parts(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all parts."""
    from sqlalchemy import select
    from app.db.models import PartMaster

    result = await db.execute(select(PartMaster))
    parts = result.scalars().all()
    return [
        {
            "part_number": p.part_number,
            "part_name": p.part_name,
            "drawing_rev": p.drawing_rev,
            "material": p.material,
            "process": p.process,
        }
        for p in parts
    ]


@router.post("", status_code=201)
async def create_part(
    req: PartRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Create or update a part master."""
    from app.db.models import PartMaster

    part = PartMaster(
        part_number=req.part_number,
        part_name=req.part_name,
        drawing_rev=req.drawing_rev,
        drawing_uri=req.drawing_uri,
        material=req.material,
        process=req.process,
        tolerances=req.tolerances,
        camera_recipe=req.camera_recipe,
        calibration=req.calibration,
    )
    db.add(part)
    await db.commit()
    return {"part_number": req.part_number}


@router.get("/{part_number}")
async def get_part(
    part_number: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get part master details."""
    from sqlalchemy import select
    from app.db.models import PartMaster

    result = await db.execute(select(PartMaster).where(PartMaster.part_number == part_number))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    return {
        "part_number": part.part_number,
        "part_name": part.part_name,
        "drawing_rev": part.drawing_rev,
        "drawing_uri": part.drawing_uri,
        "material": part.material,
        "process": part.process,
        "tolerances": part.tolerances,
        "camera_recipe": part.camera_recipe,
        "calibration": part.calibration,
    }
