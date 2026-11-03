"""The full inspection workflow must persist its results (regression: nodes never received a db session)."""
from __future__ import annotations

import uuid

import pytest
from langgraph.types import Command
from sqlalchemy import func, select


@pytest.mark.asyncio
async def test_full_workflow_writes_results_to_the_database(db):
    from app.db import models as m
    from app.db.session import _get_session_factory
    from app.workflow.graph import get_compiled_graph

    job_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": f"thread-{job_id}"}}
    app = get_compiled_graph()

    async def waiting_at(node: str) -> bool:
        return node in ((await app.aget_state(config)).next or ())

    await app.ainvoke({"job_id": job_id, "part_number": "MS-4505-001", "thread_id": f"thread-{job_id}",
                       "loops": {}, "flags": [], "status": "CREATED"}, config=config)
    await app.ainvoke(Command(resume={"decision": "confirm", "reviewer_id": "engineer", "comments": "ok", "overrides": []}), config=config)
    if await waiting_at("label_review_gate"):
        await app.ainvoke(Command(resume={"corrections": [], "reviewer_id": "engineer"}), config=config)
    assert await waiting_at("gate2_expert")
    state = await app.ainvoke(Command(resume={"decision": "accept", "selected_rank": 1, "edited_cause": None, "reason": "ok",
                                              "corrective": ["Fix A"], "preventive": ["Prevent B"], "reviewer_id": "expert"}), config=config)
    assert await waiting_at("gate3_approver")
    state = await app.ainvoke(Command(resume={"decision": "approve", "approved_by": "approver", "comments": "ok"}), config=config)
    assert state["status"] == "CLOSED"

    async with _get_session_factory()() as s:
        async def count(model):
            return (await s.execute(select(func.count()).select_from(model).where(model.job_id == job_id))).scalar_one()

        job = (await s.execute(select(m.InspectionJob).where(m.InspectionJob.job_id == job_id))).scalar_one()
        assert job.status == "CLOSED"
        assert await count(m.Defect) >= 1 and await count(m.DimensionResult) >= 1
        preds = (await s.execute(select(m.RootCausePrediction).where(m.RootCausePrediction.job_id == job_id)
                                 .order_by(m.RootCausePrediction.rank))).scalars().all()
        assert len(preds) == 3 and all(p.rationale and p.corrective_actions for p in preds)     # reason + solution stored
        final = (await s.execute(select(m.FinalRCA).where(m.FinalRCA.job_id == job_id))).scalar_one()
        assert final.cause and final.corrective_actions == ["Fix A"] and final.rationale
        report = (await s.execute(select(m.Report).where(m.Report.job_id == job_id))).scalars().first()
        assert report is not None and report.status == "APPROVED"
        assert report.rca_docx_uri and report.rca_pdf_uri and report.rca_md_uri               # RCA document recorded
        assert await count(m.CorrectiveAction) >= 1 and await count(m.GateDecision) >= 2
