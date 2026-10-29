"""Parts master API."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.core.security import get_current_user, require_role
from app.db.session import get_db

router = APIRouter(prefix="/parts", tags=["parts"])
_verified_captures: dict[str, dict] = {}
_MAX_REFERENCE_BYTES = 12 * 1024 * 1024
_MAX_CAPTURE_BYTES = 12 * 1024 * 1024


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


@router.get("/{part_number}/references")
async def get_part_references(
    part_number: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Report which raster comparison references are configured for this part."""
    from sqlalchemy import select

    from app.db.models import PartMaster

    result = await db.execute(select(PartMaster).where(PartMaster.part_number == part_number))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    calibration = part.calibration or {}
    cad_uri = calibration.get("cad_image_uri")
    image_uri = calibration.get("reference_image_uri")
    return {
        "part_number": part.part_number,
        "part_name": part.part_name,
        "drawing_rev": part.drawing_rev,
        "configured": bool(cad_uri and image_uri and Path(cad_uri).is_file() and Path(image_uri).is_file()),
        "cad_url": f"/api/v1/parts/{part_number}/references/cad",
        "reference_image_url": f"/api/v1/parts/{part_number}/references/image",
        "score_threshold": _verification_threshold(),
    }


@router.get("/{part_number}/references/{kind}")
async def get_part_reference_file(
    part_number: str,
    kind: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Serve the registered raster CAD or reference image for one part."""
    from sqlalchemy import select

    from app.db.models import PartMaster

    if kind not in {"cad", "image"}:
        raise HTTPException(status_code=404, detail="Reference type not found")
    result = await db.execute(select(PartMaster).where(PartMaster.part_number == part_number))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    calibration = part.calibration or {}
    key = "cad_image_uri" if kind == "cad" else "reference_image_uri"
    uri = calibration.get(key)
    path = Path(uri) if uri else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail=f"{kind} reference image is not configured")
    return FileResponse(path, media_type="image/png")


@router.put("/{part_number}/references", status_code=200)
async def upload_part_references(
    part_number: str,
    cad_image: UploadFile = File(...),
    reference_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Store the CAD raster and physical reference image against their part master."""
    from sqlalchemy import select

    from app.db.models import PartMaster

    result = await db.execute(select(PartMaster).where(PartMaster.part_number == part_number))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    cad_bytes = await _read_image_upload(cad_image, "CAD reference")
    reference_bytes = await _read_image_upload(reference_image, "Part reference")
    folder_name = re.sub(r"[^A-Za-z0-9._-]", "_", part_number)
    reference_dir = get_config().project_root / "data" / "part_references" / folder_name
    reference_dir.mkdir(parents=True, exist_ok=True)
    cad_path = reference_dir / "cad_reference.png"
    reference_path = reference_dir / "part_reference.png"
    cad_path.write_bytes(cad_bytes)
    reference_path.write_bytes(reference_bytes)

    calibration = dict(part.calibration or {})
    calibration["cad_image_uri"] = str(cad_path)
    calibration["reference_image_uri"] = str(reference_path)
    part.calibration = calibration
    await db.commit()
    return {
        "part_number": part_number,
        "configured": True,
        "cad_url": f"/api/v1/parts/{part_number}/references/cad",
        "reference_image_url": f"/api/v1/parts/{part_number}/references/image",
    }


@router.post("/{part_number}/verify")
async def verify_part_capture(
    part_number: str,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Compare a captured image only with this part number's registered CAD raster."""
    from sqlalchemy import select

    from app.cv.part_verification import compare_part_images
    from app.db.models import PartMaster

    result = await db.execute(select(PartMaster).where(PartMaster.part_number == part_number))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    calibration = part.calibration or {}
    cad_uri = calibration.get("cad_image_uri")
    reference_uri = calibration.get("reference_image_uri")
    if not cad_uri or not reference_uri:
        raise HTTPException(
            status_code=409,
            detail="This part has no registered CAD and reference images. Configure both before inspection.",
        )
    cad_path = Path(cad_uri)
    reference_path = Path(reference_uri)
    if not cad_path.is_file() or not reference_path.is_file():
        raise HTTPException(
            status_code=409,
            detail="This part has no registered CAD and reference images. Configure both before inspection.",
        )

    image_bytes = await _read_image_upload(image, "Captured image", _MAX_CAPTURE_BYTES)
    captured = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    cad = cv2.imread(str(cad_path))
    if captured is None or cad is None:
        raise HTTPException(status_code=422, detail="Could not decode the captured or CAD image.")
    threshold = _verification_threshold()
    comparison = compare_part_images(captured, cad, threshold)

    verification_id = str(uuid.uuid4())
    capture_dir = get_config().project_root / "tmp" / "part_verification"
    capture_dir.mkdir(parents=True, exist_ok=True)
    capture_path = capture_dir / f"{verification_id}.jpg"
    if not cv2.imwrite(str(capture_path), captured):
        raise HTTPException(status_code=500, detail="Could not save the verified capture.")

    _verified_captures[verification_id] = {
        "part_number": part_number,
        "status": comparison["status"],
        "image_uri": str(capture_path),
    }
    return {
        **comparison,
        "verification_id": verification_id,
        "part_number": part_number,
        "part_name": part.part_name,
        "drawing_rev": part.drawing_rev,
        "cad_url": f"/api/v1/parts/{part_number}/references/cad",
        "reference_image_url": f"/api/v1/parts/{part_number}/references/image",
    }


async def _read_image_upload(
    upload: UploadFile,
    label: str,
    max_bytes: int = _MAX_REFERENCE_BYTES,
) -> bytes:
    content = await upload.read(max_bytes + 1)
    if not content:
        raise HTTPException(status_code=422, detail=f"{label} file is empty.")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{label} file exceeds the 12 MB limit.")
    decoded = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise HTTPException(status_code=415, detail=f"{label} must be a valid raster image.")
    encoded, png = cv2.imencode(".png", decoded)
    if not encoded:
        raise HTTPException(status_code=422, detail=f"{label} image could not be processed.")
    return png.tobytes()


def _verification_threshold() -> float:
    configured = get_config().get("part_verification", "score_threshold")
    threshold = float(0.55 if configured is None else configured)
    if not 0 < threshold <= 1:
        raise ValueError("part_verification.score_threshold must be greater than 0 and at most 1.")
    return threshold
