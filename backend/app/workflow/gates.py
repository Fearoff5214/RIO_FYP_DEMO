"""
Human gate interrupt/resume helpers.
The API layer calls resume_gate() to inject a human decision and continue the graph.
"""
from __future__ import annotations

from typing import Any

from langgraph.types import Command

from app.core.logging import get_logger

logger = get_logger(__name__)


async def resume_gate(
    app,
    thread_id: str,
    gate: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    """
    Resume a graph that is paused at a human gate.

    Parameters
    ----------
    app : compiled LangGraph
    thread_id : LangGraph thread identifier
    gate : gate name for logging (GATE1, LABEL, GATE2, GATE3)
    decision : the human's decision payload

    Returns
    -------
    dict : current state snapshot after resumption
    """
    config = {"configurable": {"thread_id": thread_id}}

    logger.info('"action":"resume_gate","gate":"%s","thread":"%s"', gate, thread_id)

    # LangGraph Command(resume=...) injects the value returned from interrupt()
    result = await app.ainvoke(Command(resume=decision), config=config)
    return result


async def get_gate_payload(app, thread_id: str) -> dict[str, Any] | None:
    """
    Return the interrupt payload from the currently paused gate, if any.
    """
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await app.aget_state(config)
        if state and state.next:
            # The interrupt payload is stored in the state's tasks
            tasks = getattr(state, "tasks", [])
            for task in tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    return task.interrupts[0].value
        return None
    except Exception as e:
        logger.error('"action":"get_gate_payload","error":"%s"', str(e))
        return None
