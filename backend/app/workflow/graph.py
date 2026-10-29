"""
LangGraph StateGraph builder for Novaliseo inspection workflow.
Compiles the full 8-stage graph with all conditional edges and loops.
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.workflow.state import InspectionState

# ── Import all nodes ──────────────────────────────────────────────────────────
from app.workflow.nodes.s1_capture import (
    capture_images,
    create_job,
    job_on_hold,
    load_part_master,
    operator_alert,
    preprocess_store,
    read_part_id,
    set_camera_recipe,
)
from app.workflow.nodes.s2_dimensional import (
    compare_drawing,
    detect_features,
    gate1_engineer,
    lock_result,
    manual_measurement,
    measure_mm,
    parse_drawing,
    save_dim,
    set_dim_status,
)
from app.workflow.nodes.s3_defects import (
    anomaly_check,
    classify_measure,
    detect_segment,
    dispatch_detectors,
    fast_path_report,
    fuse,
    label_review_gate,
    save_defects,
)
from app.workflow.nodes.s4_retrieval import (
    apply_filters,
    assemble_evidence,
    build_query,
    embed_query,
    graph_expand,
    hybrid_retrieve,
    rerank,
    set_limits,
)
from app.workflow.nodes.s5_prediction import (
    assemble_context,
    calibrate,
    format_top3,
    llm_reason,
    rank_top3,
    save_ranked,
    score_conf,
)
from app.workflow.nodes.s6_expert_gate import (
    finalize_actions,
    gate2_expert,
    manual_rca,
    mark_rca_final,
    record_feedback,
    save_decision,
)
from app.workflow.nodes.s7_report import (
    compose_report,
    draft_report,
    escalate_admin,
    esign_archive,
    gate3_approver,
    notify_systems,
    render_files,
)
from app.workflow.nodes.s8_output_learning import (
    close_case,
    dispatch_results,
    final_output,
    learning_hub,
    track_actions,
)

# ── Import routing functions ───────────────────────────────────────────────────
from app.workflow.routing import (
    route_action_effective,
    route_any_defect,
    route_evidence,
    route_gate1,
    route_gate2,
    route_gate3,
    route_image_quality,
    route_label_review,
    route_output_valid,
    route_part_found,
    route_report_complete,
)


def build_graph() -> StateGraph:
    """Build and return the compiled inspection workflow graph."""
    g = StateGraph(InspectionState)

    # ── Stage 1 nodes ─────────────────────────────────────────────────────
    g.add_node("read_part_id", read_part_id)
    g.add_node("load_part_master", load_part_master)
    g.add_node("create_job", create_job)
    g.add_node("set_camera_recipe", set_camera_recipe)
    g.add_node("capture_images", capture_images)
    g.add_node("preprocess_store", preprocess_store)
    g.add_node("job_on_hold", job_on_hold)
    g.add_node("operator_alert", operator_alert)

    # ── Stage 2 nodes ─────────────────────────────────────────────────────
    g.add_node("parse_drawing", parse_drawing)
    g.add_node("detect_features", detect_features)
    g.add_node("measure_mm", measure_mm)
    g.add_node("compare_drawing", compare_drawing)
    g.add_node("set_dim_status", set_dim_status)
    g.add_node("gate1_engineer", gate1_engineer)
    g.add_node("lock_result", lock_result)
    g.add_node("save_dim", save_dim)
    g.add_node("manual_measurement", manual_measurement)

    # ── Stage 3 nodes ─────────────────────────────────────────────────────
    g.add_node("dispatch_detectors", dispatch_detectors)
    g.add_node("detect_segment", detect_segment)
    g.add_node("anomaly_check", anomaly_check)
    g.add_node("fuse", fuse)
    g.add_node("classify_measure", classify_measure)
    g.add_node("label_review_gate", label_review_gate)
    g.add_node("save_defects", save_defects)
    g.add_node("fast_path_report", fast_path_report)

    # ── Stage 4 nodes ─────────────────────────────────────────────────────
    g.add_node("build_query", build_query)
    g.add_node("apply_filters", apply_filters)
    g.add_node("embed_query", embed_query)
    g.add_node("graph_expand", graph_expand)
    g.add_node("set_limits", set_limits)
    g.add_node("hybrid_retrieve", hybrid_retrieve)
    g.add_node("rerank", rerank)
    g.add_node("assemble_evidence", assemble_evidence)

    # ── Stage 5 nodes ─────────────────────────────────────────────────────
    g.add_node("assemble_context", assemble_context)
    g.add_node("llm_reason", llm_reason)
    g.add_node("score_conf", score_conf)
    g.add_node("rank_top3", rank_top3)
    g.add_node("calibrate", calibrate)
    g.add_node("format_top3", format_top3)
    g.add_node("save_ranked", save_ranked)

    # ── Stage 6 nodes ─────────────────────────────────────────────────────
    g.add_node("gate2_expert", gate2_expert)
    g.add_node("finalize_actions", finalize_actions)
    g.add_node("save_decision", save_decision)
    g.add_node("record_feedback", record_feedback)
    g.add_node("mark_rca_final", mark_rca_final)
    g.add_node("manual_rca", manual_rca)

    # ── Stage 7 nodes ─────────────────────────────────────────────────────
    g.add_node("compose_report", compose_report)
    g.add_node("draft_report", draft_report)
    g.add_node("render_files", render_files)
    g.add_node("gate3_approver", gate3_approver)
    g.add_node("esign_archive", esign_archive)
    g.add_node("notify_systems", notify_systems)
    g.add_node("escalate_admin", escalate_admin)

    # ── Stage 8 nodes ─────────────────────────────────────────────────────
    g.add_node("final_output", final_output)
    g.add_node("dispatch_results", dispatch_results)
    g.add_node("track_actions", track_actions)
    g.add_node("close_case", close_case)
    g.add_node("learning_hub", learning_hub)

    # ── Entry point ───────────────────────────────────────────────────────
    g.add_edge(START, "read_part_id")

    # ── Stage 1 edges ─────────────────────────────────────────────────────
    g.add_edge("read_part_id", "load_part_master")
    g.add_conditional_edges("load_part_master", route_part_found, {
        "create_job": "create_job",
        "read_part_id": "read_part_id",
        "job_on_hold": "job_on_hold",
    })
    g.add_edge("create_job", "set_camera_recipe")
    g.add_edge("set_camera_recipe", "capture_images")
    g.add_edge("capture_images", "preprocess_store")
    g.add_conditional_edges("preprocess_store", route_image_quality, {
        "parse_drawing": "parse_drawing",
        "set_camera_recipe": "set_camera_recipe",
        "operator_alert": "operator_alert",
    })
    g.add_edge("job_on_hold", END)
    g.add_edge("operator_alert", END)

    # ── Stage 2 edges ─────────────────────────────────────────────────────
    g.add_edge("parse_drawing", "detect_features")
    g.add_edge("detect_features", "measure_mm")
    g.add_edge("measure_mm", "compare_drawing")
    g.add_edge("compare_drawing", "set_dim_status")
    g.add_edge("set_dim_status", "gate1_engineer")
    g.add_conditional_edges("gate1_engineer", route_gate1, {
        "lock_result": "lock_result",
        "measure_mm": "measure_mm",
        "manual_measurement": "manual_measurement",
    })
    g.add_edge("lock_result", "save_dim")
    g.add_edge("manual_measurement", "save_dim")
    g.add_edge("save_dim", "dispatch_detectors")

    # ── Stage 3 edges ─────────────────────────────────────────────────────
    g.add_edge("dispatch_detectors", "detect_segment")
    g.add_edge("detect_segment", "anomaly_check")
    g.add_edge("anomaly_check", "fuse")
    g.add_conditional_edges("fuse", route_any_defect, {
        "classify_measure": "classify_measure",
        "fast_path_report": "fast_path_report",
    })
    g.add_conditional_edges("classify_measure", route_label_review, {
        "label_review_gate": "label_review_gate",
        "save_defects": "save_defects",
    })
    g.add_edge("label_review_gate", "save_defects")
    g.add_edge("save_defects", "build_query")

    # ── Stage 4 edges ─────────────────────────────────────────────────────
    g.add_edge("build_query", "apply_filters")
    g.add_edge("apply_filters", "embed_query")
    g.add_edge("embed_query", "graph_expand")
    g.add_edge("graph_expand", "set_limits")
    g.add_edge("set_limits", "hybrid_retrieve")
    g.add_edge("hybrid_retrieve", "rerank")
    g.add_conditional_edges("rerank", route_evidence, {
        "assemble_evidence": "assemble_evidence",
        "apply_filters": "apply_filters",  # L4 relax
    })
    g.add_edge("assemble_evidence", "assemble_context")

    # ── Stage 5 edges ─────────────────────────────────────────────────────
    g.add_edge("assemble_context", "llm_reason")
    g.add_edge("llm_reason", "score_conf")
    g.add_edge("score_conf", "rank_top3")
    g.add_edge("rank_top3", "calibrate")
    g.add_edge("calibrate", "format_top3")
    g.add_conditional_edges("format_top3", route_output_valid, {
        "save_ranked": "save_ranked",
        "llm_reason": "llm_reason",  # L5 regenerate
    })
    g.add_edge("save_ranked", "gate2_expert")

    # ── Stage 6 edges ─────────────────────────────────────────────────────
    g.add_conditional_edges("gate2_expert", route_gate2, {
        "finalize_actions": "finalize_actions",
        "set_camera_recipe": "set_camera_recipe",  # L6 reinspect
        "manual_rca": "manual_rca",
    })
    g.add_edge("finalize_actions", "save_decision")
    g.add_edge("save_decision", "record_feedback")
    g.add_edge("record_feedback", "mark_rca_final")
    g.add_edge("mark_rca_final", "compose_report")
    g.add_edge("manual_rca", "compose_report")

    # ── Stage 7 edges (fast path) ─────────────────────────────────────────
    g.add_edge("fast_path_report", "compose_report")

    # ── Stage 7 edges ─────────────────────────────────────────────────────
    g.add_edge("compose_report", "draft_report")
    g.add_conditional_edges("draft_report", route_report_complete, {
        "render_files": "render_files",
        "compose_report": "compose_report",  # L7 add missing data
        "escalate_admin": "escalate_admin",
    })
    g.add_edge("render_files", "gate3_approver")
    g.add_conditional_edges("gate3_approver", route_gate3, {
        "esign_archive": "esign_archive",
        "draft_report": "draft_report",  # L8 redraft
    })
    g.add_edge("esign_archive", "notify_systems")
    g.add_edge("notify_systems", "final_output")
    g.add_edge("escalate_admin", END)

    # ── Stage 8 edges ─────────────────────────────────────────────────────
    g.add_edge("final_output", "dispatch_results")
    g.add_edge("dispatch_results", "track_actions")
    g.add_edge("track_actions", "close_case")
    g.add_edge("close_case", "learning_hub")
    g.add_edge("learning_hub", END)

    return g


@lru_cache(maxsize=1)
def get_compiled_graph():
    """Return the compiled (runnable) LangGraph application."""
    g = build_graph()
    # Try to use Postgres checkpointer if available, fall back to in-memory
    try:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()
    except ImportError:
        checkpointer = None

    if checkpointer:
        return g.compile(checkpointer=checkpointer, interrupt_before=[
            "gate1_engineer",
            "label_review_gate",
            "gate2_expert",
            "gate3_approver",
        ])
    return g.compile(interrupt_before=[
        "gate1_engineer",
        "label_review_gate",
        "gate2_expert",
        "gate3_approver",
    ])
