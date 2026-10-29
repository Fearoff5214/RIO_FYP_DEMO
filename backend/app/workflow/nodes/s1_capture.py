"""
Stage 1 — Trigger, Context & Image Capture nodes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.config import get_config
from app.core.logging import get_logger
from app.workflow.state import InspectionState

logger = get_logger(__name__)


async def read_part_id(state: InspectionState) -> dict:
    """Parse / validate the part number coming from trigger payload."""
    logger.info('"node":"read_part_id","job_id":"%s"', state.get("job_id", ""))
    part_number = state.get("part_number", "").strip().upper()
    return {"part_number": part_number, "status": "READING_PART"}


async def load_part_master(state: InspectionState, *, db=None) -> dict:
    """
    Load part master from database.
    Falls back to a synthetic part when no DB row exists (mock mode).
    """
    from app.cv.drawing.synthetic import generate_synthetic_part_master

    part_number = state.get("part_number", "")
    logger.info('"node":"load_part_master","part":"%s"', part_number)

    if db is not None:
        from sqlalchemy import select
        from app.db.models import PartMaster

        result = await db.execute(select(PartMaster).where(PartMaster.part_number == part_number))
        row = result.scalar_one_or_none()
        if row:
            return {
                "part_master": {
                    "part_number": row.part_number,
                    "part_name": row.part_name,
                    "drawing_rev": row.drawing_rev,
                    "drawing_uri": row.drawing_uri,
                    "material": row.material,
                    "process": row.process,
                    "tolerances": row.tolerances or {},
                    "camera_recipe": row.camera_recipe or {},
                    "calibration": row.calibration or {},
                },
                "status": "PART_FOUND",
            }

    # Not found — try synthetic (mock)
    cfg = get_config()
    if cfg.is_mock or part_number in ("MS-4505-001", ""):
        master = generate_synthetic_part_master(part_number or "MS-4505-001")
        return {"part_master": master, "status": "PART_FOUND"}

    return {"part_master": None, "status": "PART_NOT_FOUND"}


async def create_job(state: InspectionState, *, db=None) -> dict:
    """Persist the inspection_job row and first audit entry."""
    job_id = state.get("job_id") or str(uuid.uuid4())
    thread_id = f"thread-{job_id}"
    logger.info('"node":"create_job","job_id":"%s"', job_id)

    if db is not None:
        from app.db.models import InspectionJob
        from app.db.audit import write_audit

        job = InspectionJob(
            job_id=job_id,
            part_number=state.get("part_number"),
            status="CREATED",
            current_stage=1,
            thread_id=thread_id,
            loop_counters=state.get("loops", {}),
            flags=state.get("flags", []),
        )
        db.add(job)
        await db.commit()
        await write_audit(db, "job_created", job_id=job_id, node="create_job", payload={"part_number": state.get("part_number")})

    return {"job_id": job_id, "thread_id": thread_id, "status": "CREATED", "loops": {}, "flags": []}


async def set_camera_recipe(state: InspectionState) -> dict:
    """Determine camera recipe (lighting, angles, exposure) from part master."""
    part_master = state.get("part_master", {}) or {}
    recipe = part_master.get("camera_recipe") or {
        "angles": ["top", "side_left", "side_right"],
        "exposure": 50,
        "lighting": "diffuse",
        "resolution": "1920x1080",
    }

    # Auto-adjust on L2 retry: reduce exposure if glare likely
    loops = state.get("loops", {}) or {}
    if loops.get("L2", 0) > 0:
        recipe = dict(recipe)
        recipe["exposure"] = max(10, recipe.get("exposure", 50) - 15)
        logger.info('"node":"set_camera_recipe","adjusted_exposure":%d', recipe["exposure"])

    return {"camera_recipe": recipe, "status": "CAPTURING"}


async def capture_images(state: InspectionState) -> dict:
    """
    Capture images using the configured camera adapter.
    In mock mode returns synthetic images or sample folder images.
    """
    from app.cv.camera.factory import get_camera

    cfg = get_config()
    recipe = state.get("camera_recipe", {}) or {}
    job_id = state.get("job_id", "unknown")

    logger.info('"node":"capture_images","job_id":"%s"', job_id)

    camera = get_camera()
    images = await camera.capture(recipe)

    return {"images": images, "status": "PREPROCESSING"}


async def preprocess_store(state: InspectionState, *, db=None) -> dict:
    """
    Preprocess images: undistort, px→mm, normalize illumination.
    Compute quality scores. Store raw + processed assets.
    """
    from app.cv.preprocess import preprocess_images, score_quality

    cfg = get_config()
    images = state.get("images", []) or []
    part_master = state.get("part_master", {}) or {}
    calibration = part_master.get("calibration", {}) or {}
    job_id = state.get("job_id", "unknown")

    logger.info('"node":"preprocess_store","job_id":"%s","n_images":%d', job_id, len(images))

    processed = await preprocess_images(images, calibration)
    quality_ok, quality_scores = score_quality(processed, cfg)

    # Persist image assets
    if db is not None:
        from app.db.models import ImageAsset
        for img in processed:
            asset = ImageAsset(
                job_id=job_id,
                kind=img.get("kind", "processed"),
                uri=img.get("uri", ""),
                angle=img.get("angle"),
                quality_score=img.get("quality_score"),
                meta=img.get("meta"),
            )
            db.add(asset)
        await db.commit()

    return {"images": processed, "image_quality_ok": quality_ok, "status": "PREPROCESSED"}


async def job_on_hold(state: InspectionState) -> dict:
    """L1 exhausted — put job on hold."""
    logger.warning('"node":"job_on_hold","job_id":"%s"', state.get("job_id"))
    return {"status": "ON_HOLD", "error": "Part or drawing not found after maximum retries"}


async def operator_alert(state: InspectionState) -> dict:
    """L2 exhausted — send operator alert."""
    logger.warning('"node":"operator_alert","job_id":"%s"', state.get("job_id"))
    return {"status": "ON_HOLD", "error": "Image quality unacceptable after maximum recapture attempts"}
