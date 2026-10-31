import cv2
import numpy as np

from app.cv.features import analyze_image_geometry
from app.core import storage


def test_geometry_detection_returns_image_space_contour_and_hole_candidates(tmp_path):
    image = np.full((400, 600, 3), 225, dtype=np.uint8)
    outline = np.array(
        [[105, 100], [450, 80], [500, 130], [480, 300], [430, 335], [130, 310], [85, 250]],
        dtype=np.int32,
    )
    cv2.fillPoly(image, [outline], (105, 105, 105))
    for center in ((190, 180), (355, 220)):
        cv2.circle(image, center, 18, (225, 225, 225), -1)
        cv2.circle(image, center, 22, (25, 25, 25), 3)

    image_path = tmp_path / "component.png"
    assert cv2.imwrite(str(image_path), image)

    result = analyze_image_geometry(str(image_path))

    assert result["status"] in {"detected", "uncertain"}
    assert result["dimensions_px"]["calibrated_mm"] is False
    annotations = result["annotations"]
    outer = next(annotation for annotation in annotations if annotation["feature_id"] == "OUTER")
    holes = [annotation for annotation in annotations if annotation["kind"] == "circle"]
    assert outer["kind"] == "polygon"
    assert len(outer["points"]) >= 5
    assert holes
    assert all(annotation["diameter_px"] > 0 for annotation in holes)
    assert any(annotation["kind"] == "line" for annotation in annotations)


def test_geometry_detection_does_not_claim_a_blank_frame_has_a_contour(tmp_path):
    image_path = tmp_path / "blank.png"
    assert cv2.imwrite(str(image_path), np.full((240, 320, 3), 128, dtype=np.uint8))

    result = analyze_image_geometry(str(image_path))

    assert result["status"] == "unavailable"
    assert not result.get("annotations")


def test_capture_path_is_limited_to_configured_image_storage(tmp_path, monkeypatch):
    allowed_root = tmp_path / "captures"
    allowed_root.mkdir()
    allowed_image = allowed_root / "capture.png"
    allowed_image.write_bytes(b"image")
    outside_image = tmp_path / "private.txt"
    outside_image.write_text("not an inspection image")
    config = type(
        "Config",
        (),
        {
            "project_root": tmp_path,
            "get": lambda self, *keys, default=None: "captures" if keys == ("camera", "folder_path") else default,
        },
    )()
    monkeypatch.setattr(storage, "get_config", lambda: config)

    assert storage.resolve_capture_path(str(allowed_image)) == allowed_image.resolve()
    assert storage.resolve_capture_path(str(outside_image)) is None
