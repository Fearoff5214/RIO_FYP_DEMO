"""End-to-end graph tests: every loop is forced to its retry cap, every gate is exercised."""
from pathlib import Path

from backend.app import config, db
from backend.app.graph import workflow

from .conftest import gate_name, run_to_gate

CONFIRM = {"confirm": True, "reviewer": "eng"}
SELECT1 = {"action": "select", "rank": 1, "reviewer": "expert", "reason": "matches roller wear"}
APPROVE = {"approved": True, "approver": "qm"}


def stages(job_id):
    return [a["stage"] for a in db.get_audit(job_id) if a["event"] == "done"]


def test_ng_happy_path_through_all_three_gates(env, image, detections):
    job = workflow.start_job("SM-1001", [image])
    seen = run_to_gate(job, {"engineer": CONFIRM, "expert": SELECT1, "approver": APPROVE})
    assert seen == ["engineer", "expert", "approver"]
    snap = workflow.status(job)
    assert snap["next"] == [] and snap["state"]["status"] == "completed"
    j = db.get_job(job)
    assert j["status"] == "completed" and j["result"]["result"] == "NG"
    for ext in ("pdf", "xlsx", "docx"):
        assert Path(j["result"]["report_paths"][ext]).stat().st_size > 0
    assert any(a["description"] for a in db.list_actions(job))
    assert any(c["source"] == f"case-{job}" for c in db.all_chunks())  # L11
    assert db.get_feedback("expert_choice")
    assert {"load_context", "capture", "retrieve", "rca", "report", "finalize"} <= set(stages(job))


def test_fast_path_skips_stages_4_to_6(env, image, detections):
    detections["value"] = []
    job = workflow.start_job("SM-1001", [image])
    seen = run_to_gate(job, {"engineer": CONFIRM, "approver": APPROVE})
    assert seen == ["engineer", "approver"]
    assert not {"retrieve", "rca", "gate2_expert"} & set(stages(job))
    assert db.get_job(job)["result"]["result"] == "OK"


def test_l1_unknown_part_rescans_then_holds(env, image, detections):
    job = workflow.start_job("NOPE", [image])
    seen = run_to_gate(job, {"part_number": {"part_number": "STILL-NOPE"}})
    assert seen.count("part_number") == config.MAX_RETRIES["L1"]
    assert db.get_job(job)["status"] == "on_hold"


def test_l1_rescan_with_valid_part_continues(env, image, detections):
    job = workflow.start_job("NOPE", [image])
    workflow.resume(job, {"part_number": "SM-1001"})
    assert gate_name(job) == "engineer"
    assert db.get_job(job)["part_number"] == "SM-1001"


def test_l2_quality_retries_cap_then_flags(env, detections):
    import cv2
    import numpy as np
    flat = env / "flat.png"
    cv2.imwrite(str(flat), np.full((120, 120, 3), 128, np.uint8))
    job = workflow.start_job("SM-1001", [str(flat)])
    st = workflow.status(job)["state"]
    assert st["retries"]["L2"] == config.MAX_RETRIES["L2"]
    assert any(f.startswith("image_quality_unresolved") for f in st["flags"])


def test_l3_engineer_rejects_until_manual_measurement(env, image, detections):
    job = workflow.start_job("SM-1001", [image])
    run_to_gate(job, {"engineer": {"confirm": False, "scale_override": 1.0}, "expert": SELECT1, "approver": APPROVE})
    st = workflow.status(job)["state"]
    assert st["retries"]["L3"] == config.MAX_RETRIES["L3"]
    assert "manual_measurement_required" in st["flags"]
    assert st["dimensional"]["px_per_mm"] == 1.0  # re-measured with the engineer's recalibration


def test_label_review_gate_on_low_confidence_records_correction(env, image, detections):
    detections["value"] = [{"cls": "patches", "conf": 0.5, "bbox": [0, 0, 20, 20], "source": "test"}]
    job = workflow.start_job("SM-1001", [image])
    fixed = [{"cls": "scratches", "conf": 1.0, "bbox": [0, 0, 20, 20], "source": "human"}]
    seen = run_to_gate(job, {"engineer": CONFIRM, "label_review": {"defects": fixed, "reviewer": "r"},
                             "expert": SELECT1, "approver": APPROVE})
    assert seen[:2] == ["engineer", "label_review"]
    assert db.get_feedback("label_correction")[0]["payload"]["after"] == fixed  # L10 training signal


def test_l4_empty_knowledge_base_flags_low_evidence(env, image, detections):
    with db.tx() as c:
        c.execute("DELETE FROM kb_chunks")
    job = workflow.start_job("SM-1001", [image])
    run_to_gate(job, {"engineer": CONFIRM})
    st = workflow.status(job)["state"]
    assert st["retries"]["L4"] == config.MAX_RETRIES["L4"] and "low_evidence" in st["flags"]
    assert gate_name(job) == "expert"  # empty candidate list: expert writes the RCA


def test_l6_reject_all_reinspects_once_then_manual_rca(env, image, detections):
    reject = {"action": "reject_all", "reviewer": "x", "reason": "none fit", "text": "Operator error"}
    job = workflow.start_job("SM-1001", [image])
    seen = run_to_gate(job, {"engineer": CONFIRM, "expert": reject, "approver": APPROVE})
    assert seen.count("expert") == 2 and seen.count("engineer") == 2
    st = workflow.status(job)["state"]
    assert "manual_rca" in st["flags"] and st["selected_cause"]["cause"] == "Operator error"


