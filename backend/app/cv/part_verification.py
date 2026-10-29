"""Geometric comparison of a camera image with a part's raster CAD reference."""
from __future__ import annotations

import cv2
import numpy as np


def compare_part_images(
    captured: np.ndarray,
    reference: np.ndarray,
    threshold: float = 0.55,
) -> dict:
    """Compare two images using ORB correspondences and a RANSAC homography."""
    captured_gray = _prepare(captured)
    reference_gray = _prepare(reference)

    methods = [
        (cv2.SIFT_create(nfeatures=3000), cv2.NORM_L2),
        (cv2.ORB_create(nfeatures=2500, scaleFactor=1.2, nlevels=8), cv2.NORM_HAMMING),
    ]
    candidates = []
    matched_features = 0
    for detector, norm in methods:
        captured_points, captured_descriptors = detector.detectAndCompute(
            captured_gray, None
        )
        reference_points, reference_descriptors = detector.detectAndCompute(
            reference_gray, None
        )
        if captured_descriptors is None or reference_descriptors is None:
            continue

        matcher = cv2.BFMatcher(norm)
        pairs = matcher.knnMatch(reference_descriptors, captured_descriptors, k=2)
        good = [
            first
            for pair in pairs
            if len(pair) == 2
            for first, second in [pair]
            if first.distance < 0.75 * second.distance
        ]
        matched_features = max(matched_features, len(good))
        if len(good) < 6:
            continue

        source_points = np.float32(
            [reference_points[match.queryIdx].pt for match in good]
        ).reshape(-1, 1, 2)
        target_points = np.float32(
            [captured_points[match.trainIdx].pt for match in good]
        ).reshape(-1, 1, 2)
        homography, inlier_mask = cv2.findHomography(
            source_points, target_points, cv2.RANSAC, 5.0
        )
        if homography is None or inlier_mask is None:
            continue

        inliers = int(inlier_mask.sum())
        inlier_ratio = inliers / len(good)
        feature_coverage = min(1.0, inliers / 20.0)
        feature_score = 0.65 * inlier_ratio + 0.35 * feature_coverage
        candidates.append(
            (feature_score, homography, inliers, len(good), inlier_ratio)
        )

    if not candidates:
        if matched_features == 0:
            return _manual_result(
                threshold, "Not enough visual detail to compare the images."
            )
        return _manual_result(
            threshold,
            "The images could not be aligned reliably; manual verification is required.",
            feature_matches=matched_features,
        )

    feature_score, homography, inliers, match_count, inlier_ratio = max(
        candidates, key=lambda candidate: candidate[0]
    )

    height, width = captured_gray.shape
    aligned_reference = cv2.warpPerspective(
        reference_gray, homography, (width, height)
    )
    captured_edges = cv2.Canny(captured_gray, 60, 160) > 0
    reference_edges = cv2.Canny(aligned_reference, 60, 160) > 0
    captured_distance = cv2.distanceTransform(
        (~captured_edges).astype(np.uint8), cv2.DIST_L2, 3
    )
    reference_distance = cv2.distanceTransform(
        (~reference_edges).astype(np.uint8), cv2.DIST_L2, 3
    )
    captured_edge_count = int(captured_edges.sum())
    reference_edge_count = int(reference_edges.sum())
    captured_coverage = (
        float((captured_edges & (reference_distance <= 3)).sum() / captured_edge_count)
        if captured_edge_count
        else 0.0
    )
    reference_coverage = (
        float((reference_edges & (captured_distance <= 3)).sum() / reference_edge_count)
        if reference_edge_count
        else 0.0
    )
    edge_overlap = (captured_coverage + reference_coverage) / 2
    score = float(np.clip(0.8 * feature_score + 0.2 * edge_overlap, 0.0, 1.0))

    if score >= threshold:
        status = "Match"
        differences = ["No major geometric difference detected."]
    elif score < threshold * 0.6:
        status = "Mismatch"
        differences = [
            "The part's visual geometry differs from the selected CAD reference."
        ]
    else:
        status = "Needs Manual Inspection"
        differences = [
            "The visual match is inconclusive; inspect shape and edge alignment manually."
        ]

    captured_contours = _contour_count(captured_edges.astype(np.uint8) * 255)
    reference_contours = _contour_count(reference_edges.astype(np.uint8) * 255)
    if abs(captured_contours - reference_contours) > 3:
        differences.append(
            "Visible contour count differs "
            f"(captured {captured_contours}, reference {reference_contours})."
        )

    return {
        "status": status,
        "score": round(score, 4),
        "threshold": threshold,
        "feature_matches": match_count,
        "geometric_inliers": inliers,
        "edge_overlap": round(edge_overlap, 4),
        "captured_contours": captured_contours,
        "reference_contours": reference_contours,
        "differences": differences,
    }


def _prepare(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        raise ValueError("Image is empty or could not be decoded.")
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 2:
        gray = image
    else:
        raise ValueError("Image must have one or three channels.")
    height, width = gray.shape
    scale = min(1.0, 1400 / max(height, width))
    if scale < 1:
        gray = cv2.resize(
            gray, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
        )
    normalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    height, width = normalized.shape
    border = np.concatenate(
        (normalized[0, :], normalized[-1, :], normalized[:, 0], normalized[:, -1])
    )
    background = np.uint8(np.median(border))
    foreground_delta = cv2.absdiff(normalized, np.full_like(normalized, background))
    otsu_threshold, _ = cv2.threshold(
        foreground_delta, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
    )
    foreground = foreground_delta > max(12, otsu_threshold)
    y_coords, x_coords = np.where(foreground)
    if len(x_coords) and len(y_coords):
        x_min, x_max = int(x_coords.min()), int(x_coords.max())
        y_min, y_max = int(y_coords.min()), int(y_coords.max())
        if (x_max - x_min) < width * 0.95 and (y_max - y_min) < height * 0.95:
            margin = max(4, round(min(width, height) * 0.04))
            normalized = normalized[
                max(0, y_min - margin) : min(height, y_max + margin + 1),
                max(0, x_min - margin) : min(width, x_max + margin + 1),
            ]
    return normalized


def _contour_count(edges: np.ndarray) -> int:
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    return sum(1 for contour in contours if cv2.arcLength(contour, False) >= 20)


def _manual_result(threshold: float, message: str, **metrics: int) -> dict:
    return {
        "status": "Needs Manual Inspection",
        "score": 0.0,
        "threshold": threshold,
        "feature_matches": metrics.get("feature_matches", 0),
        "geometric_inliers": 0,
        "edge_overlap": 0.0,
        "captured_contours": 0,
        "reference_contours": 0,
        "differences": [message],
    }
