"""
Chat-style Streamlit dashboard: attach a sheet-metal image or short video in
the chat box (like an AI chat app's file attachment), and a reply bubble
shows the annotated frame, PASS/FAIL verdict, and defect counts. Live camera
feeds (webcam / ESP32-CAM) don't fit a turn-based chat, so they live in a
collapsed sidebar section instead.

Run with:
    streamlit run src/app.py
"""
from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path

import cv2
import streamlit as st

from alert import send_esp32_alert, send_plc_fail_signal
from decision import decide
from detector import Detector
from sources import Esp32Source, WebcamSource

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEIGHTS = PROJECT_ROOT / "models" / "best.pt"
SAMPLES_DIR = PROJECT_ROOT / "samples"

# Detect at a low, fixed confidence so every candidate box is captured once;
# the user's slider threshold (applied in decision.decide) controls what
# actually counts as a defect, without needing to re-run the model.
DETECT_CONF_FLOOR = 0.10
MAX_VIDEO_FRAMES = 8  # cap how many frames of an uploaded video we sample

DEFECT_COLOR = (0, 0, 255)  # BGR red
BOX_THICKNESS = 2

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov"}


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


def analyze_image(detector, frame, confidence_threshold):
    detections = detector.detect(frame, conf_threshold=DETECT_CONF_FLOOR)
    verdict = decide(detections, confidence_threshold=confidence_threshold)
    annotated = draw_detections(frame, detections, confidence_threshold)
    return annotated, verdict


def analyze_video(detector, path: Path, confidence_threshold, max_frames=MAX_VIDEO_FRAMES):
    """Samples up to max_frames evenly-spaced frames and analyzes each."""
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
            results.append(analyze_image(detector, frame, confidence_threshold))
        idx += 1
    cap.release()
    return results


def handle_attachment(detector, file_bytes: bytes, file_name: str, confidence_threshold, esp32_alert_url):
    """Runs detection on one uploaded/sample file, returns (user_preview, reply_text, reply_image)."""
    suffix = Path(file_name).suffix.lower()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file_bytes)
    tmp.close()
    tmp_path = Path(tmp.name)

    if suffix in VIDEO_EXTS:
        cap = cv2.VideoCapture(str(tmp_path))
        ok, user_preview = cap.read()
        cap.release()
        if not ok:
            return None, "Couldn't read any frames from that video.", None

        frame_results = analyze_video(detector, tmp_path, confidence_threshold)
        if not frame_results:
            return user_preview, "Couldn't read any frames from that video.", None

        overall_fail = any(not v.passed for _, v in frame_results)
        total_counts = Counter()
        for _, v in frame_results:
            total_counts.update(v.counts)
        display_frame = next((a for a, v in frame_results if not v.passed), frame_results[0][0])

        if overall_fail:
            text = (
                f"Scanned {len(frame_results)} sampled frames. "
                f"❌ **FAIL** — defect(s) found: {dict(total_counts)}"
            )
        else:
            text = f"Scanned {len(frame_results)} sampled frames. ✅ **PASS** — no defects above threshold in any of them."
        passed = not overall_fail
    else:
        frame = cv2.imread(str(tmp_path))
        if frame is None:
            return None, "Couldn't read that image.", None
        user_preview = frame
        display_frame, verdict = analyze_image(detector, frame, confidence_threshold)
        text = (
            "✅ **PASS** — no defects above threshold"
            if verdict.passed
            else f"❌ **FAIL** — defects detected: {verdict.counts}"
        )
        passed = verdict.passed

    if not passed:
        send_plc_fail_signal()
    if esp32_alert_url:
        send_esp32_alert(esp32_alert_url, state=not passed)

    return user_preview, text, display_frame


