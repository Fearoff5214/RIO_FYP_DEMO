"""Unit tests for workflow routing and loop counters."""
import pytest
from app.workflow.routing import (
    route_part_found,
    route_image_quality,
    route_any_defect,
    route_label_review,
    route_evidence,
    route_output_valid,
    route_gate1,
    route_gate2,
    route_gate3,
)


def test_route_part_found_ok():
    state = {"part_master": {"part_number": "MS-4505-001"}, "loops": {}}
    assert route_part_found(state) == "create_job"


def test_route_part_found_retry_l1():
    state = {"part_master": None, "loops": {}}
    route = route_part_found(state)
    assert route == "read_part_id"
    assert state["loops"]["L1"] == 1


def test_route_part_found_on_hold_after_max():
    state = {"part_master": None, "loops": {"L1": 2}}
    route = route_part_found(state)
    assert route == "job_on_hold"


def test_route_image_quality_ok():
    state = {"image_quality_ok": True, "loops": {}}
    assert route_image_quality(state) == "parse_drawing"


def test_route_image_quality_retry():
    state = {"image_quality_ok": False, "loops": {}}
    route = route_image_quality(state)
    assert route == "set_camera_recipe"
    assert state["loops"]["L2"] == 1


def test_route_any_defect_found():
    state = {"defect_found": True, "loops": {}}
    assert route_any_defect(state) == "classify_measure"


def test_route_any_defect_fast_path():
    state = {"defect_found": False, "loops": {}}
    assert route_any_defect(state) == "fast_path_report"


def test_route_label_review_triggered():
    state = {
        "min_confidence": 0.76,
        "defects": [{"defect_type": "crack", "confidence": 0.76}],
        "loops": {},
    }
    assert route_label_review(state) == "label_review_gate"


def test_route_label_review_skip():
    state = {
        "min_confidence": 0.92,
        "defects": [{"defect_type": "scratch", "confidence": 0.92}],
        "loops": {},
    }
    assert route_label_review(state) == "save_defects"


def test_route_evidence_sufficient():
    state = {"evidence_sufficient": True, "loops": {}, "flags": []}
    assert route_evidence(state) == "assemble_evidence"


def test_route_evidence_l4_retry():
    state = {"evidence_sufficient": False, "loops": {}, "flags": []}
    route = route_evidence(state)
    assert route == "apply_filters"
    assert state["loops"]["L4"] == 1


def test_route_evidence_l4_exhausted():
    state = {"evidence_sufficient": False, "loops": {"L4": 2}, "flags": []}
    route = route_evidence(state)
    assert route == "assemble_evidence"
    assert "low_evidence" in state["flags"]


def test_route_gate1_confirm():
    state = {"gate1": {"decision": "confirm"}, "loops": {}}
    assert route_gate1(state) == "lock_result"


def test_route_gate1_override():
    state = {"gate1": {"decision": "override", "reason_code": "calibration_error"}, "loops": {}}
    assert route_gate1(state) == "lock_result"


def test_route_gate1_reject_l3():
    state = {"gate1": {"decision": "reject"}, "loops": {}}
    route = route_gate1(state)
    assert route == "measure_mm"
    assert state["loops"]["L3"] == 1


def test_route_gate2_accept():
    state = {"gate2": {"decision": "accept"}, "loops": {}}
    assert route_gate2(state) == "finalize_actions"


def test_route_gate2_reject_reinspect():
    state = {"gate2": {"decision": "reject_all", "next": "reinspect"}, "loops": {}}
    assert route_gate2(state) == "set_camera_recipe"


def test_route_gate3_approve():
    state = {"gate3": {"decision": "approve"}, "loops": {}}
    assert route_gate3(state) == "esign_archive"


def test_route_gate3_reject_redraft():
    state = {"gate3": {"decision": "reject"}, "loops": {}}
    assert route_gate3(state) == "draft_report"
