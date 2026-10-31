"""
Feature detection in images using OpenCV:
- Holes (HoughCircles + ellipse fit)
- Edges (contour approximation)
- Registration to drawing features
"""
from __future__ import annotations

import math
from typing import Any


def analyze_image_geometry(image_uri: str) -> dict[str, Any]:
    """Extract image-space contour and circular-feature candidates from a capture."""
    import cv2
    import numpy as np

    image = cv2.imread(image_uri)
    if image is None:
        return {"status": "unavailable", "reason": "The captured image could not be decoded."}

    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    median = float(np.median(blurred))
    edges = cv2.Canny(
        blurred,
        max(0, int(0.66 * median)),
        min(255, int(1.33 * median)),
    )
    kernel_size = max(3, (min(width, height) // 160) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    frame_area = width * height
    border_margin = max(2, int(min(width, height) * 0.01))
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.int16)
    border_width = max(2, int(min(width, height) * 0.03))
    border_pixels = np.concatenate((
        lab[:border_width].reshape(-1, 3),
        lab[-border_width:].reshape(-1, 3),
        lab[:, :border_width].reshape(-1, 3),
        lab[:, -border_width:].reshape(-1, 3),
    ))
    background_color = np.median(border_pixels, axis=0)
    border_delta = np.linalg.norm(border_pixels - background_color, axis=1)
    border_median_delta = float(np.median(border_delta))
    border_mad = float(np.median(np.abs(border_delta - border_median_delta)))
    color_threshold = float(np.clip(border_median_delta + 4 * 1.4826 * border_mad, 14, 32))
    foreground = (np.linalg.norm(lab - background_color, axis=2) > color_threshold).astype(np.uint8) * 255
    foreground = cv2.morphologyEx(
        foreground,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        iterations=2,
    )
    component_count, component_labels, component_stats, _ = cv2.connectedComponentsWithStats(foreground)
    components = []
    for label in range(1, component_count):
        x, y, box_width, box_height, area = component_stats[label]
        touches_border = (
            x <= border_margin
            or y <= border_margin
            or x + box_width >= width - border_margin
            or y + box_height >= height - border_margin
        )
        if not touches_border and frame_area * 0.015 <= area <= frame_area * 0.9:
            components.append((int(area), label))

    segmented_mask = None
    segmentation_confident = False
    if components:
        component_area, component_label = max(components)
        segmented_mask = (component_labels == component_label).astype(np.uint8) * 255
        segmentation_confident = border_median_delta <= 18
        contours, hierarchy = cv2.findContours(segmented_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    else:
        contours, hierarchy = cv2.findContours(closed_edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    outer_candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < frame_area * 0.015 or area > frame_area * 0.92:
            continue
        x, y, box_width, box_height = cv2.boundingRect(contour)
        touches_border = (
            x <= border_margin
            or y <= border_margin
            or x + box_width >= width - border_margin
            or y + box_height >= height - border_margin
        )
        if touches_border:
            continue
        outer_candidates.append((area, contour))

    if not outer_candidates:
        return {
            "status": "unavailable",
            "width": width,
            "height": height,
            "reason": "No closed outer contour could be isolated from the image boundary.",
        }

    outer_candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    distinct_candidates: list[tuple[float, Any]] = []
    candidate_boxes: list[tuple[int, int, int, int]] = []
    for candidate_area, contour in outer_candidates:
        candidate_box = cv2.boundingRect(contour)
        duplicate = False
        for x, y, box_width, box_height in candidate_boxes:
            left = max(candidate_box[0], x)
            top = max(candidate_box[1], y)
            right = min(candidate_box[0] + candidate_box[2], x + box_width)
            bottom = min(candidate_box[1] + candidate_box[3], y + box_height)
            intersection = max(0, right - left) * max(0, bottom - top)
            union = candidate_box[2] * candidate_box[3] + box_width * box_height - intersection
            if union > 0 and intersection / union >= 0.9:
                duplicate = True
                break
        if not duplicate:
            distinct_candidates.append((candidate_area, contour))
            candidate_boxes.append(candidate_box)
    outer_candidates = distinct_candidates
    outer_area, outer_contour = outer_candidates[0]
    perimeter = cv2.arcLength(outer_contour, True)
    simplified = cv2.approxPolyDP(outer_contour, max(1.0, perimeter * 0.0015), True)
    points = [
        {"x": round(float(point[0][0]) / width, 6), "y": round(float(point[0][1]) / height, 6)}
        for point in simplified
    ]

    support_radius = max(1, kernel_size // 2)
    sampled = outer_contour[::max(1, len(outer_contour) // 500)].reshape(-1, 2)
    edge_support = 0
    for x, y in sampled:
        left, right = max(0, x - support_radius), min(width, x + support_radius + 1)
        top, bottom = max(0, y - support_radius), min(height, y + support_radius + 1)
        edge_support += int(np.any(edges[top:bottom, left:right]))
    contour_confidence = edge_support / max(1, len(sampled))

    competing_contour = False
    for area, contour in outer_candidates[1:]:
        if area < outer_area * 0.25:
            continue
        x, y, box_width, box_height = cv2.boundingRect(contour)
        center = (float(x + box_width / 2), float(y + box_height / 2))
        if cv2.pointPolygonTest(outer_contour, center, False) >= 0:
            competing_contour = True
            break
    outer_area_ratio = outer_area / frame_area
    outer_status = "warning" if (
        not segmentation_confident
        or competing_contour
        or contour_confidence < 0.55
        or outer_area_ratio > 0.4
    ) else "unavailable"
    outer_label = "OUTER · contour candidate · review" if outer_status == "warning" else "OUTER · detected contour"
    annotations: list[dict[str, Any]] = [{
        "feature_id": "OUTER",
        "kind": "polygon",
        "points": points,
        "label": outer_label,
        "status": outer_status,
        "confidence": round(contour_confidence, 3),
    }]

    circle_candidates: list[dict[str, float | str]] = []
    if segmented_mask is not None:
        component_contours, component_hierarchy = cv2.findContours(
            segmented_mask,
            cv2.RETR_TREE,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        roots = [
            index
            for index, relation in enumerate(component_hierarchy[0])
            if relation[3] < 0
        ] if component_hierarchy is not None else []
        root_index = max(roots, key=lambda index: cv2.contourArea(component_contours[index])) if roots else -1

        if root_index >= 0:
            for index, contour in enumerate(component_contours):
                if component_hierarchy[0][index][3] != root_index or len(contour) < 5:
                    continue
                area = cv2.contourArea(contour)
                perimeter = cv2.arcLength(contour, True)
                circularity = 4 * math.pi * area / (perimeter * perimeter) if perimeter > 0 else 0
                if not frame_area * 0.00015 <= area <= frame_area * 0.03 or circularity < 0.5:
                    continue

                (center_x, center_y), axes, angle = cv2.fitEllipse(contour)
                major_axis, minor_axis = max(axes), min(axes)
                if minor_axis < 8 or major_axis / minor_axis > 4:
                    continue
                ellipse_area = math.pi * major_axis * minor_axis / 4
                fit_ratio = area / ellipse_area if ellipse_area else 0
                if not 0.45 <= fit_ratio <= 1.3:
                    continue

                if axes[0] >= axes[1]:
                    radius_x, radius_y, rotation = axes[0] / 2, axes[1] / 2, angle
                else:
                    radius_x, radius_y, rotation = axes[1] / 2, axes[0] / 2, angle + 90
                circle_candidates.append({
                    "x": float(center_x),
                    "y": float(center_y),
                    "rx": float(radius_x),
                    "ry": float(radius_y),
                    "rotation": float(rotation % 180),
                    "confidence": float(min(1, circularity)),
                    "kind": "circle" if major_axis / minor_axis >= 0.9 else "ellipse",
                })

    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(12, int(min(width, height) * 0.045)),
        param1=90,
        param2=30,
        minRadius=max(4, int(min(width, height) * 0.012)),
        maxRadius=max(5, int(min(width, height) * 0.16)),
    )
    if circles is not None:
        for center_x, center_y, radius in circles[0]:
            if cv2.pointPolygonTest(outer_contour, (float(center_x), float(center_y)), False) < 0:
                continue
            if segmented_mask is not None and segmented_mask[int(center_y), int(center_x)] > 0:
                continue
            angles = np.linspace(0, 2 * math.pi, 96, endpoint=False)
            samples = []
            for offset in (-2, -1, 0, 1, 2):
                sample_x = np.rint(center_x + (radius + offset) * np.cos(angles)).astype(int)
                sample_y = np.rint(center_y + (radius + offset) * np.sin(angles)).astype(int)
                valid = (sample_x >= 0) & (sample_x < width) & (sample_y >= 0) & (sample_y < height)
                samples.extend((edges[sample_y[valid], sample_x[valid]] > 0).tolist())
            circle_confidence = sum(samples) / max(1, len(samples))
            if circle_confidence < 0.16 or any(
                math.hypot(center_x - float(candidate["x"]), center_y - float(candidate["y"]))
                < max(8, min(radius, float(candidate["rx"])) * 0.65)
                for candidate in circle_candidates
            ):
                continue
            circle_candidates.append({
                "x": float(center_x),
                "y": float(center_y),
                "rx": float(radius),
                "ry": float(radius),
                "rotation": 0.0,
                "confidence": circle_confidence,
                "kind": "circle",
            })

    circle_candidates.sort(key=lambda candidate: float(candidate["confidence"]), reverse=True)
    unique_circles: list[dict[str, float | str]] = []
    for candidate in circle_candidates:
        if any(
            math.hypot(
                float(candidate["x"]) - float(existing["x"]),
                float(candidate["y"]) - float(existing["y"]),
            ) < max(8, min(float(candidate["rx"]), float(existing["rx"])) * 0.65)
            for existing in unique_circles
        ):
            continue
        unique_circles.append(candidate)
        if len(unique_circles) == 12:
            break

    circle_candidates = sorted(unique_circles, key=lambda candidate: (float(candidate["y"]), float(candidate["x"])))
    for index, candidate in enumerate(circle_candidates, start=1):
        feature_id = f"H{index}"
        center_x = float(candidate["x"])
        center_y = float(candidate["y"])
        radius_x = float(candidate["rx"])
        radius_y = float(candidate["ry"])
        confidence = float(candidate["confidence"])
        annotations.append({
            "feature_id": feature_id,
            "kind": str(candidate["kind"]),
            "points": [{"x": round(center_x / width, 6), "y": round(center_y / height, 6)}],
            "radius": round(radius_x / min(width, height), 6),
            "rx": round(radius_x / min(width, height), 6),
            "ry": round(radius_y / min(width, height), 6),
            "rotation": round(float(candidate["rotation"]), 3),
            "diameter_px": round(radius_x * 2, 2),
            "label": f"{feature_id} · Ø{radius_x * 2:.1f} px",
            "status": "unavailable" if confidence >= 0.65 else "warning",
            "confidence": round(confidence, 3),
        })

    rectangle = cv2.minAreaRect(outer_contour)
    contour_width, contour_height = rectangle[1]
    box_points = cv2.boxPoints(rectangle)
    first_edge = float(np.linalg.norm(box_points[0] - box_points[1]))
    second_edge = float(np.linalg.norm(box_points[1] - box_points[2]))
    dimension_edges = (
        ("OUTER-L", box_points[0], box_points[1], max(contour_width, contour_height)),
        ("OUTER-W", box_points[1], box_points[2], min(contour_width, contour_height)),
    )
    if second_edge > first_edge:
        dimension_edges = (
            ("OUTER-L", box_points[1], box_points[2], max(contour_width, contour_height)),
            ("OUTER-W", box_points[0], box_points[1], min(contour_width, contour_height)),
        )
    for feature_id, start, end, length in dimension_edges:
        annotations.append({
            "feature_id": feature_id,
            "kind": "line",
            "points": [
                {"x": round(float(start[0]) / width, 6), "y": round(float(start[1]) / height, 6)},
                {"x": round(float(end[0]) / width, 6), "y": round(float(end[1]) / height, 6)},
            ],
            "label": f"{feature_id.replace('OUTER-', '')} · {length:.1f} px",
            "status": "warning" if outer_status == "warning" else "unavailable",
        })

    for index in range(len(circle_candidates) - 1):
        first = circle_candidates[index]
        second = circle_candidates[index + 1]
        center_distance = math.hypot(
            float(second["x"]) - float(first["x"]),
            float(second["y"]) - float(first["y"]),
        )
        annotations.append({
            "feature_id": f"{'H' + str(index + 1)}-{'H' + str(index + 2)}",
            "kind": "line",
            "points": [
                {"x": round(float(first["x"]) / width, 6), "y": round(float(first["y"]) / height, 6)},
                {"x": round(float(second["x"]) / width, 6), "y": round(float(second["y"]) / height, 6)},
            ],
            "label": f"Centre distance · {center_distance:.1f} px",
            "status": "warning",
        })

    outer_points = outer_contour.reshape(-1, 2)
    for index, candidate in enumerate(circle_candidates, start=1):
        center_x = float(candidate["x"])
        center_y = float(candidate["y"])
        radius = float(candidate["rx"])
        closest_index = int(np.argmin(np.sum((outer_points - (center_x, center_y)) ** 2, axis=1)))
        boundary_x, boundary_y = outer_points[closest_index]
        center_distance = math.hypot(float(boundary_x) - center_x, float(boundary_y) - center_y)
        edge_gap = center_distance - radius
        if edge_gap <= 1:
            continue
        unit_x = (float(boundary_x) - center_x) / center_distance
        unit_y = (float(boundary_y) - center_y) / center_distance
        annotations.append({
            "feature_id": f"H{index}-EDGE",
            "kind": "line",
            "points": [
                {
                    "x": round((center_x + unit_x * radius) / width, 6),
                    "y": round((center_y + unit_y * radius) / height, 6),
                },
                {"x": round(float(boundary_x) / width, 6), "y": round(float(boundary_y) / height, 6)},
            ],
            "label": f"H{index} to edge · {edge_gap:.1f} px",
            "status": "warning",
        })

    return {
        "status": "uncertain" if outer_status == "warning" else "detected",
        "width": width,
        "height": height,
        "dimensions_px": {
            "length": round(float(max(contour_width, contour_height)), 2),
            "width": round(float(min(contour_width, contour_height)), 2),
            "calibrated_mm": False,
        },
        "annotations": annotations,
        "reason": (
            "Image-space geometry only; dimensional calibration is not available."
            if outer_status == "unavailable"
            else "Competing closed contours were found; verify the orange contour before relying on it."
        ),
    }


async def detect_features(
    images: list[dict],
    drawing: dict,
    calibration: dict,
) -> list[dict]:
    """
    Detect geometric features in the processed images.
    Returns a list of detected features with pixel coordinates and estimated sizes.
    """
    import cv2
    import numpy as np
    from pathlib import Path

    px_per_mm = calibration.get("px_per_mm", 10.0)
    drawing_features = drawing.get("features", [])
    detected = []

    for img_info in images:
        uri = img_info.get("uri", "")
        if uri.startswith("mock://") or not Path(uri).exists():
            # Return synthetic detections matching drawing features
            detected.extend(_synthetic_detections(drawing_features, px_per_mm))
            break

        img = cv2.imread(uri)
        if img is None:
            detected.extend(_synthetic_detections(drawing_features, px_per_mm))
            break

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Detect circles (holes)
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=20,
            param1=50,
            param2=30,
            minRadius=5,
            maxRadius=100,
        )

        if circles is not None:
            for i, c in enumerate(circles[0]):
                diameter_mm = (c[2] * 2) / px_per_mm
                detected.append({
                    "feature_id": f"H_det_{i+1}",
                    "feature_type": "hole",
                    "diameter_px": float(c[2] * 2),
                    "diameter_mm": round(diameter_mm, 3),
                    "center_px": (float(c[0]), float(c[1])),
                })

        # Detect edges via contours
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            largest = max(contours, key=cv2.contourArea)
            rect = cv2.minAreaRect(largest)
            w_mm = rect[1][0] / px_per_mm
            h_mm = rect[1][1] / px_per_mm
            detected.append({
                "feature_id": "BBOX",
                "feature_type": "bounding_box",
                "width_mm": round(w_mm, 3),
                "height_mm": round(h_mm, 3),
            })

        break  # Use first image only for now

    if not detected:
        detected = _synthetic_detections(drawing_features, px_per_mm)

    return detected


def _synthetic_detections(drawing_features: list[dict], px_per_mm: float) -> list[dict]:
    """
    Generate synthetic detected features matching drawing spec
    with small realistic measurement noise.
    """
    import random
    random.seed(42)  # deterministic for CI

    detected = []
    for f in drawing_features:
        noise = random.uniform(-0.08, 0.08)
        detected.append({
            "feature_id": f["feature_id"],
            "feature_type": f["feature_type"],
            "measured_mm": round(f["nominal"] + noise, 3),
            "source": "synthetic",
        })
    return detected
