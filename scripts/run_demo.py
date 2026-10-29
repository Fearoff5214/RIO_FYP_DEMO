"""
Golden demo script — reproduces the infographic scenario end-to-end in mock mode.
Run with: python scripts/run_demo.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import os
os.environ["NOVALISEO_MODE"] = "mock"


async def run_demo() -> None:
    print("=" * 60)
    print("NOVALISEO — Golden Demo (Mock Mode)")
    print("Part: MS-4505-001 — Sheet Metal Bracket")
    print("=" * 60)

    # Setup
    from app.db.session import create_tables
    await create_tables()

    from scripts.seed_demo import seed_if_empty
    await seed_if_empty()

    from scripts.load_kb import load_sample_kb
    await load_sample_kb()

    print("\n[1/8] Starting inspection job...")
    from app.workflow.graph import get_compiled_graph
    from app.workflow.state import InspectionState
    import uuid

    job_id = str(uuid.uuid4())
    thread_id = f"thread-{job_id}"
    config = {"configurable": {"thread_id": thread_id}}

    app = get_compiled_graph()

    initial_state: InspectionState = {
        "job_id": job_id,
        "part_number": "MS-4505-001",
        "thread_id": thread_id,
        "loops": {},
        "flags": [],
        "status": "CREATED",
    }

    print(f"   Job ID: {job_id}")

    # Run until first interrupt (Gate 1)
    print("\n[2/3] Running Stages 1-2 (capture + dimensional)...")
    result = await app.ainvoke(initial_state, config=config)
    _print_state_summary(result, "After Stage 2")

    # Gate 1: engineer confirms
    print("\n[GATE 1] Engineer reviewing dimensional results...")
    print("   Decision: CONFIRM (all within tolerance)")
    from langgraph.types import Command
    result = await app.ainvoke(
        Command(resume={
            "decision": "confirm",
            "reviewer_id": "engineer",
            "reason_code": None,
            "comments": "Measurements verified",
            "overrides": [],
        }),
        config=config,
    )
    _print_state_summary(result, "After Gate 1")

    # The graph continues to Stage 3 (defect detection) and pauses at Label Review
    # (because mock detector returns crack with conf=0.76 < 0.85)
    if _is_paused_at(result, "label_review_gate"):
        print("\n[LABEL REVIEW] Engineer reviewing low-confidence detection...")
        defects = result.get("defects", [])
        print(f"   Defects before review: {[(d.get('defect_type'), d.get('confidence', 0)) for d in defects]}")
        print("   Confirming crack detection (no correction)")
        result = await app.ainvoke(
            Command(resume={
                "corrections": [],
                "reviewer_id": "engineer",
            }),
            config=config,
        )
        _print_state_summary(result, "After Label Review")

    # Gate 2: expert reviews top-3 RCA
    if _is_paused_at(result, "gate2_expert"):
        print("\n[GATE 2] Quality expert reviewing top-3 root causes...")
        top3 = result.get("top3", [])
        if top3:
            for c in top3:
                print(f"   Rank {c.get('rank')}: {c.get('cause')} ({c.get('confidence_cal', 0):.0%})")
        print("   Decision: ACCEPT Rank 1")
        result = await app.ainvoke(
            Command(resume={
                "decision": "accept",
                "selected_rank": 1,
                "edited_cause": None,
                "reason": "Matches production history",
                "corrective": ["Recalibrate press brake", "Verify material lot"],
                "preventive": ["Schedule monthly calibration", "Incoming inspection"],
                "reviewer_id": "expert",
            }),
            config=config,
        )
        _print_state_summary(result, "After Gate 2")

    # Gate 3: approver signs off
    if _is_paused_at(result, "gate3_approver"):
        print("\n[GATE 3] Approver reviewing report...")
        print("   Decision: APPROVE")
        result = await app.ainvoke(
            Command(resume={
                "decision": "approve",
                "approved_by": "approver",
                "comments": "Report verified and approved.",
            }),
            config=config,
        )
        _print_state_summary(result, "After Gate 3")

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print(f"Final status: {result.get('status', 'UNKNOWN')}")

    report_uris = result.get("report_uris", {})
    if report_uris:
        print("\nGenerated report files:")
        for fmt, uri in report_uris.items():
            print(f"  {fmt}: {uri}")

    flags = result.get("flags", [])
    if flags:
        print(f"\nFlags: {flags}")

    print("=" * 60)


def _print_state_summary(state: dict, label: str) -> None:
    print(f"\n   [{label}]")
    print(f"   Status: {state.get('status', 'unknown')}")
    if state.get("dimensional_status"):
        print(f"   Dimensional: {state['dimensional_status']}")
    if state.get("defects"):
        defects = state["defects"]
        print(f"   Defects: {len(defects)} found")
    if state.get("top3"):
        top3 = state["top3"]
        print(f"   Top 3 causes: {[c.get('cause', '')[:30] for c in top3]}")


def _is_paused_at(state: dict, node: str) -> bool:
    """Check if the graph paused at the given node (heuristic)."""
    status = state.get("status", "")
    status_map = {
        "label_review_gate": "AWAIT_LABEL_REVIEW",
        "gate2_expert": "AWAIT_GATE2",
        "gate3_approver": "AWAIT_GATE3",
    }
    return status == status_map.get(node, "")


if __name__ == "__main__":
    asyncio.run(run_demo())
