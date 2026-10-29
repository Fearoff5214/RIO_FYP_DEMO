"""Jobs API — create, list, get, trigger."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/jobs", tags=["jobs"])

# In-memory graph runs (thread_id → state) — in production use Postgres checkpointer
_graph_runs: dict[str, Any] = {}


class CreateJobRequest(BaseModel):
    part_number: str
    image_uris: list[str] = []
    trigger_source: str = "api"


class JobResponse(BaseModel):
    job_id: str
    part_number: str | None
    status: str
    current_stage: int | None
    thread_id: str | None
    created_at: str


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    req: CreateJobRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new inspection job and start the workflow."""
    from app.workflow.graph import get_compiled_graph
    from app.cv.camera.upload import UploadCamera
    from app.db.models import InspectionJob

    job_id = str(uuid.uuid4())
    thread_id = f"thread-{job_id}"

    # Set upload URIs if provided
    if req.image_uris:
        UploadCamera.set_pending(req.image_uris)

    # Persist job
    job = InspectionJob(
        job_id=job_id,
        part_number=req.part_number,
        status="CREATED",
        current_stage=1,
        thread_id=thread_id,
        loop_counters={},
        flags=[],
    )
    db.add(job)
    await db.commit()

    # Start workflow in background
    initial_state = {
        "job_id": job_id,
        "part_number": req.part_number,
        "thread_id": thread_id,
        "loops": {},
        "flags": [],
        "status": "CREATED",
    }

    background_tasks.add_task(
        _run_workflow,
        job_id=job_id,
        thread_id=thread_id,
        initial_state=initial_state,
    )

    return JobResponse(
        job_id=job_id,
        part_number=req.part_number,
        status="CREATED",
        current_stage=1,
        thread_id=thread_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


async def _run_workflow(job_id: str, thread_id: str, initial_state: dict) -> None:
    """Run the LangGraph workflow asynchronously."""
    from app.workflow.graph import get_compiled_graph
    from app.core.logging import get_logger
    logger = get_logger(__name__)

    try:
        app = get_compiled_graph()
        config = {"configurable": {"thread_id": thread_id}}
        _graph_runs[thread_id] = {"status": "running", "state": initial_state}

        result = await app.ainvoke(initial_state, config=config)
        _graph_runs[thread_id] = {"status": "paused_or_done", "state": result}
        logger.info('"workflow":"completed","job_id":"%s"', job_id)

    except Exception as e:
        logger.error('"workflow":"error","job_id":"%s","error":"%s"', job_id, str(e))
        _graph_runs[thread_id] = {"status": "error", "error": str(e)}


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all inspection jobs."""
    from sqlalchemy import select
    from app.db.models import InspectionJob

    result = await db.execute(select(InspectionJob).order_by(InspectionJob.created_at.desc()).limit(100))
    jobs = result.scalars().all()

    return [
        JobResponse(
            job_id=j.job_id,
            part_number=j.part_number,
            status=j.status,
            current_stage=j.current_stage,
            thread_id=j.thread_id,
            created_at=j.created_at.isoformat(),
        )
        for j in jobs
    ]


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get job detail including state, timeline, measurements, defects."""
    from sqlalchemy import select
    from app.db.models import InspectionJob, DimensionResult, Defect, GateDecision

    result = await db.execute(select(InspectionJob).where(InspectionJob.job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    dim_result = await db.execute(select(DimensionResult).where(DimensionResult.job_id == job_id))
    dims = dim_result.scalars().all()

    defect_result = await db.execute(select(Defect).where(Defect.job_id == job_id))
    defects = defect_result.scalars().all()

    gate_result = await db.execute(select(GateDecision).where(GateDecision.job_id == job_id))
    gates = gate_result.scalars().all()

    # Get current workflow state
    thread_run = _graph_runs.get(job.thread_id, {})

    return {
        "job_id": job.job_id,
        "part_number": job.part_number,
        "status": job.status,
        "current_stage": job.current_stage,
        "dimensional_status": job.dimensional_status,
        "defect_found": job.defect_found,
        "final_decision": job.final_decision,
        "loop_counters": job.loop_counters,
        "flags": job.flags,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "measurements": [
            {
                "feature_id": d.feature_id,
                "nominal": d.nominal,
                "measured": d.measured,
                "deviation": d.deviation,
                "within_tolerance": d.within_tolerance,
            }
            for d in dims
        ],
        "defects": [
            {
                "defect_id": d.defect_id,
                "defect_type": d.defect_type,
                "severity": d.severity,
                "confidence": d.confidence,
                "size_mm2": d.size_mm2,
            }
            for d in defects
        ],
        "gate_decisions": [
            {
                "gate": g.gate,
                "decision": g.decision,
                "reviewer_id": g.reviewer_id,
                "decided_at": g.decided_at.isoformat() if g.decided_at else None,
            }
            for g in gates
        ],
        "workflow_status": thread_run.get("status"),
    }


@router.get("/{job_id}/events")
async def job_events(job_id: str, user: dict = Depends(get_current_user)):
    """SSE stream of job status events."""
    from app.db.models import InspectionJob

    async def event_stream():
        import json
        thread_id = f"thread-{job_id}"
        for _ in range(60):  # max 60 seconds
            run = _graph_runs.get(thread_id, {})
            state = run.get("state", {})
            event_data = {
                "job_id": job_id,
                "status": state.get("status", "unknown"),
                "stage": state.get("current_stage"),
                "workflow": run.get("status", "unknown"),
            }
            yield f"data: {json.dumps(event_data)}\n\n"
            if run.get("status") in ("paused_or_done", "error"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{job_id}/rescan")
async def rescan_job(
    job_id: str,
    part_number: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """L1 operator rescan — provide/correct the part number."""
    from sqlalchemy import update
    from app.db.models import InspectionJob

    await db.execute(
        update(InspectionJob)
        .where(InspectionJob.job_id == job_id)
        .values(part_number=part_number, updated_at=datetime.now(timezone.utc))
    )
    await db.commit()

    thread_id = f"thread-{job_id}"
    run = _graph_runs.get(thread_id, {})
    state = run.get("state", {})
    state["part_number"] = part_number

    return {"job_id": job_id, "part_number": part_number, "status": "rescanned"}
