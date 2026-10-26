"""Live-camera loop L2, output connectors with outbox retry, and the learning loops."""
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
import requests

from backend.app import camera, config, db, integrations, learning
from backend.app.graph import workflow

from .conftest import SAMPLES, run_to_gate

CONFIRM = {"confirm": True, "reviewer": "eng"}
SELECT1 = {"action": "select", "rank": 1, "reviewer": "expert", "reason": "ok"}
APPROVE = {"approved": True, "approver": "qm"}


# --- camera ---------------------------------------------------------------------------------

class FakeCam:
    """Returns a flat blurry frame until the recipe asks for autofocus (what a blur problem triggers)."""

    def __init__(self, tmp):
        self.tmp, self.calls = tmp, []

    def capture(self, device, dest, n, recipe=None, **kw):
        self.calls.append((device, dict(recipe or {})))
        good = bool(recipe) and ("autofocus" in recipe or "brightness" in recipe)
        img = cv2.imread(str(SAMPLES / "defect_scratches.jpg")) if good else np.full((120, 120, 3), 128, np.uint8)
        dest.mkdir(parents=True, exist_ok=True)
        out = []
        for i in range(n):
            p = dest / f"f{len(self.calls)}_{i}.png"
            cv2.imwrite(str(p), img)
            out.append(str(p))
        return out


def test_adjust_recipe_reacts_to_problem():
    assert camera.adjust_recipe({}, ["glare"])["brightness"] < 128
    assert camera.adjust_recipe({}, ["exposure"])["brightness"] > 128
    assert camera.adjust_recipe({}, ["blur"])["autofocus"] is True


def test_l2_with_live_camera_changes_recipe_and_recaptures(env, detections, monkeypatch):
    cam = FakeCam(env)
    monkeypatch.setattr(camera, "capture", cam.capture)
    first = cam.capture(1, env / "up", 1)  # the initial (bad) frame the API would have taken
    job = workflow.start_job("SM-1001", first, source={"type": "camera", "device": 1})
    st = workflow.status(job)["state"]
    assert st["retries"]["L2"] == 1  # one recapture was enough
    assert st["recipe"].get("autofocus") is True
    assert cam.calls[-1][0] == 1 and cam.calls[-1][1].get("autofocus") is True
    assert not any(f.startswith("image_quality_unresolved") for f in st["flags"])


def test_camera_failure_falls_back_to_software_adjust(env, detections, monkeypatch):
    def broken(*a, **k):
        raise camera.CameraError("unplugged")
    monkeypatch.setattr(camera, "capture", broken)
    flat = env / "flat.png"
    cv2.imwrite(str(flat), np.full((120, 120, 3), 128, np.uint8))
    job = workflow.start_job("SM-1001", [str(flat)], source={"type": "camera", "device": 1})
    flags = workflow.status(job)["state"]["flags"]
    assert any(f.startswith("camera_error:unplugged") for f in flags)


def test_reject_all_recaptures_at_default_recipe(env, detections, monkeypatch):
    shot = env / "ok.png"
    shutil.copy(SAMPLES / "defect_scratches.jpg", shot)
    calls = []

    def cap(device, dest, n, recipe=None, **kw):
        calls.append(recipe)
        p = dest / "again.png"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(SAMPLES / "defect_scratches.jpg", p)
        return [str(p)]
    monkeypatch.setattr(camera, "capture", cap)
    job = workflow.start_job("SM-1001", [str(shot)], source={"type": "camera", "device": 2})
    reject = {"action": "reject_all", "reviewer": "x", "reason": "none fit", "text": "manual"}
    run_to_gate(job, {"engineer": CONFIRM, "expert": reject, "approver": APPROVE})
    assert calls == [camera.DEFAULT_RECIPE]  # exactly one recapture, at the default recipe


# --- integrations -----------------------------------------------------------------------------

@pytest.fixture
def systems(monkeypatch):
    """All four connectors on; _post records deliveries, and can be made to fail."""
    for name in ("MES", "QMS", "ERP", "NOTIFY"):
        monkeypatch.setattr(config, f"{name}_URL", f"http://plant/{name.lower()}")
    monkeypatch.setattr(config, "INTEGRATION_ATTEMPTS", 3)
    box = {"fail": False, "sent": []}

    def post(url, payload, key):
        if box["fail"]:
            raise requests.ConnectionError("down")
        box["sent"].append((url.rsplit("/", 1)[1], key, payload))
    monkeypatch.setattr(integrations, "_post", post)
    return box


CTX = {"part_number": "P1", "result": "NG", "completed_at": 1.0,
       "defects": [{"cls": "dent", "severity": "high"}], "dimensional": {"status": "PASS"},
       "selected_cause": {"cause": "die debris"}, "actions": ["clean die"], "approver": "qm"}


def test_dispatch_shapes_per_system(env, systems):
    out = integrations.dispatch("j1", CTX, sleep=lambda s: None)
    assert out == {"mes": "sent", "qms": "sent", "erp": "sent", "notify": "sent"}
    by = {s: p for s, _, p in systems["sent"]}
    assert by["mes"]["disposition"] == "hold" and by["erp"]["quarantine"] and by["erp"]["scrap_review"]
    assert by["qms"]["root_cause"]["cause"] == "die debris" and "die debris" in by["notify"]["text"]
    assert {k for _, k, _ in systems["sent"]} == {"j1:mes", "j1:qms", "j1:erp", "j1:notify"}


def test_disabled_connector_is_skipped(env, systems, monkeypatch):
    monkeypatch.setattr(config, "ERP_URL", "")
    assert integrations.dispatch("j2", CTX, sleep=lambda s: None)["erp"] == "disabled"


