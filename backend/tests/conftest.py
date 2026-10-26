import shutil
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from backend.app import config, db, rag
from backend.app.graph import workflow

SAMPLES = config.ROOT / "samples"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(config, "LLM_PROVIDER", "none")  # offline: hash embeddings, evidence-only RCA
    workflow.use_graph(workflow.build(MemorySaver()))
    rag.ingest_seed_dir()
    yield tmp_path
    workflow.use_graph(None)


@pytest.fixture
def image(env):
    dst = env / "plate.jpg"
    shutil.copy(SAMPLES / "defect_scratches.jpg", dst)
    return str(dst)


@pytest.fixture
def detections(monkeypatch):
    """Control what the detector returns: detections['value'] = [...]."""
    box = {"value": [{"cls": "scratches", "conf": 0.9, "bbox": [10, 10, 80, 60], "source": "test"}]}
    monkeypatch.setattr("backend.app.graph.nodes.detector.detect", lambda p: [dict(d) for d in box["value"]])
    return box


def pending(job_id):
    return workflow.status(job_id)["pending"]


def gate_name(job_id):
    p = pending(job_id)
    return p["gate"] if p else None


def run_to_gate(job_id, answers):
    """Resume with answers[gate] (a dict, or a list consumed in order) until no gate is pending."""
    answers = {k: list(v) if isinstance(v, list) else [v] for k, v in answers.items()}
    seen = []
    while (g := gate_name(job_id)):
        seen.append(g)
        queue = answers.get(g)
        if not queue:
            break
        workflow.resume(job_id, queue.pop(0) if len(queue) > 1 else queue[0])
        if len(seen) > 40:
            raise AssertionError(f"runaway loop: {seen}")
    return seen
