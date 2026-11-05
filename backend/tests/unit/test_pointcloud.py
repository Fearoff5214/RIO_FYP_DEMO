"""Point-cloud inspection of bracket MS-4505-001 and the RCA report picture / "no defect" report."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from app.cv.pointcloud_inspector import PointCloudError, inspect_pointcloud, load_point_cloud
from app.reports.evidence import render_frame_evidence, render_pointcloud_evidence
from app.reports.rca_document import build_view, render_rca_documents, to_markdown
from app.workflow.rca_pipeline import build_report, run_rca

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def clouds():
    """Simulated scans (0.25 mm spacing, 0.03 mm noise, random offset) of the bracket variants."""
    pytest.importorskip("trimesh")
    pytest.importorskip("manifold3d")
    sys.path.insert(0, str(SCRIPTS))
    import bracket_variants as bv
    from make_bracket_pointclouds import sample_cloud

    variants = bv.make_variants()
    return {name: sample_cloud(bv.build_mesh(variants[name]), spacing=0.25) for name in ("good", "defect", "crack", "size_mismatch")}


def kinds(result):
    return sorted(d["defect_type"] for d in result["defects"])


def test_good_part_passes(clouds):
    result = inspect_pointcloud(clouds["good"])
    assert result["status"] == "PASS" and result["defects"] == []
    assert all(m["within_tolerance"] for m in result["measurements"])


def test_good_part_survives_sparse_noisy_scan(clouds):
    rng = np.random.default_rng(5)
    cloud = clouds["good"][rng.random(len(clouds["good"])) < 0.4]
    assert inspect_pointcloud(cloud + rng.normal(0, 0.04, cloud.shape))["status"] == "PASS"


def test_surface_defects_and_bend(clouds):
    result = inspect_pointcloud(clouds["defect"])
    assert kinds(result) == ["deformation", "dent", "scratch"]
    bend = next(d for d in result["defects"] if d["defect_type"] == "deformation")
    assert bend["note"].startswith(("bend 92.9", "bend 93.0", "bend 93.1"))


def test_cracks_found_on_base_and_flange(clouds):
    result = inspect_pointcloud(clouds["crack"])
    assert kinds(result) == ["crack", "crack"]


def test_size_mismatch_length_and_holes(clouds):
    result = inspect_pointcloud(clouds["size_mismatch"])
    notes = " | ".join(d["note"] for d in result["defects"])
    assert "length 118.3" in notes or "length 118.4" in notes
    assert "base hole 3: dia 12.6" in notes or "base hole 3: dia 12.7" in notes
    assert "base hole 4: position off" in notes and "flange hole 2: position off" in notes
    measured = {m["feature_id"]: m["actual"] for m in result["measurements"]}
    assert measured["Length (X)"] == pytest.approx(118.4, abs=0.05)
    assert measured["Base hole 3 dia"] == pytest.approx(12.7, abs=0.05)


def test_rejects_scan_that_is_not_the_bracket():
    with pytest.raises(PointCloudError, match="not bracket"):
        inspect_pointcloud(np.random.default_rng(0).uniform(0, 50, (5000, 3)))


def test_loader_reads_xyz_and_rejects_small_clouds():
    text = "\n".join(f"{i % 50} {i % 30} {i % 7}" for i in range(3000)).encode()
    assert load_point_cloud(text, "scan.xyz").shape == (3000, 3)
    with pytest.raises(PointCloudError, match="at least"):
        load_point_cloud(b"1 2 3\n4 5 6\n", "scan.xyz")


def _state(result, picture):
    return {"job_id": "t", "part_master": {"part_number": "MS-4505-001", "part_name": "Bracket", "material": "SPCC Steel", "process": "bending"},
            "defects": result["defects"], "measurements": result["measurements"],
            "evidence_images": [{"path": str(picture), "caption": "scan"}]}


@pytest.mark.asyncio
async def test_good_part_gets_no_defect_report_with_picture(clouds, tmp_path):
    result = inspect_pointcloud(clouds["good"])
    picture = render_pointcloud_evidence(result, tmp_path / "good.png")
    state = await run_rca(_state(result, picture))          # nothing to analyse: no LLM call
    report = build_report(state)
    assert report["verdict"] == "NO_DEFECT" and report["root_cause"] is None
    docs = await render_rca_documents(report, out_dir=tmp_path, stem="good")
    md = Path(docs["md"]).read_text(encoding="utf-8")
    assert "NO DEFECT FOUND" in md and "![scan](good_evidence1.png)" in md and "Root cause" not in md
    assert (tmp_path / "good_evidence1.png").is_file()
    assert all(Path(p).stat().st_size > 1000 for p in docs.values())


@pytest.mark.asyncio
async def test_defect_report_embeds_picture(clouds, tmp_path):
    result = inspect_pointcloud(clouds["size_mismatch"])
    picture = render_pointcloud_evidence(result, tmp_path / "bad.png")
    report = build_report(await run_rca(_state(result, picture)))
    assert report["verdict"] == "DEFECT" and report["root_cause"]["cause"]
    view = build_view(report)
    assert not view["clean"] and len(view["images"]) == 1
    docs = await render_rca_documents(report, out_dir=tmp_path, stem="bad")
    assert "![scan](bad_evidence1.png)" in Path(docs["md"]).read_text(encoding="utf-8")
    from docx import Document

    assert len(Document(docs["docx"]).inline_shapes) == 1


def test_frame_evidence_marks_defects_and_banner(tmp_path):
    frame = np.full((240, 320, 3), 180, np.uint8)
    bad = render_frame_evidence(frame, [{"defect_type": "crack", "polygon": [[10, 10], [90, 12], [60, 80]], "bbox": {"x1": 10, "y1": 10, "x2": 90, "y2": 80}}], tmp_path / "bad.png")
    good = render_frame_evidence(frame, [], tmp_path / "good.png")
    import cv2

    assert not np.array_equal(cv2.imread(str(bad)), cv2.imread(str(good)))
    assert not np.array_equal(cv2.imread(str(good)), frame)          # banner drawn on the clean frame too


def test_markdown_of_clean_view_has_measurement_table():
    view = build_view({"job_id": "x", "part": {}, "defects": [], "root_cause": None,
                       "measurements": [{"feature_id": "Length (X)", "nominal": 120.0, "actual": 120.01, "tolerance": 0.1, "within_tolerance": True}]})
    md = to_markdown(view)
    assert "| Length (X) | 120.0 | 120.01 | ±0.1 | OK |" in md


# ---- the picture must reach every report format, now and for future report types ----------
def _picture(tmp_path):
    import cv2

    path = tmp_path / "part.png"
    cv2.imwrite(str(path), np.full((120, 160, 3), 120, np.uint8))
    return path


def _report(picture=None, defects=()):
    return {"job_id": "j1", "report_type": "NG" if defects else "OK", "generated_at": "2026-01-01T00:00:00+00:00",
            "part": {"part_number": "MS-4505-001"}, "inspection_summary": {"dimensional": "PASS", "defect_detection": "PASS"},
            "defects": list(defects), "measurements": [], "root_cause": None, "version": 1,
            "evidence_images": [{"path": str(picture), "caption": "Part picture"}] if picture else []}


@pytest.mark.asyncio
@pytest.mark.parametrize("defects", [(), ({"defect_type": "crack", "severity": "critical", "confidence": 0.9},)])
async def test_main_report_embeds_picture_in_pdf_docx_xlsx(tmp_path, monkeypatch, defects):
    import openpyxl
    import pdfplumber
    from docx import Document

    from app.reports import compose

    monkeypatch.setattr(compose, "REPORTS_DIR", tmp_path)
    uris = await compose.render_report(_report(_picture(tmp_path), defects))
    with pdfplumber.open(uris["pdf"]) as pdf:
        assert sum(len(p.images) for p in pdf.pages) == 1
    assert len(Document(uris["docx"]).inline_shapes) == 1
    assert len(openpyxl.load_workbook(uris["xlsx"])["Summary"]._images) == 1


@pytest.mark.asyncio
async def test_missing_picture_is_stated_not_silently_dropped(tmp_path, monkeypatch):
    import pdfplumber

    from app.reports import compose
    from app.reports.evidence import NO_PICTURE_TEXT

    monkeypatch.setattr(compose, "REPORTS_DIR", tmp_path)
    uris = await compose.render_report(_report(None))
    with pdfplumber.open(uris["pdf"]) as pdf:
        assert "No picture of the part" in " ".join(p.extract_text() for p in pdf.pages)
    docs = await render_rca_documents(_report(None), out_dir=tmp_path, stem="nopic")
    assert NO_PICTURE_TEXT in Path(docs["md"]).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_workflow_compose_report_attaches_picture(tmp_path, monkeypatch):
    import cv2

    from app.workflow.nodes import s7_report

    monkeypatch.chdir(tmp_path)
    frame = tmp_path / "frame.jpg"
    cv2.imwrite(str(frame), np.full((120, 160, 3), 150, np.uint8))
    for fast in (True, False):
        defects = [] if fast else [{"defect_type": "crack", "confidence": 0.9, "bbox": {"x1": 5, "y1": 5, "x2": 50, "y2": 50}}]
        state = {"job_id": f"w{fast}", "fast_path": fast, "defects": defects, "images": [{"uri": str(frame)}], "final_rca": {}}
        images = (await s7_report.compose_report(state))["report"]["evidence_images"]
        assert len(images) == 1 and Path(images[0]["path"]).is_file()
