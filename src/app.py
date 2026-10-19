"""
Flask-based AI-chat dashboard for sheet-metal defect detection.

Run with:
    python src/app.py
Then open http://localhost:5000
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request, send_from_directory

# Make sure sibling modules are importable when run as `python src/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from alert import send_esp32_alert, send_plc_fail_signal
from decision import decide
from detector import Detector

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEIGHTS = PROJECT_ROOT / "models" / "best.pt"
SAMPLES_DIR = PROJECT_ROOT / "samples"

DETECT_CONF_FLOOR = 0.10
MAX_VIDEO_FRAMES = 8

DEFECT_COLOR = (0, 0, 255)  # BGR red
BOX_THICKNESS = 2

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov"}

app = Flask(__name__, template_folder="templates", static_folder="static")

# Load detector once at startup
_detector: Detector | None = None


def get_detector() -> Detector:
    global _detector
    if _detector is None:
        _detector = Detector(str(DEFAULT_WEIGHTS))
    return _detector


# ---------------------------------------------------------------------------
# Helper: draw bounding boxes
# ---------------------------------------------------------------------------

def draw_detections(frame: np.ndarray, detections, confidence_threshold: float) -> np.ndarray:
    annotated = frame.copy()
    for det in detections:
        if det.confidence < confidence_threshold:
            continue
        x1, y1, x2, y2 = (int(v) for v in det.xyxy)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), DEFECT_COLOR, BOX_THICKNESS)
        label = f"{det.class_name} {det.confidence:.2f}"
        cv2.putText(
            annotated, label, (x1, max(0, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, DEFECT_COLOR, 1, cv2.LINE_AA,
        )
    return annotated


def frame_to_b64(frame: np.ndarray) -> str:
    """Convert a BGR OpenCV frame to a base64-encoded PNG data-URI."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    ok, buf = cv2.imencode(".jpg", rgb, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("Could not encode frame")
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


# ---------------------------------------------------------------------------
# Core analysis helpers
# ---------------------------------------------------------------------------

def analyze_image(detector: Detector, frame: np.ndarray, conf: float):
    detections = detector.detect(frame, conf_threshold=DETECT_CONF_FLOOR)
    verdict = decide(detections, confidence_threshold=conf)
    annotated = draw_detections(frame, detections, conf)
    return annotated, verdict


def analyze_video(detector: Detector, path: Path, conf: float, max_frames: int = MAX_VIDEO_FRAMES):
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    step = max(1, total // max_frames) if total else 1
    results = []
    idx = 0
    while len(results) < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            results.append(analyze_image(detector, frame, conf))
        idx += 1
    cap.release()
    return results


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    samples = []
    if SAMPLES_DIR.exists():
        samples = sorted(
            p.name for p in SAMPLES_DIR.glob("*")
            if p.suffix.lower() not in (".md",)
        )
    return render_template("index.html", samples=samples)


@app.route("/analyze", methods=["POST"])
def analyze():
    """
    Accepts multipart/form-data with:
      - file: uploaded file  OR  sample_name: name of bundled sample
      - confidence: float threshold (default 0.5)
      - esp32_url: optional alert URL
    Returns JSON with preview_b64, annotated_b64, verdict, counts, message.
    """
    conf = float(request.form.get("confidence", 0.5))
    esp32_url = request.form.get("esp32_url", "").strip()

    # Resolve file bytes + filename
    if "file" in request.files and request.files["file"].filename:
        f = request.files["file"]
        file_bytes = f.read()
        filename = f.filename
    elif request.form.get("sample_name"):
        name = request.form["sample_name"]
        sample_path = SAMPLES_DIR / name
        if not sample_path.exists():
            return jsonify(error=f"Sample '{name}' not found"), 404
        file_bytes = sample_path.read_bytes()
        filename = name
    else:
        return jsonify(error="No file or sample provided"), 400

    suffix = Path(filename).suffix.lower()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file_bytes)
    tmp.close()
    tmp_path = Path(tmp.name)

    try:
        detector = get_detector()

        if suffix in VIDEO_EXTS:
            cap = cv2.VideoCapture(str(tmp_path))
            ok, preview_frame = cap.read()
            cap.release()
            if not ok:
                return jsonify(error="Could not read any frames from that video."), 400

            frame_results = analyze_video(detector, tmp_path, conf)
            if not frame_results:
                return jsonify(error="Could not read any frames from that video."), 400

            overall_fail = any(not v.passed for _, v in frame_results)
            total_counts: Counter = Counter()
            for _, v in frame_results:
                total_counts.update(v.counts)

            display_frame = next(
                (a for a, v in frame_results if not v.passed),
                frame_results[0][0],
            )

            passed = not overall_fail
            n = len(frame_results)
            if passed:
                message = f"Scanned {n} sampled frames. No defects above threshold found."
            else:
                message = f"Scanned {n} sampled frames. Defect(s) detected."

            preview_b64 = frame_to_b64(preview_frame)
            annotated_b64 = frame_to_b64(display_frame)
            counts = dict(total_counts)

        elif suffix in IMAGE_EXTS:
            frame = cv2.imread(str(tmp_path))
            if frame is None:
                return jsonify(error="Could not read that image."), 400
            preview_b64 = frame_to_b64(frame)
            annotated_frame, verdict = analyze_image(detector, frame, conf)
            annotated_b64 = frame_to_b64(annotated_frame)
            passed = verdict.passed
            counts = verdict.counts
            message = "No defects above threshold." if passed else "Defects detected."
        else:
            return jsonify(error=f"Unsupported file type: {suffix}"), 400

        # Side effects
        if not passed:
            send_plc_fail_signal()
        if esp32_url:
            send_esp32_alert(esp32_url, state=not passed)

        return jsonify(
            preview_b64=preview_b64,
            annotated_b64=annotated_b64,
            passed=passed,
            counts=counts,
            message=message,
            filename=filename,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


@app.route("/samples/<path:filename>")
def serve_sample(filename):
    return send_from_directory(str(SAMPLES_DIR), filename)


if __name__ == "__main__":
    if not DEFAULT_WEIGHTS.exists():
        print(f"ERROR: No trained weights found at {DEFAULT_WEIGHTS}")
        print("Run scripts/train.py + evaluate.py first.")
        sys.exit(1)
    app.run(host="0.0.0.0", port=5000, debug=False)
