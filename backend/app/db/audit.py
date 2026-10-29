"""Audit log writer — append-only, never deletes or updates."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def write_audit(
    db: AsyncSession,
    event: str,
    *,
    job_id: str | None = None,
    actor: str | None = None,
    actor_role: str | None = None,
    node: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    """Append an audit log entry. Computes a SHA-256 hash of the payload."""
    state_hash: str | None = None
    if payload:
        state_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

    entry = AuditLog(
        job_id=job_id,
        actor=actor,
        actor_role=actor_role,
        node=node,
        event=event,
        state_hash=state_hash,
        payload=payload,
        ts=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.commit()
    return entry
