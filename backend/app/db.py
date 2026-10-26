"""SQLite persistence: jobs, audit trail, knowledge base, feedback, corrective actions.

stdlib sqlite3 keeps the MVP dependency-free. The functions here are the whole data
interface, so moving to PostgreSQL later means reimplementing this one module.
"""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, part_number TEXT, status TEXT, created REAL, updated REAL, result TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, ts REAL, stage TEXT, event TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS kb_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, text TEXT, tags TEXT, embedding TEXT, created REAL
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, kind TEXT, payload TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, description TEXT, owner TEXT, due TEXT,
  status TEXT, evidence TEXT, ts REAL
);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None
_conn_path = None


def conn() -> sqlite3.Connection:
    """Process-wide connection, reopened if DB_PATH changed (tests point it at a temp dir)."""
    global _conn, _conn_path
    path = config.DB_PATH
    with _lock:
        if _conn is None or _conn_path != path:
            if _conn is not None:
                _conn.close()
            path.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(path, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(_SCHEMA)
            _conn_path = path
        return _conn


@contextmanager
def tx():
    with _lock:
        c = conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def create_job(job_id: str, part_number: str) -> None:
    now = time.time()
    with tx() as c:
        c.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?)",
                  (job_id, part_number, "created", now, now, "{}"))


def update_job(job_id: str, status: str | None = None, result: dict | None = None,
               part_number: str | None = None) -> None:
    with tx() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return
        merged = json.loads(row["result"] or "{}")
        merged.update(result or {})
        c.execute("UPDATE jobs SET status=?, part_number=?, updated=?, result=? WHERE id=?",
                  (status or row["status"], part_number or row["part_number"], time.time(),
                   json.dumps(merged, default=str), job_id))


def get_job(job_id: str) -> dict | None:
    with _lock:
        row = conn().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _job(row) if row else None


def list_jobs() -> list[dict]:
    with _lock:
        rows = conn().execute("SELECT * FROM jobs ORDER BY created DESC").fetchall()
    return [_job(r) for r in rows]


def _job(row) -> dict:
    d = dict(row)
    d["result"] = json.loads(d["result"] or "{}")
    return d


def audit(job_id: str, stage: str, event: str, detail: dict | None = None) -> None:
    with tx() as c:
        c.execute("INSERT INTO audit_log (job_id, ts, stage, event, detail) VALUES (?,?,?,?,?)",
                  (job_id, time.time(), stage, event, json.dumps(detail or {}, default=str)))


def get_audit(job_id: str) -> list[dict]:
    with _lock:
        rows = conn().execute("SELECT * FROM audit_log WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
    return [{**dict(r), "detail": json.loads(r["detail"])} for r in rows]


def add_chunk(source: str, text: str, tags: dict, embedding: list[float]) -> int:
    with tx() as c:
        cur = c.execute("INSERT INTO kb_chunks (source, text, tags, embedding, created) VALUES (?,?,?,?,?)",
                        (source, text, json.dumps(tags), json.dumps(embedding), time.time()))
        return cur.lastrowid


def all_chunks() -> list[dict]:
    with _lock:
        rows = conn().execute("SELECT * FROM kb_chunks").fetchall()
    return [{**dict(r), "tags": json.loads(r["tags"]), "embedding": json.loads(r["embedding"])}
            for r in rows]


def count_chunks() -> int:
    with _lock:
        return conn().execute("SELECT COUNT(*) FROM kb_chunks").fetchone()[0]


def add_feedback(job_id: str, kind: str, payload: dict) -> None:
    with tx() as c:
        c.execute("INSERT INTO feedback (job_id, kind, payload, ts) VALUES (?,?,?,?)",
                  (job_id, kind, json.dumps(payload, default=str), time.time()))


def get_feedback(kind: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM feedback", ()
    if kind:
        q, args = q + " WHERE kind=?", (kind,)
    with _lock:
        rows = conn().execute(q, args).fetchall()
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


def add_action(job_id: str, description: str, owner: str = "quality-lead", due: str = "") -> int:
    with tx() as c:
        cur = c.execute("INSERT INTO actions (job_id, description, owner, due, status, evidence, ts) "
                        "VALUES (?,?,?,?,?,?,?)", (job_id, description, owner, due, "open", "", time.time()))
        return cur.lastrowid


def list_actions(job_id: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM actions", ()
    if job_id:
        q, args = q + " WHERE job_id=?", (job_id,)
    with _lock:
        return [dict(r) for r in conn().execute(q, args).fetchall()]


def close_action(action_id: int, effective: bool, evidence: str = "") -> str:
    """L9: an ineffective action is reopened and escalated rather than closed."""
    status = "closed" if effective else "escalated"
    with tx() as c:
        c.execute("UPDATE actions SET status=?, evidence=? WHERE id=?", (status, evidence, action_id))
    return status