def test_l8_approver_reject_redrafts_with_comments(env, image, detections):
    job = workflow.start_job("SM-1001", [image])
    run_to_gate(job, {"engineer": CONFIRM, "expert": SELECT1,
                      "approver": [{"approved": False, "comments": "add torque data"}]})
    # the helper repeats a lone answer, so the loop ends at the L8 cap
    st = workflow.status(job)["state"]
    assert st["retries"]["L8"] == config.MAX_RETRIES["L8"] + 1
    assert st["report_revision"] == config.MAX_RETRIES["L8"] + 1
    assert st["approver_comments"][0] == "add torque data"
    assert db.get_job(job)["status"] == "on_hold"


def test_l8_reject_once_then_approve(env, image, detections):
    job = workflow.start_job("SM-1001", [image])
    run_to_gate(job, {"engineer": CONFIRM, "expert": SELECT1,
                      "approver": [{"approved": False, "comments": "redo"}, APPROVE]})
    st = workflow.status(job)["state"]
    assert st["report_revision"] == 2 and st["status"] == "completed"
    assert "report_rev2" in st["report_paths"]["pdf"]


def test_checkpoint_survives_new_graph_instance(env, image, detections):
    """A gate stays pending when the graph object is rebuilt on the same checkpointer."""
    saver = workflow.graph().checkpointer
    job = workflow.start_job("SM-1001", [image])
    workflow.use_graph(workflow.build(saver))
    assert gate_name(job) == "engineer"
    workflow.resume(job, CONFIRM)
    assert gate_name(job) == "expert"


def _flat(env):
    import cv2
    import numpy as np
    flat = env / "flat.png"
    cv2.imwrite(str(flat), np.full((120, 120, 3), 128, np.uint8))
    return str(flat)


def test_unusable_image_stops_at_operator_gate_instead_of_passing(env, detections):
    detections["value"] = []  # a blank frame detects nothing: without the gate this would be "OK"
    job = workflow.start_job("SM-1001", [_flat(env)])
    assert gate_name(job) == "operator"
    workflow.resume(job, {"action": "abort"})
    j = db.get_job(job)
    assert j["status"] == "on_hold" and workflow.status(job)["next"] == []
    assert "aborted_by_operator" in workflow.status(job)["state"]["flags"]


def test_operator_can_retake_with_a_good_photo(env, image, detections):
    job = workflow.start_job("SM-1001", [_flat(env)])
    workflow.resume(job, {"action": "retake", "image_paths": [image]})
    st = workflow.status(job)["state"]
    assert gate_name(job) == "engineer"
    assert st["retries"]["L2"] == 0 and not any(f.startswith("image_quality_unresolved") for f in st["flags"])


def test_operator_can_accept_a_poor_image_and_it_is_flagged(env, detections):
    job = workflow.start_job("SM-1001", [_flat(env)])
    workflow.resume(job, {"action": "accept"})
    assert gate_name(job) == "engineer"
    assert "accepted_poor_image" in workflow.status(job)["state"]["flags"]


GOOD_CAUSES = {"causes": [{"cause": "worn roller", "effect": "scratch lines", "precautions": ["replace roller"],
                           "sources": [1], "rationale": "KB paragraph 1"}]}


def test_l5_invalid_llm_output_is_regenerated_then_accepted(env, image, detections, monkeypatch):
    from backend.app import llm
    replies = iter([None, {"causes": [{"cause": "uncited"}]}, GOOD_CAUSES])  # invalid, invalid, valid
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda s, u: next(replies))
    job = workflow.start_job("SM-1001", [image])
    run_to_gate(job, {"engineer": CONFIRM})
    st = workflow.status(job)["state"]
    assert st["retries"]["L5"] == 2 and "low_confidence" not in st["flags"]
    assert st["rca"][0]["cause"] == "worn roller"


def test_l5_gives_up_after_cap_and_falls_back_to_evidence(env, image, detections, monkeypatch):
    from backend.app import llm
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda s, u: {"causes": []})
    job = workflow.start_job("SM-1001", [image])
    run_to_gate(job, {"engineer": CONFIRM})
    st = workflow.status(job)["state"]
    assert st["retries"]["L5"] == config.MAX_RETRIES["L5"] and "low_confidence" in st["flags"]
    assert st["rca"]  # still gives the expert candidates, taken from the documents


def test_l7_incomplete_report_is_repaired_once(env, image, detections, monkeypatch):
    from backend.app import report
    real, calls = report.missing, {"n": 0}

    def missing_once(data):
        calls["n"] += 1
        return ["dimensional"] if calls["n"] == 1 else real(data)
    monkeypatch.setattr(report, "missing", missing_once)
    job = workflow.start_job("SM-1001", [image])
    run_to_gate(job, {"engineer": CONFIRM, "expert": SELECT1})
    st = workflow.status(job)["state"]
    assert st["retries"]["L7"] == 1 and st["report_paths"] and gate_name(job) == "approver"
