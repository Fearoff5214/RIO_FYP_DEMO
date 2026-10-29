"""Unit tests for confidence scoring and validation."""
import pytest
from app.scoring.confidence import score_candidates
from app.llm.validators import validate_top3


def test_score_candidates_ordered():
    candidates = [
        {"cause": "Cause A", "citations": ["seed-001"], "confidence_raw": 0},
        {"cause": "Cause B", "citations": ["seed-002"], "confidence_raw": 0},
        {"cause": "Cause C", "citations": ["seed-003"], "confidence_raw": 0},
    ]
    reranked = [
        {"chunk_id": "seed-001", "score": 0.9},
        {"chunk_id": "seed-002", "score": 0.7},
        {"chunk_id": "seed-003", "score": 0.6},
    ]
    defects = [{"severity": "critical", "confidence": 0.9}]
    weights = {"retrieval": 0.5, "history": 0.3, "detection": 0.2}

    scored = score_candidates(candidates, reranked, defects, weights)
    # Scores should be decreasing (higher index = lower score)
    assert scored[0]["confidence_raw"] > scored[2]["confidence_raw"]


def test_validate_top3_valid():
    top3 = [
        {"rank": 1, "cause": "Over Bending", "effect": "Deformation",
         "precautions": ["Action 1"], "citations": ["seed-001"]},
        {"rank": 2, "cause": "Material Issue", "effect": "Cracking",
         "precautions": ["Action 2"], "citations": ["seed-002"]},
        {"rank": 3, "cause": "Tool Wear", "effect": "Scratches",
         "precautions": ["Action 3"], "citations": ["seed-003"]},
    ]
    reranked = [{"chunk_id": "seed-001"}, {"chunk_id": "seed-002"}, {"chunk_id": "seed-003"}]
    valid, issues = validate_top3(top3, reranked)
    assert valid is True
    assert len(issues) == 0


def test_validate_top3_missing_cause():
    top3 = [{"rank": 1, "effect": "Deformation", "precautions": ["A"], "citations": ["seed-001"]}]
    reranked = [{"chunk_id": "seed-001"}]
    valid, issues = validate_top3(top3, reranked)
    assert valid is False
    assert any("cause" in i for i in issues)


def test_validate_top3_empty():
    valid, issues = validate_top3([], [])
    assert valid is False
