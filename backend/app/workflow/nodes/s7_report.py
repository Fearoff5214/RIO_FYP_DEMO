"""Stage 7 — Report Generation & Human Gate 3 nodes."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.logging import get_logger
from app.workflow.state import InspectionState

logger = get_logger(__name__)


async def compose_report(state: InspectionState) -> dict:
    """Compose report data model (works for both OK and NG parts)."""
    job_id = state.get("job_id", "")
    part_master = state.get("part_master", {}) or {}
    fast_path = state.get("fast_path", False)
    measurements = state.get("measurements", []) or []
    defects = state.get("defects", []) or []
    final_rca = state.get("final_rca", {}) or {}
    dimensional_status = state.get("dimensional_status", "PASS")
    gate1 = state.get("gate1", {}) or {}
    gate2 = state.get("gate2", {}) or {}

    report = {
        "job_id": job_id,
        "report_type": "OK" if fast_path else "NG",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "part": {
            "part_number": part_master.get("part_number", ""),
            "part_name": part_master.get("part_name", ""),
            "drawing_rev": part_master.get("drawing_rev", ""),
            "material": part_master.get("material", ""),
            "process": part_master.get("process", ""),
        },
        "inspector": "System AI + Human",
        "inspection_summary": {
            "dimensional": dimensional_status,
            "defect_detection": "PASS" if fast_path else "FAIL",
        },
        "measurements": measurements,
        "defects": defects,
        "root_cause": final_rca if not fast_path else None,
        "flags": state.get("flags", []),
        "gate1_reviewer": gate1.get("reviewer_id"),
        "gate2_reviewer": gate2.get("reviewer_id") if not fast_path else None,
        "version": 1,
    }

    return {"report": report}


async def draft_report(state: InspectionState) -> dict:
    """Validate report completeness; set report_complete."""
    report = state.get("report", {}) or {}
    fast_path = state.get("fast_path", False)

    required_fields = ["job_id", "part", "inspection_summary", "generated_at"]
    if not fast_path:
        required_fields += ["defects", "root_cause"]

    missing = [f for f in required_fields if not report.get(f)]
    complete = len(missing) == 0

    if not complete:
        logger.warning('"node":"draft_report","missing":%s', missing)

    return {"report_complete": complete, "report": {**report, "missing_fields": missing}}


async def render_files(state: InspectionState) -> dict:
    """Render PDF, Excel, Word report files."""
    from app.reports.compose import render_report

    report = state.get("report", {}) or {}
    job_id = state.get("job_id", "")
    logger.info('"node":"render_files","job_id":"%s"', job_id)

    uris = await render_report(report)
    return {"report_uris": uris, "status": "AWAIT_GATE3"}


async def gate3_approver(state: InspectionState) -> dict:
    """Human Gate 3 — interrupt for approver sign-off."""
    from langgraph.types import interrupt

    job_id = state.get("job_id", "")
    report_uris = state.get("report_uris", {}) or {}
    report = state.get("report", {}) or {}

    logger.info('"node":"gate3_approver","job_id":"%s"', job_id)

    payload = {
        "gate": "GATE3",
        "job_id": job_id,
        "report_type": report.get("report_type", "NG"),
        "report_uris": report_uris,
        "message": "Please review the report and approve or reject.",
    }

    decision = interrupt(payload)
    return {"gate3": decision, "status": "GATE3_DECIDED"}


async def esign_archive(state: InspectionState, *, db=None) -> dict:
    """Apply e-signature, archive report, notify systems."""
    from app.reports.esign import apply_esignature

    report = state.get("report", {}) or {}
    report_uris = state.get("report_uris", {}) or {}
    gate3 = state.get("gate3", {}) or {}
    job_id = state.get("job_id", "")

    signed_uri, sig_uri = await apply_esignature(
        pdf_uri=report_uris.get("pdf", ""),
        approver=gate3.get("approved_by", ""),
        job_id=job_id,
    )

    if db is not None:
        from app.db.models import Report, GateDecision

        rpt = Report(
            job_id=job_id,
            version=report.get("version", 1),
            status="APPROVED",
            pdf_uri=signed_uri or report_uris.get("pdf"),
            xlsx_uri=report_uris.get("xlsx"),
            docx_uri=report_uris.get("docx"),
            approved_by=gate3.get("approved_by"),
            approved_at=datetime.now(timezone.utc),
            signature_uri=sig_uri,
        )
        db.add(rpt)

        gd = GateDecision(
            job_id=job_id,
            gate="GATE3",
            reviewer_id=gate3.get("approved_by"),
            decision="approve",
            reason_code=None,
            comments=gate3.get("comments"),
            payload=gate3,
            decided_at=datetime.now(timezone.utc),
        )
        db.add(gd)
        await db.commit()

    return {
        "report_uris": {**report_uris, "pdf_signed": signed_uri},
        "gate3": {**gate3, "signature_uri": sig_uri},
        "status": "OUTPUT",
    }


async def notify_systems(state: InspectionState) -> dict:
    """Send notifications to MES/QMS/ERP/email."""
    from app.notifications.dispatcher import dispatch_all

    await dispatch_all(state)
    return {}


async def escalate_admin(state: InspectionState) -> dict:
    """L7 exhausted — escalate to admin."""
    flags = list(state.get("flags", []) or [])
    if "report_escalated" not in flags:
        flags.append("report_escalated")
    return {"flags": flags, "status": "ON_HOLD", "error": "Report generation failed; escalated to admin"}
