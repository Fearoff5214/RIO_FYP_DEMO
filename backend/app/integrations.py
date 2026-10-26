"""Stage 8 output: push the signed-off result to MES, QMS, ERP and a notification webhook.

Every message goes through the DB outbox first, so a down system never loses a result or
blocks the job: delivery is retried with backoff now and again by `retry_pending` (the API
calls it on a timer). Connector URLs come from .env; an empty URL disables that connector.
The default message shapes are generic JSON - map them to a specific vendor in `_build`.
"""
import time

import requests

from . import config, db

SYSTEMS = ("mes", "qms", "erp", "notify")


def _urls() -> dict[str, str]:
    return {"mes": config.MES_URL, "qms": config.QMS_URL, "erp": config.ERP_URL, "notify": config.NOTIFY_URL}


def _build(system: str, job_id: str, ctx: dict) -> dict:
    ok = ctx["result"] == "OK"
    base = {"job_id": job_id, "part_number": ctx["part_number"], "result": ctx["result"],
            "completed_at": ctx["completed_at"]}
    if system == "mes":  # shop-floor disposition
        return {**base, "disposition": "release" if ok else "hold",
                "defect_classes": sorted({d["cls"] for d in ctx["defects"]})}
    if system == "qms":  # full quality record
        return {**base, "defects": ctx["defects"], "dimensional": ctx["dimensional"],
                "root_cause": ctx.get("selected_cause"), "actions": ctx.get("actions", []),
                "approved_by": ctx.get("approver"), "flags": ctx.get("flags", []),
                "report_files": ctx.get("report_paths", {})}
    if system == "erp":  # stock / cost impact
        return {**base, "quarantine": not ok, "scrap_review": not ok and
                any(d.get("severity") == "high" for d in ctx["defects"])}
    n = len(ctx["defects"])
    cause = (ctx.get("selected_cause") or {}).get("cause", "")
    return {"text": f"Part {ctx['part_number']} job {job_id}: {ctx['result']}"
                    + (f", {n} defect(s). Root cause: {cause}" if not ok else ""), **base}


def _post(url: str, payload: dict, key: str) -> None:
    headers = {"Idempotency-Key": key}
    if config.INTEGRATION_TOKEN:
        headers["Authorization"] = f"Bearer {config.INTEGRATION_TOKEN}"
    requests.post(url, json=payload, headers=headers, timeout=10).raise_for_status()


def _deliver(row: dict, sleep=time.sleep) -> str:
    url = _urls()[row["system"]]
    attempts, err = row["attempts"], ""
    while attempts < config.INTEGRATION_ATTEMPTS:
        try:
            _post(url, row["payload"], f"{row['job_id']}:{row['system']}")
            db.outbox_update(row["id"], "sent", attempts + 1)
            return "sent"
        except requests.RequestException as e:
            attempts += 1
            err = f"{type(e).__name__}: {e}"
            db.outbox_update(row["id"], "pending" if attempts < config.INTEGRATION_ATTEMPTS else "failed", attempts, err)
            if attempts < config.INTEGRATION_ATTEMPTS:
                sleep(min(2 ** attempts, 8))
    return "failed"


def dispatch(job_id: str, ctx: dict, sleep=time.sleep) -> dict[str, str]:
    """Queue and send to every configured system. Returns {system: sent|failed|disabled}."""
    out = {}
    for system, url in _urls().items():
        if not url:
            out[system] = "disabled"
            continue
        db.outbox_enqueue(job_id, system, _build(system, job_id, ctx))
        row = next(r for r in db.outbox_list(job_id=job_id) if r["system"] == system)
        out[system] = row["status"] if row["status"] == "sent" else _deliver(row, sleep)
    db.audit(job_id, "dispatch", "notify", out)
    return out


def retry_pending(sleep=time.sleep) -> dict[str, int]:
    """Re-send queued and failed messages (e.g. after a system comes back)."""
    done = failed = 0
    for row in db.outbox_list():
        if row["status"] == "sent" or not _urls().get(row["system"]):
            continue
        row["attempts"] = 0  # a manual or timed retry gets a fresh attempt budget
        if _deliver(row, sleep) == "sent":
            done += 1
        else:
            failed += 1
    return {"sent": done, "failed": failed}
