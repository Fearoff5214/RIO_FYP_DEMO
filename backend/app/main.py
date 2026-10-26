"""FastAPI surface: create jobs, poll status, resolve human gates, download reports, manage the KB."""
import shutil
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, rag
from .graph import workflow

app = FastAPI(title="Novaliseo AI Quality Inspection")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _seed_kb() -> None:
    if db.count_chunks() == 0 and config.KB_SEED_DIR.exists():
        rag.ingest_seed_dir()


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


_dist = config.ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
