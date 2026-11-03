"""Nodes that persist loop counters and flags (routing functions cannot change state)."""
from __future__ import annotations

from app.workflow.state import InspectionState


def _flags_with(state: InspectionState, flag: str) -> list:
    flags = list(state.get("flags", []) or [])
    if flag not in flags:
        flags.append(flag)
    return flags


def _bumped(state: InspectionState, loop: str) -> dict:
    loops = dict(state.get("loops", {}) or {})
    loops[loop] = loops.get(loop, 0) + 1
    return loops


async def retry_evidence(state: InspectionState) -> dict:
    """L4: count the retry, then filters are relaxed one step further by apply_filters."""
    return {"loops": _bumped(state, "L4")}


async def flag_low_evidence(state: InspectionState) -> dict:
    """L4 exhausted: continue with the evidence we have, flagged."""
    return {"loops": _bumped(state, "L4"), "flags": _flags_with(state, "low_evidence")}


async def retry_llm(state: InspectionState) -> dict:
    """L5: count the regeneration; the flag makes the provider regenerate with strict citations."""
    return {"loops": _bumped(state, "L5"), "flags": _flags_with(state, "low_confidence")}


async def flag_low_confidence(state: InspectionState) -> dict:
    """L5 exhausted: keep the output, flagged."""
    return {"loops": _bumped(state, "L5"), "flags": _flags_with(state, "low_confidence")}
