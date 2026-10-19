"""
Streamlit demo UI: pick a frame source, run YOLO detection on each frame,
show the annotated image, PASS/FAIL status, and running defect counts.

Run with:
    streamlit run src/app.py
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

import cv2
import streamlit as st

from alert import send_esp32_alert, send_plc_fail_signal
from decision import decide
from detector import Detector
from sources import Esp32Source, FileSource, WebcamSource

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEIGHTS = PROJECT_ROOT / "models" / "best.pt"
SAMPLES_DIR = PROJECT_ROOT / "samples"

# Detect at a low, fixed confidence so every candidate box is captured once;
# the user's slider threshold (applied in decision.decide) controls what
# actually counts as a defect, without needing to re-run the model.
DETECT_CONF_FLOOR = 0.10

DEFECT_COLOR = (0, 0, 255)  # BGR red
BOX_THICKNESS = 2


def draw_detections(frame, detections, confidence_threshold):
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


@st.cache_resource
def load_detector(weights_path: str) -> Detector:
    return Detector(weights_path)


def main():
    st.set_page_config(page_title="Sheet Metal Defect Detection", layout="wide")
    st.title("Sheet Metal Defect Detection — Demo")

    with st.sidebar:
        st.header("Settings")

        if not DEFAULT_WEIGHTS.exists():
            st.error(f"No trained weights found at {DEFAULT_WEIGHTS}. Run scripts/train.py + evaluate.py first.")
            st.stop()

        confidence_threshold = st.slider("Confidence threshold", 0.0, 1.0, 0.5, 0.05)

        source_options = ["Upload image/video", "Sample image/video", "Image/video file", "Webcam", "ESP32-CAM (Phase 3)"]
        source_kind = st.radio("Frame source", source_options)

        file_path = None
        esp32_url = None
        uploaded_file = None
        sample_choice = None
        if source_kind == "Upload image/video":
            uploaded_file = st.file_uploader(
                "Upload an image or video", type=["jpg", "jpeg", "png", "bmp", "mp4", "avi", "mov"]
            )
        elif source_kind == "Sample image/video":
            sample_files = sorted(p.name for p in SAMPLES_DIR.glob("*") if p.suffix.lower() != ".md")
            if not sample_files:
                st.warning(f"No samples found in {SAMPLES_DIR}. Run scripts/make_samples.py.")
            else:
                sample_choice = st.selectbox("Pick a bundled sample", sample_files)
                st.caption("Files prefixed `defect_` should FAIL; `clean_` are synthetic defect-free plates that should PASS.")
        elif source_kind == "Image/video file":
            file_path = st.text_input("Path to image, folder of images, or video file")
        elif source_kind == "ESP32-CAM (Phase 3)":
            esp32_url = st.text_input("ESP32-CAM base URL", placeholder="http://192.168.1.50")
            st.caption(
                "Requires Phase 3 hardware running this project's firmware. "
                "Not available until the ESP32-CAM is flashed and wired up."
            )

        esp32_alert_url = st.text_input(
            "ESP32-CAM alert URL (optional, for LED/buzzer)", placeholder="http://192.168.1.50"
        )

        st.caption(
            "Caveats: trained on NEU-DET (hot-rolled steel strip), not stamped sheet/brackets/gaskets. "
            "Metrics here were measured on NEU-DET's own test split and will not automatically "
            "transfer to ESP32-CAM images without separately testing on real captures."
        )

        run = st.button("Start / Restart")

    if not run:
        st.info("Configure a source in the sidebar and click **Start / Restart**.")
        return

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
    resolved_path = None  # set for FileSource-backed options, used to decide frame pacing below
    try:
        if source_kind == "Upload image/video":
            if uploaded_file is None:
                st.warning("Upload an image or video first.")
                return
            suffix = Path(uploaded_file.name).suffix
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(uploaded_file.getvalue())
            tmp.close()
            resolved_path = Path(tmp.name)
            source = FileSource(str(resolved_path))
        elif source_kind == "Sample image/video":
            if not sample_choice:
                st.warning("Pick a bundled sample first.")
                return
            resolved_path = SAMPLES_DIR / sample_choice
            source = FileSource(str(resolved_path))
        elif source_kind == "Image/video file":
            if not file_path:
                st.warning("Enter a file or folder path.")
                return
            resolved_path = Path(file_path)
            source = FileSource(file_path)
        elif source_kind == "Webcam":
            source = WebcamSource(0)
        else:
            if not esp32_url:
                st.warning("Enter the ESP32-CAM base URL.")
                return
            source = Esp32Source(f"{esp32_url.rstrip('/')}/stream")
    except Exception as exc:
        st.error(f"Could not open source: {exc}")
        return

    # Pace through anything with multiple frames (a folder, or a video file)
    # so the viewer can actually see each frame; a single still image needs none.
    paced = resolved_path is not None and (
        resolved_path.is_dir() or resolved_path.suffix.lower() not in IMAGE_EXTS
    )

    detector = load_detector(str(DEFAULT_WEIGHTS))

    frame_slot = st.empty()
    status_slot = st.empty()
    counts_slot = st.empty()
    end_slot = st.empty()

    last_alert_state = None
    try:
        while True:
            frame = source.read()
            if frame is None:
                end_slot.info("Source exhausted (end of file/folder, or stream dropped). Status above is the last frame's result.")
                break

            detections = detector.detect(frame, conf_threshold=DETECT_CONF_FLOOR)
            verdict = decide(detections, confidence_threshold=confidence_threshold)
            annotated = draw_detections(frame, detections, confidence_threshold)

            frame_slot.image(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB), channels="RGB")

            if verdict.passed:
                status_slot.success("PASS - no defects above threshold")
            else:
                status_slot.error(f"FAIL - defects detected: {verdict.counts}")
                send_plc_fail_signal()

            counts_slot.write(verdict.counts)

            if esp32_alert_url and verdict.passed != (last_alert_state is None or last_alert_state):
                send_esp32_alert(esp32_alert_url, state=not verdict.passed)
                last_alert_state = verdict.passed

            if paced:
                time.sleep(0.5)  # slow down so a folder or video is actually watchable
    finally:
        source.release()


if __name__ == "__main__":
    main()
