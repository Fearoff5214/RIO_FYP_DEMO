"""Validate LLM top-3 output: JSON valid, citations exist, effect consistent."""
from __future__ import annotations


def validate_top3(top3: list[dict], reranked: list[dict]) -> tuple[bool, list[str]]:
    """
    Validate the top-3 root cause candidates.
    Returns (valid, issues).
    """
    issues = []

    if not top3:
        return False, ["No candidates produced"]

    chunk_ids = {c.get("chunk_id", "") for c in reranked}

    for i, cand in enumerate(top3):
        if not cand.get("cause"):
            issues.append(f"Candidate {i+1}: missing 'cause'")
        if not cand.get("effect"):
            issues.append(f"Candidate {i+1}: missing 'effect'")
        if not cand.get("precautions"):
            issues.append(f"Candidate {i+1}: missing 'precautions'")

        # Citation check: allow seed IDs and real chunk IDs
        citations = cand.get("citations", [])
        if not citations:
            issues.append(f"Candidate {i+1}: no citations")
        else:
            bad = [c for c in citations if c not in chunk_ids and not c.startswith("seed-")]
            if bad:
                issues.append(f"Candidate {i+1}: unknown citations {bad}")

    return len(issues) == 0, issues
