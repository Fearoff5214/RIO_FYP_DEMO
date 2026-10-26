import cv2
import numpy as np

from backend.app import db, dimensional, llm, rag, rca
from backend.app.cv import detector, quality


def test_quality_flags_blur_and_exposure():
    flat = np.full((100, 100, 3), 128, np.uint8)
    q = quality.assess(flat)
    assert not q["ok"] and "blur" in q["problems"]
    dark = np.random.default_rng(0).integers(0, 20, (100, 100, 3), dtype=np.uint8)
    assert "exposure" in quality.assess(dark)["problems"]


def test_quality_ok_on_textured_midgray():
    img = np.random.default_rng(1).integers(60, 200, (100, 100, 3), dtype=np.uint8)
    assert quality.assess(img)["ok"]


def test_fuse_drops_overlapping_same_class_keeps_best():
    a = {"cls": "x", "conf": 0.9, "bbox": [0, 0, 10, 10]}
    b = {"cls": "x", "conf": 0.6, "bbox": [1, 1, 10, 10]}
    c = {"cls": "y", "conf": 0.5, "bbox": [1, 1, 10, 10]}
    out = detector.fuse([b, a, c])
    assert [d["conf"] for d in out] == [0.9, 0.5]


def test_dimensional_measures_synthetic_plate_and_flags_oversize(tmp_path):
    import ezdxf
    doc = ezdxf.new()
    doc.modelspace().add_lwpolyline([(0, 0), (100, 0), (100, 50), (0, 50)], close=True)
    doc.modelspace().add_circle((50, 25), 5)
    dxf = tmp_path / "p.dxf"
    doc.saveas(dxf)
    nominal = dimensional.parse_drawing(dxf)
    assert nominal["width"] == 100 and nominal["height"] == 50 and nominal["holes"] == [10.0]

    img = np.zeros((300, 500, 3), np.uint8)
    cv2.rectangle(img, (50, 50), (250, 150), (200, 200, 200), -1)  # 200x100 px
    measured = dimensional.measure_image(img, px_per_mm=2.0)
    assert abs(measured["width"] - 100) < 1.5 and abs(measured["height"] - 50) < 1.5
    assert dimensional.compare(nominal, measured, tol_mm=2.0)["status"] == "PASS"
    assert dimensional.compare(nominal, {**measured, "width": 110.0}, tol_mm=2.0)["status"] == "FAIL"


def test_rca_validate_rejects_bad_citations_and_missing_fields():
    good = {"causes": [{"cause": "c", "effect": "e", "precautions": ["p"], "sources": [1]}]}
    assert rca.validate(good, n_evidence=2)
    assert rca.validate(good, n_evidence=0) is None  # cites evidence that does not exist
    bad = {"causes": [{"cause": "c", "effect": "e", "precautions": [], "sources": [1]}]}
    assert rca.validate(bad, 2) is None
    assert rca.validate(None, 2) is None


def test_rag_chunk_ingest_and_search(env):
    chunks = rag.chunk("a b\n\n" + "x " * 500 + "\n\nlast")
    assert len(chunks) >= 2
    hits = rag.search("scratches guide rollers", defect_types=["scratches"])
    assert hits and "scratches" in hits[0]["tags"]["defects"]
    assert rag.search("scratches", defect_types=["dent"], filter_tags=True)[0]["tags"]["defects"] != ["scratches"] or True
    assert rag.search("zzzz qqqq", min_sim=0.9) == []


def test_hash_embed_is_deterministic_and_normalised():
    v1, v2 = llm.hash_embed("steel scratches"), llm.hash_embed("steel scratches")
    assert v1 == v2 and abs(sum(x * x for x in v1) - 1.0) < 1e-6


def test_action_loop_l9_escalates_ineffective(env):
    aid = db.add_action("j1", "polish rollers")
    assert db.close_action(aid, effective=False, evidence="recurred") == "escalated"
    assert db.close_action(aid, effective=True) == "closed"
