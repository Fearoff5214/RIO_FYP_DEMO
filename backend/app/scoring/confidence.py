"""Confidence scoring for root cause candidates."""
from __future__ import annotations


def score_candidates(
    candidates: list[dict],
    reranked: list[dict],
    defects: list[dict],
    weights: dict[str, float],
) -> list[dict]:
    """
    Compute confidence_raw for each candidate using:
    - retrieval: max rerank score for chunks cited by this candidate
    - history: frequency score (placeholder; 0.5 if no history)
    - detection: average detection confidence weighted by defect severity
    """
    w_ret = weights.get("retrieval", 0.5)
    w_hist = weights.get("history", 0.3)
    w_det = weights.get("detection", 0.2)

    chunk_score_map = {c.get("chunk_id", ""): c.get("score", 0.0) for c in reranked}

    # Detection score: average confidence weighted by severity
    severity_weights = {"critical": 1.0, "major": 0.7, "minor": 0.4}
    if defects:
        det_scores = [
            d.get("confidence", 0.5) * severity_weights.get(d.get("severity", "minor"), 0.4)
            for d in defects
        ]
        det_score = sum(det_scores) / len(det_scores)
    else:
        det_score = 0.5

    scored = []
    for i, cand in enumerate(candidates):
        citations = cand.get("citations", [])
        retrieval_scores = [
            chunk_score_map.get(cid, 0.0) for cid in citations if cid in chunk_score_map
        ]
        # Seed citations get a default score
        seed_scores = [0.7 for cid in citations if cid.startswith("seed-")]
        all_scores = retrieval_scores + seed_scores
        ret_score = max(all_scores) if all_scores else 0.3

        # History: decrease score for lower-ranked candidates (placeholder)
        history_score = max(0.3, 0.7 - i * 0.1)

        raw = w_ret * ret_score + w_hist * history_score + w_det * det_score
        raw = min(1.0, max(0.0, raw))

        scored.append({**cand, "confidence_raw": round(raw, 4)})

    return scored
