"""Unit tests for defect detection logic."""
import pytest
from app.cv.detectors.fuse import fuse_detections, classify_and_measure_basic


def test_fuse_no_overlap():
    dets = [
        {"defect_type": "scratch", "confidence": 0.9,
         "bbox": {"x1": 0, "y1": 0, "x2": 100, "y2": 100}, "source": "yolo"},
        {"defect_type": "dent", "confidence": 0.8,
         "bbox": {"x1": 200, "y1": 200, "x2": 300, "y2": 300}, "source": "yolo"},
    ]
    result = fuse_detections(dets)
    assert len(result) == 2


def test_fuse_deduplicates_overlap():
    dets = [
        {"defect_type": "crack", "confidence": 0.9,
         "bbox": {"x1": 0, "y1": 0, "x2": 100, "y2": 100}, "source": "yolo"},
        {"defect_type": "crack", "confidence": 0.7,
         "bbox": {"x1": 10, "y1": 10, "x2": 110, "y2": 110}, "source": "yolo"},
    ]
    result = fuse_detections(dets)
    # Should keep only 1 (NMS suppressed the lower confidence duplicate)
    assert len(result) == 1


def test_classify_severity():
    dets = [
        {"defect_type": "crack", "confidence": 0.9, "size_px": 1000, "source": "yolo"},
        {"defect_type": "scratch", "confidence": 0.8, "size_px": 500, "source": "yolo"},
    ]
    severity_rules = {"crack": "critical", "scratch": "minor"}
    result, min_conf = classify_and_measure_basic(dets, {"px_per_mm": 10.0}, severity_rules)
    severities = {d["defect_type"]: d["severity"] for d in result}
    assert severities["crack"] == "critical"
    assert severities["scratch"] == "minor"
    assert min_conf == pytest.approx(0.8, abs=0.01)


@pytest.mark.asyncio
async def test_mock_detector_returns_four_defect_types():
    """Mock detector returns exactly the infographic scenario."""
    from app.cv.detectors.mock import MockDetector

    detector = MockDetector()
    detections = await detector.detect([])
    types = {d["defect_type"] for d in detections}
    assert "scratch" in types
    assert "dent" in types
    assert "crack" in types
    assert "deformation" in types
