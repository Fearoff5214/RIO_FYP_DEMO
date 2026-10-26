"""LangGraph wiring for the 8-stage flow, plus start/resume/status helpers used by the API."""
import sqlite3
import uuid

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from .. import config, db
from . import nodes
from .state import InspectionState


def _route(state):
    return state.get("_route")


def build(checkpointer):
    g = StateGraph(InspectionState)
    for name, fn in [("load_context", nodes.load_context), ("capture", nodes.capture),
                     ("dimensional", nodes.dimensional_check), ("gate1", nodes.gate1),
                     ("detect", nodes.detect), ("label_review", nodes.label_review),
                     ("retrieve", nodes.retrieve), ("rca", nodes.run_rca), ("gate2", nodes.gate2),
                     ("report", nodes.make_report), ("gate3", nodes.gate3), ("finalize", nodes.finalize)]:
        g.add_node(name, fn)

    g.add_edge(START, "load_context")
    g.add_conditional_edges("load_context", _route, {"ok": "capture", "retry": "load_context", "hold": END})
    g.add_conditional_edges("capture", _route, {"ok": "dimensional", "retry": "capture"})
    g.add_edge("dimensional", "gate1")
    g.add_conditional_edges("gate1", _route, {"ok": "detect", "retry": "dimensional"})
    g.add_edge("detect", "label_review")
    g.add_conditional_edges("label_review", _route, {"retrieve": "retrieve", "report": "report"})  # fast path
    g.add_conditional_edges("retrieve", _route, {"ok": "rca", "retry": "retrieve"})
    g.add_conditional_edges("rca", _route, {"ok": "gate2", "retry": "rca"})
    g.add_conditional_edges("gate2", _route, {"ok": "report", "reinspect": "capture"})
    g.add_conditional_edges("report", _route, {"ok": "gate3", "retry": "report"})
    g.add_conditional_edges("gate3", _route, {"approved": "finalize", "redraft": "report", "hold": END})
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)


_graph = None


def make_checkpointer(persistent: bool = True):
    if not persistent:
        return MemorySaver()
    config.CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(config.CHECKPOINT_PATH, check_same_thread=False))


def graph():
    global _graph
    if _graph is None:
        _graph = build(make_checkpointer())
    return _graph


def use_graph(g) -> None:
    """Swap the compiled graph (tests use an in-memory checkpointer)."""
    global _graph
    _graph = g


def _cfg(job_id: str) -> dict:
    return {"configurable": {"thread_id": job_id}}


def start_job(part_number: str, image_paths: list[str], job_id: str | None = None) -> str:
    job_id = job_id or uuid.uuid4().hex[:12]
    db.create_job(job_id, part_number)
    db.audit(job_id, "trigger", "job_created", {"part_number": part_number, "images": image_paths})
    graph().invoke({"job_id": job_id, "part_number": part_number, "image_paths": image_paths,
                    "flags": [], "retries": {}, "report_revision": 1, "approver_comments": []}, _cfg(job_id))
    return job_id


def resume(job_id: str, value: dict) -> None:
    graph().invoke(Command(resume=value), _cfg(job_id))


def status(job_id: str) -> dict:
    snap = graph().get_state(_cfg(job_id))
    pending = [i.value for t in snap.tasks for i in t.interrupts]
    return {"job_id": job_id, "next": list(snap.next), "pending": pending[0] if pending else None,
            "state": {k: v for k, v in snap.values.items() if not k.startswith("_")}}
