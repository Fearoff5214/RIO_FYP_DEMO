"""
InspectionState — the single TypedDict that flows through the LangGraph.
Every field is optional (total=False) so nodes only write what they produce.
"""
from __future__ import annotations

from typing import Literal, TypedDict


class InspectionState(TypedDict, total=False):
    # ── Job / part ────────────────────────────────────────────────────────
    job_id: str
    part_number: str
    part_master: dict          # raw part_master row as dict
    thread_id: str
    image_uris: list[str]
    part_verification_id: str | None

    # ── Stage 1: capture ──────────────────────────────────────────────────
    camera_recipe: dict
    images: list[dict]         # [{uri, angle, quality_score, ...}]
    image_quality_ok: bool

    # ── Stage 2: dimensional ──────────────────────────────────────────────
    drawing: dict              # parsed dims, tolerances, GD&T
    measurements: list[dict]   # [{feature_id, nominal, measured, deviation, within_tolerance}]
    dimensional_status: Literal["PASS", "FAIL"]
    dimensional_overlay_uri: str

    # ── Gate 1 ────────────────────────────────────────────────────────────
    gate1: dict                # {decision, reviewer_id, reason_code, comments}

    # ── Stage 3: defect detection ─────────────────────────────────────────
    detections: list[dict]     # raw fused detections before classification
    defects: list[dict]        # classified defects with severity
    defect_found: bool
    min_confidence: float
    fast_path: bool            # True when no defect found

    # ── Label review gate ─────────────────────────────────────────────────
    label_review: dict         # {decision, reviewer_id, corrections}

    # ── Stage 4: retrieval ────────────────────────────────────────────────
    query: dict                # built retrieval query
    retrieved: list[dict]      # raw retrieved chunks
    reranked: list[dict]       # after cross-encoder rerank
    evidence_sufficient: bool
    evidence_pack: dict        # assembled evidence for LLM

    # ── Stage 5: prediction ───────────────────────────────────────────────
    candidates: list[dict]     # LLM output candidates (raw)
    top3: list[dict]           # [{rank, cause, effect, precautions, confidence_raw, confidence_cal, evidence}]
    output_valid: bool

    # ── Gate 2 ────────────────────────────────────────────────────────────
    gate2: dict                # {decision, selected_rank, edited_cause, reason, corrective[], preventive[]}
    final_rca: dict

    # ── Stage 7: report ───────────────────────────────────────────────────
    report: dict               # composed report data
    report_complete: bool
    report_uris: dict          # {pdf, xlsx, docx}

    # ── Gate 3 ────────────────────────────────────────────────────────────
    gate3: dict                # {decision, comments, approved_by, signature_uri}

    # ── Stage 8: output & learning ────────────────────────────────────────
    dispatched: bool
    case_closed: bool

    # ── Cross-cutting ─────────────────────────────────────────────────────
    loops: dict[str, int]      # L1..L9 counters
    flags: list[str]           # "low_evidence", "low_confidence", "manual_measurement", ...
    status: str
    error: str | None
