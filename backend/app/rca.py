"""Stage 5: root-cause candidates from retrieved evidence. LLM when available, else evidence-only."""
from . import llm

REQUIRED = ("cause", "effect", "precautions", "sources")

SYSTEM = (
    "You are a sheet-metal manufacturing root-cause analyst. Use ONLY the numbered evidence. "
    'Reply with JSON: {"causes":[{"cause":str,"effect":str,"precautions":[str],"sources":[int],'
    '"rationale":str}]} with exactly 3 causes, most likely first. "sources" are evidence numbers.'
)


def _prompt(defects: list[dict], dim_status: str, part: dict, evidence: list[dict]) -> str:
    ev = "\n".join(f"[{i + 1}] ({e['source']}) {e['text']}" for i, e in enumerate(evidence))
    d = ", ".join(f"{x['cls']} ({x['conf']:.0%})" for x in defects)
    return (f"Part: {part.get('name', '?')}, material {part.get('material', '?')}, "
            f"process {part.get('process', '?')}\nDefects: {d}\nDimensional status: {dim_status}\n\nEvidence:\n{ev}")


def validate(raw: dict | None, n_evidence: int) -> list[dict] | None:
    """Schema + citation check. Returns cleaned causes or None if invalid (loop L5)."""
    causes = (raw or {}).get("causes")
    if not isinstance(causes, list) or len(causes) < 1:
        return None
    clean = []
    for c in causes[:3]:
        if not isinstance(c, dict) or any(not c.get(k) for k in REQUIRED):
            return None
        srcs = c["sources"]
        if not isinstance(srcs, list) or not all(isinstance(s, int) and 1 <= s <= n_evidence for s in srcs):
            return None
        clean.append({"cause": str(c["cause"]), "effect": str(c["effect"]),
                      "precautions": [str(p) for p in c["precautions"]] if isinstance(c["precautions"], list)
                      else [str(c["precautions"])],
                      "sources": srcs, "rationale": str(c.get("rationale", ""))})
    return clean


def generate(defects, dim_status, part, evidence) -> list[dict] | None:
    return validate(llm.chat_json(SYSTEM, _prompt(defects, dim_status, part, evidence)), len(evidence))


def from_evidence(evidence: list[dict]) -> list[dict]:
    """No-LLM fallback: surface the top evidence chunks as candidate causes, labelled as such."""
    out = []
    for i, e in enumerate(evidence[:3]):
        first = e["text"].strip().split("\n")[0][:160]
        out.append({"cause": first, "effect": "See source document.",
                    "precautions": [e["text"].strip()[:300]], "sources": [i + 1],
                    "rationale": f"Taken directly from {e['source']} (no LLM available)."})
    return out


def calibrate(causes: list[dict], evidence: list[dict], defects: list[dict], low_evidence: bool) -> list[dict]:
    """Confidence % per cause from retrieval score, detection confidence and rank. Top 3, ranked."""
    det = sum(d["conf"] for d in defects) / len(defects) if defects else 0.5
    ranked = []
    for rank, c in enumerate(causes[:3], start=1):
        ret = max((evidence[s - 1]["score"] for s in c["sources"] if 1 <= s <= len(evidence)), default=0.0)
        conf = min(0.95, (0.5 * min(1.0, ret * 2) + 0.5 * det) * (1 - 0.12 * (rank - 1)))
        if low_evidence:
            conf *= 0.6
        ranked.append({**c, "rank": rank, "confidence": round(conf * 100, 1)})
    return ranked
