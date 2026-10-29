"""Unit tests for measurement comparison logic."""
import pytest
from app.cv.measure import compare_with_drawing


def test_compare_all_pass():
    measurements = [
        {"feature_id": "L1", "nominal": 120.0, "measured": 120.05, "deviation": 0.05,
         "tol_plus": 0.10, "tol_minus": 0.10},
    ]
    result = compare_with_drawing(measurements, {})
    assert result[0]["within_tolerance"] is True


def test_compare_fail_on_out_of_tolerance():
    measurements = [
        {"feature_id": "H1", "nominal": 12.0, "measured": 11.70, "deviation": -0.30,
         "tol_plus": 0.05, "tol_minus": 0.05},
    ]
    result = compare_with_drawing(measurements, {})
    assert result[0]["within_tolerance"] is False


def test_compare_infographic_scenario(sample_measurements):
    # From spec: L1(+0.05) OK, L2(+0.02) OK, H1(-0.30) OUT, L3(+0.01) OK
    result = compare_with_drawing(sample_measurements, {})
    status_map = {m["feature_id"]: m["within_tolerance"] for m in result}
    assert status_map["L1"] is True
    assert status_map["L2"] is True
    assert status_map["H1"] is False
    assert status_map["L3"] is True
