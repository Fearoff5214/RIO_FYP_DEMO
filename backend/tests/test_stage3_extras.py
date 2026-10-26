"""SAM masks and the PatchCore-style anomaly detector."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.app import config
from backend.app.cv import anomaly, detector, segmenter


def plate(seed):
    rng = np.random.default_rng(seed)
    base = rng.normal(150, 8, (200, 200)).astype(np.float32)
    g = cv2.GaussianBlur(cv2.GaussianBlur(base, (1, 15), 0), (9, 1), 0)
    return cv2.cvtColor(np.clip(g, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    path = tmp_path_factory.mktemp("an") / "default.pt"
    anomaly.fit([plate(i) for i in range(8)], path)
    return path


def test_fit_needs_enough_images(tmp_path):
    with pytest.raises(ValueError, match="at least"):
        anomaly.fit([plate(1), plate(2)], tmp_path / "x.pt")


def test_clean_plate_passes_and_blob_is_localised(model):
    assert not anomaly.score(plate(50), model)["anomalous"]
    bad = plate(51)
    cv2.circle(bad, (130, 70), 14, (40, 40, 40), -1)
    res = anomaly.score(bad, model)
    x1, y1, x2, y2 = res["bbox"]
    assert res["anomalous"] and x1 <= 130 <= x2 and y1 <= 70 <= y2
    assert (x2 - x1) < 120  # tight box, not the whole image


def _setup_detect(monkeypatch, tmp_path, model, yolo_boxes):
    (tmp_path / "an").mkdir()
    (tmp_path / "an" / "default.pt").write_bytes(model.read_bytes())
    monkeypatch.setattr(config, "ANOMALY_DIR", tmp_path / "an")
    monkeypatch.setattr(config, "SAM_ENABLED", False)
    monkeypatch.setattr(detector, "_detect_primary", lambda p: [dict(b) for b in yolo_boxes])
    bad = plate(52)
    cv2.circle(bad, (130, 70), 14, (40, 40, 40), -1)
    img = tmp_path / "bad.png"
    cv2.imwrite(str(img), bad)
    return img


def test_unseen_defect_becomes_unknown_anomaly_below_review_threshold(monkeypatch, tmp_path, model):
    img = _setup_detect(monkeypatch, tmp_path, model, [])
    dets = detector.detect(img, "ANY-PART")
    assert [d["cls"] for d in dets] == ["unknown_anomaly"]
    assert dets[0]["conf"] < config.LABEL_REVIEW_CONF  # forces the human label-review gate


def test_anomaly_already_explained_by_yolo_box_is_not_duplicated(monkeypatch, tmp_path, model):
    box = {"cls": "scratches", "conf": 0.9, "bbox": [90, 30, 170, 110], "source": "yolo"}
    img = _setup_detect(monkeypatch, tmp_path, model, [box])
    assert [d["cls"] for d in detector.detect(img)] == ["scratches"]


def test_anomaly_skipped_when_no_model_fitted(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ANOMALY_DIR", tmp_path / "none")
    monkeypatch.setattr(config, "SAM_ENABLED", False)
    monkeypatch.setattr(detector, "_detect_primary", lambda p: [])
    cv2.imwrite(str(tmp_path / "a.png"), plate(1))
    assert detector.detect(tmp_path / "a.png") == []


def test_sam_failure_degrades_without_losing_detections(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SAM_ENABLED", True)
    monkeypatch.setattr(segmenter, "_model", lambda: (_ for _ in ()).throw(OSError("no weights")))
    dets = [{"cls": "x", "conf": 0.9, "bbox": [1, 1, 5, 5]}]
    assert segmenter.segment(tmp_path / "a.png", dets) == dets
    assert "no weights" in segmenter.sam_error


@pytest.mark.skipif(not Path(config.SAM_WEIGHTS).exists(), reason="SAM weights not downloaded yet")
def test_real_sam_adds_mask_and_tightens_severity(monkeypatch):
    monkeypatch.setattr(config, "SAM_ENABLED", True)
    img = config.ROOT / "samples" / "defect_scratches.jpg"
    dets = segmenter.segment(img, [{"cls": "scratches", "conf": 0.7, "bbox": [27.0, 16.3, 41.2, 169.8]}])
    assert segmenter.sam_error is None
    d = dets[0]
    assert 0 < d["mask_frac"] < 0.05 and len(d["polygon"]) >= 3
    box_frac = (41.2 - 27.0) * (169.8 - 16.3) / (200 * 200)
    assert d["mask_frac"] < box_frac  # a thin scratch fills only part of its box
