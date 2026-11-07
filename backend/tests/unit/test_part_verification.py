import cv2
import numpy as np
import pytest

from app.cv.part_verification import compare_part_images


def _drawing() -> np.ndarray:
    image = np.full((600, 600, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (100, 130), (510, 490), (0, 0, 0), 5)
    cv2.circle(image, (165, 195), 20, (0, 0, 0), 4)
    cv2.circle(image, (440, 200), 32, (0, 0, 0), 4)
    cv2.circle(image, (220, 410), 14, (0, 0, 0), 4)
    cv2.rectangle(image, (345, 330), (400, 370), (0, 0, 0), -1)
    cv2.line(image, (300, 130), (300, 230), (0, 0, 0), 3)
    return image


def test_identical_cad_and_capture_match():
    image = _drawing()

    result = compare_part_images(image, image, threshold=0.55)

    assert result["status"] == "Match"
    assert result["score"] >= result["threshold"]
    assert result["geometric_inliers"] >= 6
    assert result["alignment_status"] == "aligned"
    assert result["feature_match_percent"] > 0
    assert result["visualizations"]["aligned_overlay"].startswith("data:image/jpeg;base64,")
    assert result["visualizations"]["difference_image"].startswith("data:image/png;base64,")
    assert result["visualizations"]["difference_heatmap"].startswith("data:image/png;base64,")
    assert result["visualizations"]["matched_features"].startswith("data:image/jpeg;base64,")
    assert "edge_overlap" in result


def test_unalignable_images_do_not_report_a_fake_zero_similarity():
    reference = _drawing()
    unrelated = np.full((600, 600, 3), 255, dtype=np.uint8)

    result = compare_part_images(unrelated, reference, threshold=0.55)

    assert result["alignment_status"] == "required"
    assert result["score"] is None
    assert result["feature_match_percent"] is None
    assert result["edge_overlap"] is None
    assert result["visualizations"] == {}


def test_rotated_and_resized_part_is_geometrically_aligned():
    reference = _drawing()
    transform = cv2.getRotationMatrix2D((300, 300), 12, 0.85)
    captured = cv2.warpAffine(reference, transform, (600, 600), borderValue=(255, 255, 255))

    result = compare_part_images(captured, reference, threshold=0.55)

    assert result["status"] == "Match"
    assert result["geometric_inliers"] >= 6


def test_part_with_geometric_deviation_still_returns_measured_comparison():
    reference = _drawing()
    captured = reference.copy()
    cv2.line(captured, (140, 330), (260, 330), (0, 0, 0), 8)

    result = compare_part_images(captured, reference, threshold=0.55)

    assert result["alignment_status"] == "aligned"
    assert isinstance(result["score"], float)
    assert 0 <= result["score"] <= 1
    assert result["visualizations"]["difference_heatmap"].startswith("data:image/png;base64,")


@pytest.mark.parametrize(
    "captured, reference",
    [
        (None, _drawing()),
        (np.array([], dtype=np.uint8), _drawing()),
        (np.zeros((10, 10, 4), dtype=np.uint8), _drawing()),
    ],
)
def test_invalid_image_inputs_raise_instead_of_returning_zero(captured, reference):
    with pytest.raises(ValueError):
        compare_part_images(captured, reference)


def test_unrelated_image_never_passes_verification():
    reference = _drawing()
    unrelated = np.full((600, 600, 3), 255, dtype=np.uint8)
    cv2.putText(unrelated, "OTHER PART", (40, 320), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 6)

    result = compare_part_images(unrelated, reference, threshold=0.55)

    assert result["status"] != "Match"


@pytest.mark.asyncio
async def test_workflow_uses_the_verified_capture_instead_of_mock_camera(tmp_path):
    from app.workflow.nodes.s1_capture import capture_images

    capture = tmp_path / "verified.jpg"
    assert cv2.imwrite(str(capture), _drawing())

    result = await capture_images(
        {"job_id": "job-1", "image_uris": [str(capture)], "camera_recipe": {"angles": ["top"]}}
    )

    assert result["images"] == [
        {
            "uri": str(capture),
            "angle": "top",
            "kind": "raw",
            "quality_score": None,
            "meta": {"source": "verified_camera_capture"},
        }
    ]