def test_outage_is_queued_then_delivered_on_retry_without_duplicates(env, systems):
    systems["fail"] = True
    out = integrations.dispatch("j3", CTX, sleep=lambda s: None)
    assert set(out.values()) == {"failed"} and not systems["sent"]
    assert {r["attempts"] for r in db.outbox_list(status="failed")} == {3}
    systems["fail"] = False
    assert integrations.retry_pending(sleep=lambda s: None) == {"sent": 4, "failed": 0}
    assert integrations.retry_pending(sleep=lambda s: None) == {"sent": 0, "failed": 0}
    integrations.dispatch("j3", CTX, sleep=lambda s: None)  # re-dispatch the same job
    assert len(systems["sent"]) == 4  # already-sent messages are not sent twice


def test_finished_job_dispatches_and_survives_connector_outage(env, image, detections, systems):
    systems["fail"] = True
    job = workflow.start_job("SM-1001", [image])
    run_to_gate(job, {"engineer": CONFIRM, "expert": SELECT1, "approver": APPROVE})
    assert db.get_job(job)["status"] == "completed"  # outage did not fail the signed-off job
    assert len(db.outbox_list(status="failed", job_id=job)) == 4


# --- learning ---------------------------------------------------------------------------------

def _label_fix(job_id, after_cls, image):
    before = [{"cls": "patches", "conf": 0.5, "bbox": [10, 10, 60, 60], "image": image}]
    after = [{"cls": after_cls, "conf": 1.0, "bbox": [10, 10, 60, 60], "image": image}] if after_cls else []
    db.add_feedback(job_id, "label_correction", {"before": before, "after": after, "reviewer": "r"})


def test_recalibration_blends_acceptance_rates(env, monkeypatch):
    monkeypatch.setattr(config, "RECAL_MIN_SAMPLES", 4)
    assert learning.apply_calibration(1, 80.0) == 80.0  # no data yet: raw confidence
    for rank in (1, 1, 1, 2):  # experts picked rank 1 three times, rank 2 once
        db.add_feedback("j", "expert_choice", {"chosen_rank": rank, "edited": False, "confidences": [80, 70, 60]})
    cal = learning.recalibrate()
    assert cal["active"] and cal["rank_acc"]["1"] == 0.75 and cal["rank_acc"]["3"] == 0.0
    assert learning.apply_calibration(1, 80.0) == 77.5  # 0.5*80 + 0.5*75
    assert learning.apply_calibration(3, 60.0) == 30.0  # never chosen: confidence pulled down


def test_dataset_export_writes_yolo_labels_and_negatives(env, tmp_path):
    img = str(SAMPLES / "defect_scratches.jpg")
    db.add_feedback("a", "label_correction", {"before": [], "after": [], "reviewer": "r"})  # no-op correction
    _label_fix("a", "scratches", img)
    _label_fix("b", None, str(SAMPLES / "defect_patches.jpg"))  # false alarm -> empty label file
    rows = learning.correction_rows()
    assert len(rows) == 2
    ds = learning.export_dataset(rows, tmp_path / "ds", ["crazing", "scratches"])
    labels = list((tmp_path / "ds" / "labels").rglob("*.txt"))
    assert len(labels) == 2 and sorted(p.read_text().strip() == "" for p in labels) == [False, True]
    positive = next(p for p in labels if p.read_text().strip()).read_text().split()
    assert positive[0] == "1" and all(0 <= float(v) <= 1 for v in positive[1:])
    assert ds["n_train"] + ds["n_val"] >= 2 and Path(ds["yaml"]).exists()


@pytest.mark.parametrize("new_map,expected", [(0.60, "promoted"), (0.30, "rejected")])
def test_retrain_promotes_only_if_not_worse(env, monkeypatch, new_map, expected):
    img = str(SAMPLES / "defect_scratches.jpg")
    _label_fix("a", "scratches", img)
    _label_fix("b", "scratches", str(SAMPLES / "defect_patches.jpg"))
    metrics = iter([0.50, new_map])  # baseline mAP, then candidate mAP
    monkeypatch.setattr(learning, "_map50", lambda w, y: next(metrics))

    def fake_trainer(base, yaml, out):
        out.mkdir(parents=True, exist_ok=True)
        f = out / "fake.pt"
        shutil.copy(base, f)
        return f
    res = learning.retrain(force=True, trainer=fake_trainer)
    assert res["status"] == expected and res["version"] == "v1"
    reg = learning.registry()
    assert reg["active"] == ("v1" if expected == "promoted" else "baseline")
    assert learning.correction_rows() == []  # labels are consumed either way
    learning.set_active("baseline")  # rollback works
    assert learning.active_weights() == config.YOLO_WEIGHTS


def test_retrain_waits_for_enough_labels(env):
    _label_fix("a", "scratches", str(SAMPLES / "defect_scratches.jpg"))
    assert learning.retrain()["status"] == "not_enough_labels"
    with pytest.raises(KeyError):
        learning.set_active("v99")


def test_retrain_never_promotes_without_labelled_validation_objects(env, monkeypatch):
    """Only a false-alarm (empty-label) image: mAP is undefined, so the model must not go live."""
    _label_fix("a", None, str(SAMPLES / "defect_scratches.jpg"))
    monkeypatch.setattr(learning, "_map50", lambda w, y: 0.0)

    def fake_trainer(base, yaml, out):
        out.mkdir(parents=True, exist_ok=True)
        f = out / "fake.pt"
        shutil.copy(base, f)
        return f
    res = learning.retrain(force=True, trainer=fake_trainer)
    assert res["status"] == "unvalidated" and learning.registry()["active"] == "baseline"