def render_live_camera(detector, confidence_threshold, esp32_alert_url):
    """Continuous webcam/ESP32-CAM feed - doesn't fit the turn-based chat above."""
    source_kind = st.radio("Source", ["Webcam", "ESP32-CAM (Phase 3)"])
    esp32_url = None
    if source_kind == "ESP32-CAM (Phase 3)":
        esp32_url = st.text_input("ESP32-CAM base URL", placeholder="http://192.168.1.50")
        st.caption("Requires Phase 3 hardware running this project's firmware.")

    if not st.button("Start live feed"):
        return

    try:
        source = WebcamSource(0) if source_kind == "Webcam" else Esp32Source(f"{esp32_url.rstrip('/')}/stream")
    except Exception as exc:
        st.error(f"Could not open source: {exc}")
        return

    frame_slot = st.empty()
    status_slot = st.empty()
    last_alert_state = None
    try:
        while True:
            frame = source.read()
            if frame is None:
                status_slot.info("Stream ended.")
                break
            annotated, verdict = analyze_image(detector, frame, confidence_threshold)
            frame_slot.image(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB), channels="RGB")
            status_slot.success("PASS") if verdict.passed else status_slot.error(f"FAIL - {verdict.counts}")
            if esp32_alert_url and verdict.passed != (last_alert_state is None or last_alert_state):
                send_esp32_alert(esp32_alert_url, state=not verdict.passed)
                last_alert_state = verdict.passed
    finally:
        source.release()


def main():
    st.set_page_config(page_title="Sheet Metal Defect Detection", layout="wide")
    st.title("🔩 Sheet Metal Defect Detection")

    if not DEFAULT_WEIGHTS.exists():
        st.error(f"No trained weights found at {DEFAULT_WEIGHTS}. Run scripts/train.py + evaluate.py first.")
        st.stop()

    detector = load_detector(str(DEFAULT_WEIGHTS))

    with st.sidebar:
        st.header("Settings")
        confidence_threshold = st.slider("Confidence threshold", 0.0, 1.0, 0.5, 0.05)
        esp32_alert_url = st.text_input("ESP32-CAM alert URL (optional, for LED/buzzer)", placeholder="http://192.168.1.50")

        st.caption(
            "Caveats: trained on NEU-DET (hot-rolled steel strip), not stamped sheet/brackets/gaskets. "
            "Metrics were measured on NEU-DET's own test split and won't automatically transfer to "
            "ESP32-CAM images without separately testing on real captures."
        )

        sample_files = sorted(p.name for p in SAMPLES_DIR.glob("*") if p.suffix.lower() != ".md") if SAMPLES_DIR.exists() else []
        if sample_files:
            st.divider()
            st.caption("No files handy? Drop a bundled sample into the chat:")
            chosen = st.selectbox("Bundled samples", ["—"] + sample_files, label_visibility="collapsed")
            if chosen != "—" and st.button(f"Send `{chosen}` to chat"):
                st.session_state.setdefault("pending_sample", chosen)

        st.divider()
        with st.expander("Live camera (webcam / ESP32-CAM)"):
            render_live_camera(detector, confidence_threshold, esp32_alert_url)

        st.divider()
        if st.button("Clear chat"):
            st.session_state.messages = []
            st.rerun()

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "text": "Hi! Attach a sheet-metal image or short video using the 📎 button below "
                        "and I'll check it for surface defects.",
                "image": None,
            }
        ]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg.get("image") is not None:
                st.image(cv2.cvtColor(msg["image"], cv2.COLOR_BGR2RGB), channels="RGB")
            if msg.get("text"):
                st.markdown(msg["text"])

    prompt = st.chat_input(
        "Attach an image or video to check for defects...",
        accept_file=True,
        file_type=["jpg", "jpeg", "png", "bmp", "mp4", "avi", "mov"],
    )

    pending_sample = st.session_state.pop("pending_sample", None)

    if pending_sample or (prompt and prompt.files):
        files_to_process = []
        if pending_sample:
            sample_path = SAMPLES_DIR / pending_sample
            files_to_process.append(("sample", sample_path, pending_sample))
        if prompt and prompt.files:
            for f in prompt.files:
                files_to_process.append(("upload", f, f.name))

        for kind, payload, name in files_to_process:
            file_bytes = payload.read_bytes() if kind == "sample" else payload.getvalue()

            user_preview, reply_text, reply_image = handle_attachment(
                detector, file_bytes, name, confidence_threshold, esp32_alert_url
            )

            user_text = (prompt.text if prompt and prompt.text else None) or f"Sent `{name}`"
            st.session_state.messages.append({"role": "user", "text": user_text, "image": user_preview})
            st.session_state.messages.append({"role": "assistant", "text": reply_text, "image": reply_image})

        st.rerun()
    elif prompt and prompt.text:
        st.session_state.messages.append({"role": "user", "text": prompt.text, "image": None})
        st.session_state.messages.append({
            "role": "assistant",
            "text": "Attach an image or video using the 📎 button and I'll check it for defects.",
            "image": None,
        })
        st.rerun()


if __name__ == "__main__":
    main()
