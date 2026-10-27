"""FastAPI surface: create jobs, poll status, resolve human gates, download reports, manage the KB."""
import shutil
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import threading
import time

from . import camera, config, db, integrations, learning, rag, watcher
from .graph import workflow

app = FastAPI(title="Novaliseo AI Quality Inspection")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup() -> None:
    if db.count_chunks() == 0 and config.KB_SEED_DIR.exists():
        rag.ingest_seed_dir()
    rag.reindex_if_needed()

    def retry_loop():  # re-send queued MES/QMS/ERP messages every minute
        while True:
            time.sleep(60)
            try:
                integrations.retry_pending()
            except Exception:
                pass
    threading.Thread(target=retry_loop, daemon=True).start()


def _job_or_404(job_id: str) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/health")
def health():
    from . import llm
    return {"ok": True, "llm_available": llm.available(), "kb_chunks": db.count_chunks()}


@app.post("/api/jobs")
def create_job(part_number: str = Form(...), files: list[UploadFile] = File(...)):
    job_id = uuid.uuid4().hex[:12]
    dest = config.UPLOAD_DIR / job_id
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for f in files:
        name = Path(f.filename or "image.jpg").name  # strip any client-supplied directories
        with open(dest / name, "wb") as out:
            shutil.copyfileobj(f.file, out)
        paths.append(str(dest / name))
    workflow.start_job(part_number, paths, job_id=job_id)
    return {"job_id": job_id}


@app.get("/api/jobs")
def jobs():
    return db.list_jobs()


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    job = _job_or_404(job_id)
    return {"job": job, "graph": workflow.status(job_id), "audit": db.get_audit(job_id)}


@app.post("/api/jobs/{job_id}/gate")
def resolve_gate(job_id: str, answer: dict = Body(...)):
    _job_or_404(job_id)
    if not workflow.status(job_id)["pending"]:
        raise HTTPException(409, "no human gate is pending for this job")
    workflow.resume(job_id, answer)
    return workflow.status(job_id)


@app.get("/api/jobs/{job_id}/report/{fmt}")
def download_report(job_id: str, fmt: str):
    paths = _job_or_404(job_id)["result"].get("report_paths") or workflow.status(job_id)["state"].get("report_paths")
    if not paths or fmt not in paths:
        raise HTTPException(404, "report not available")
    return FileResponse(paths[fmt], filename=Path(paths[fmt]).name)


@app.post("/api/kb/upload")
def kb_upload(file: UploadFile = File(...)):
    dest = config.DATA_DIR / "kb_uploads"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / Path(file.filename or "doc.txt").name
    with open(path, "wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        return {"chunks": rag.ingest_path(path)}
    except ValueError as e:
        raise HTTPException(415, str(e))


@app.get("/api/actions")
def actions(job_id: str | None = None):
    return db.list_actions(job_id)


@app.post("/api/actions/{action_id}/close")
def close_action(action_id: int, effective: bool = Body(..., embed=True), evidence: str = Body("", embed=True)):
    return {"status": db.close_action(action_id, effective, evidence)}


# --- live camera (phone via Iriun Webcam) -------------------------------------------------

@app.get("/api/camera/devices")
def camera_devices():
    return camera.list_devices()


@app.get("/api/camera/stream")
def camera_stream(device: int = config.CAMERA_DEFAULT_DEVICE):
    try:
        camera.grab(device, settle_frames=0)  # fail fast with a clear message instead of an empty stream
    except camera.CameraError as e:
        raise HTTPException(503, str(e))
    return StreamingResponse(camera.mjpeg(device), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/jobs/from-camera")
def job_from_camera(part_number: str = Body(...), device: int = Body(config.CAMERA_DEFAULT_DEVICE),
                    frames: int = Body(1), recipe: dict = Body(default_factory=dict)):
    job_id = uuid.uuid4().hex[:12]
    try:
        paths = camera.capture(device, config.UPLOAD_DIR / job_id, max(1, min(frames, 8)), recipe or None)
    except camera.CameraError as e:
        raise HTTPException(503, str(e))
    workflow.start_job(part_number, paths, job_id=job_id, source={"type": "camera", "device": device}, recipe=recipe)
    return {"job_id": job_id}


@app.post("/api/watch/start")
def watch_start(part_number: str = Body(...), device: int = Body(config.CAMERA_DEFAULT_DEVICE),
                live_boxes: bool = Body(True)):
    try:
        camera.grab(device)
    except camera.CameraError as e:
        raise HTTPException(503, str(e))
    try:
        return watcher.start(part_number, device, live_boxes).status()
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@app.post("/api/watch/stop")
def watch_stop():
    watcher.stop()
    return {"ok": True}


@app.get("/api/watch")
def watch_status():
    w = watcher.current()
    return w.status() if w else {"running": False, "state": "off", "jobs": []}


@app.get("/api/watch/stream")
def watch_stream():
    w = watcher.current()
    if not w or not w.running:
        raise HTTPException(409, "not watching")
    return StreamingResponse(w.mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/camera/release")
def camera_release(device: int | None = None):
    camera.release(device)
    return {"ok": True}


# --- learning ---------------------------------------------------------------------------

@app.get("/api/learning")
def learning_status():
    return learning.status()


@app.post("/api/learning/retrain")
def learning_retrain(force: bool = Body(False, embed=True), epochs: int = Body(30, embed=True)):
    if not learning.retrain_async(force=force, epochs=epochs):
        raise HTTPException(409, "training already running")
    return {"started": True}


@app.post("/api/learning/activate")
def learning_activate(version: str = Body(..., embed=True)):
    try:
        learning.set_active(version)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return learning.status()


@app.post("/api/learning/recalibrate")
def learning_recalibrate():
    return learning.recalibrate()


# --- integrations ---------------------------------------------------------------------------

@app.get("/api/outbox")
def outbox(status: str | None = None, job_id: str | None = None):
    return db.outbox_list(status, job_id)


@app.post("/api/outbox/retry")
def outbox_retry():
    return integrations.retry_pending()


# --- anomaly model ----------------------------------------------------------------------------

@app.post("/api/anomaly/fit")
def anomaly_fit(part_number: str = Body("default", embed=True)):
    import cv2
    from .cv import anomaly
    folder = config.GOOD_IMAGES_DIR / part_number
    imgs = [cv2.imread(str(p)) for p in sorted(folder.glob("*")) if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    imgs = [i for i in imgs if i is not None]
    try:
        return anomaly.fit(imgs, config.ANOMALY_DIR / f"{part_number}.pt")
    except ValueError as e:
        raise HTTPException(422, str(e))


_dist = config.ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
