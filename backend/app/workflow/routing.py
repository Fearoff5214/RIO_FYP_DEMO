"""
Conditional edge functions for the LangGraph.
Each function receives InspectionState and returns a node name string.
Loop counters are checked and incremented here before routing.
"""
from __future__ import annotations

from app.core.config import get_config
from app.workflow.state import InspectionState


def _inc(state: InspectionState, loop: str) -> int:
    """Increment loop counter in state (returns new value)."""
    loops = state.get("loops", {}) or {}
    loops[loop] = loops.get(loop, 0) + 1
    state["loops"] = loops  # type: ignore[typeddict-item]
    return loops[loop]


def _get_max(loop: str) -> int:
    cfg = get_config()
    return int(cfg.get("workflow", "retries", loop) or 3)


# ── Stage 1 routing ────────────────────────────────────────────────────────────

def route_part_found(state: InspectionState) -> str:
    """After load_part_master: part found or L1 retry."""
    if state.get("part_master"):
        return "create_job"
    count = _inc(state, "L1")
    if count < _get_max("L1"):
        return "read_part_id"  # retry
    return "job_on_hold"


def route_image_quality(state: InspectionState) -> str:
    """After preprocess_store: quality OK or L2 retry."""
    if state.get("image_quality_ok"):
        return "parse_drawing"
    count = _inc(state, "L2")
    if count < _get_max("L2"):
        return "set_camera_recipe"  # auto-adjust and recapture
    return "operator_alert"


# ── Stage 2 routing ────────────────────────────────────────────────────────────

def route_gate1(state: InspectionState) -> str:
    """After gate1_engineer: confirmed / rejected (L3) / overridden."""
    gate1 = state.get("gate1", {}) or {}
    decision = gate1.get("decision", "confirm")
    if decision in ("confirm", "override"):
        return "lock_result"
    # reject → L3
    count = _inc(state, "L3")
    if count < _get_max("L3"):
        return "measure_mm"
    return "manual_measurement"


# ── Stage 3 routing ────────────────────────────────────────────────────────────

def route_any_defect(state: InspectionState) -> str:
    """After fuse: defect found or fast path."""
    if state.get("defect_found"):
        return "classify_measure"
    return "fast_path_report"  # → Stage 7 OK report


def route_label_review(state: InspectionState) -> str:
    """After classify_measure: all confident or needs label review."""
    min_conf = state.get("min_confidence", 1.0)
    defects = state.get("defects", []) or []
    has_unknown = any(d.get("defect_type") == "unknown_anomaly" for d in defects)
    threshold = get_config().get("detection", "label_review_confidence_threshold") or 0.85
    if min_conf < threshold or has_unknown:
        return "label_review_gate"
    return "save_defects"


# ── Stage 4 routing ────────────────────────────────────────────────────────────

def route_evidence(state: InspectionState) -> str:
    """After rerank: evidence sufficient or L4 retry."""
    if state.get("evidence_sufficient"):
        return "assemble_evidence"
    count = _inc(state, "L4")
    if count < _get_max("L4"):
        return "apply_filters"  # relax filters and retry
    # exhausted: flag and continue
    flags = list(state.get("flags", []) or [])
    if "low_evidence" not in flags:
        flags.append("low_evidence")
    state["flags"] = flags  # type: ignore[typeddict-item]
    return "assemble_evidence"


# ── Stage 5 routing ────────────────────────────────────────────────────────────

def route_output_valid(state: InspectionState) -> str:
    """After format_top3 / calibrate: valid or L5 regenerate."""
    if state.get("output_valid"):
        return "save_ranked"
    count = _inc(state, "L5")
    if count < _get_max("L5"):
        return "llm_reason"
    # exhausted: send flagged low_confidence
    flags = list(state.get("flags", []) or [])
    if "low_confidence" not in flags:
        flags.append("low_confidence")
    state["flags"] = flags  # type: ignore[typeddict-item]
    return "save_ranked"


# ── Stage 6 routing ────────────────────────────────────────────────────────────

def route_gate2(state: InspectionState) -> str:
    """After gate2_expert."""
    gate2 = state.get("gate2", {}) or {}
    decision = gate2.get("decision", "accept")
    if decision in ("accept", "edit"):
        return "finalize_actions"
    # reject_all
    next_action = gate2.get("next", "reinspect")
    if next_action == "reinspect":
        return "set_camera_recipe"
    return "manual_rca"


# ── Stage 7 routing ────────────────────────────────────────────────────────────

def route_report_complete(state: InspectionState) -> str:
    """After draft_report: complete or L7 add missing data."""
    if state.get("report_complete"):
        return "render_files"
    count = _inc(state, "L7")
    if count < _get_max("L7"):
        return "compose_report"
    return "escalate_admin"


def route_gate3(state: InspectionState) -> str:
    """After gate3_approver: approved or L8 redraft."""
    gate3 = state.get("gate3", {}) or {}
    decision = gate3.get("decision", "approve")
    if decision == "approve":
        return "esign_archive"
    # reject → always retry (L8 unlimited)
    return "draft_report"


# ── Stage 8 routing ────────────────────────────────────────────────────────────

def route_action_effective(state: InspectionState) -> str:
    """Placeholder — corrective-action effectiveness checked externally via API."""
    return "close_case"
