"""
Turns a list of detections into a PASS/FAIL verdict plus per-class counts.
Kept as a pure function (no I/O, no model, no hardware) so it's trivial to
unit test and reason about independently of everything else.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from detector import Detection


@dataclass
class Verdict:
    passed: bool
    counts: dict[str, int]


def decide(detections: list[Detection], confidence_threshold: float) -> Verdict:
    failing = [d for d in detections if d.confidence >= confidence_threshold]
    counts = Counter(d.class_name for d in failing)
    return Verdict(passed=len(failing) == 0, counts=dict(counts))
