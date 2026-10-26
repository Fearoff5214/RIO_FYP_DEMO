"""Stand-in MES / QMS / ERP / notification receiver for local testing.

    uvicorn backend.mock_systems:app --port 9000
    then in .env: MES_URL=http://localhost:9000/mes  QMS_URL=http://localhost:9000/qms
                  ERP_URL=http://localhost:9000/erp  NOTIFY_URL=http://localhost:9000/notify

POST /fail?on=true makes every receiver answer 503, to exercise the outbox retry path.
"""
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI(title="Mock plant systems")
received: list[dict] = []
_state = {"fail": False}
_seen_keys: set[str] = set()


@app.post("/fail")
def set_fail(on: bool = True):
    _state["fail"] = on
    return _state


@app.get("/received")
def get_received():
    return received


@app.post("/{system}")
async def receive(system: str, request: Request, idempotency_key: str | None = Header(default=None)):
    if system not in ("mes", "qms", "erp", "notify"):
        raise HTTPException(404)
    if _state["fail"]:
        raise HTTPException(503, "simulated outage")
    if idempotency_key and idempotency_key in _seen_keys:
        return {"ok": True, "duplicate": True}
    if idempotency_key:
        _seen_keys.add(idempotency_key)
    received.append({"system": system, "key": idempotency_key, "body": await request.json()})
    return {"ok": True}
