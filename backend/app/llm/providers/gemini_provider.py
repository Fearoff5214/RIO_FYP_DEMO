"""Google Gemini LLM provider (REST, no extra SDK).

Reads the key from GEMINI_API_KEY (via Settings / .env). The key is sent in the
`x-goog-api-key` header and is never logged or placed in a URL.

On any failure (no key, network error, HTTP error, unparseable answer) it falls back to the
deterministic fake provider and marks every candidate with `model_version` starting with
"fallback-fake" and a short, key-free reason, so a failed AI call can never be mistaken for a
real one.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "root_cause.md"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"
RETRY_STATUS = {429, 500, 502, 503, 504}
LIST_FIELDS = ("precautions", "corrective_actions", "preventive_actions", "citations")
_STR_LIST = {"type": "ARRAY", "items": {"type": "STRING"}}
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {"candidates": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "cause": {"type": "STRING"}, "rationale": {"type": "STRING"}, "effect": {"type": "STRING"},
        "corrective_actions": _STR_LIST, "preventive_actions": _STR_LIST, "precautions": _STR_LIST,
        "verification": {"type": "STRING"}, "citations": _STR_LIST,
    }, "required": ["cause", "rationale", "effect", "corrective_actions", "preventive_actions", "citations"]}}},
    "required": ["candidates"],
}
_PLACEHOLDER = re.compile(r"insufficient|no (other|further|additional) (cause|evidence)|not enough evidence|unknown|n/?a", re.I)
MIN_OUTPUT_TOKENS = 8192      # newer Gemini models spend output tokens on thinking; a small limit truncates the JSON


class GeminiProvider:
    def __init__(self, cfg, transport: httpx.AsyncBaseTransport | None = None):
        self.cfg = cfg
        self.transport = transport                 # injectable for tests
        self.model = cfg.settings.gemini_model or "gemini-2.5-flash"
        self.last_error: str | None = None

    # ---- public API (same contract as the other providers) -------------------------------
    async def generate_root_causes(self, context: dict, evidence: dict, regenerate: bool = False) -> list[dict]:
        self.last_error = None
        key = (self.cfg.settings.gemini_api_key or "").strip()
        if not key:
            return await self._fallback("GEMINI_API_KEY is not set", context, evidence, regenerate)
        try:
            fallback_model = (getattr(self.cfg.settings, "gemini_fallback_model", "") or "").strip()
            models = list(dict.fromkeys(model for model in (self.model, fallback_model) if model))
            last: Exception | None = None
            for model in models:
                for attempt in range(2):                       # one retry if the answer cannot be parsed
                    try:
                        text = await self._call(
                            key,
                            _system_prompt(),
                            _user_message(context, evidence, regenerate or attempt > 0),
                            model=model,
                        )
                        candidates = _parse_candidates(text, evidence)
                        if candidates:
                            tag = f"gemini:{model}"
                            return [{**c, "model_version": tag} for c in candidates[:3]]
                        last = ValueError("the model returned no usable candidates")
                    except (json.JSONDecodeError, ValueError) as exc:
                        last = exc
                    except httpx.HTTPStatusError as exc:
                        last = exc
                        if not _can_try_next_model(exc) or model == models[-1]:
                            raise
                        break
            raise last or ValueError("no candidates")
        except Exception as exc:                                  # noqa: BLE001 - always degrade safely
            return await self._fallback(_safe_error(exc, key), context, evidence, regenerate)

    # ---- internals ------------------------------------------------------------------------
    async def _call(self, key: str, system: str, user: str, model: str | None = None) -> str:
        temperature = float(self.cfg.get("prediction", "llm", "temperature") or 0.2)
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max(int(self.cfg.get("prediction", "llm", "max_tokens") or 0), MIN_OUTPUT_TOKENS),
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
            },
        }
        url = f"{API_BASE}/models/{model or self.model}:generateContent"
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=60.0, transport=self.transport) as client:
            last: Exception | None = None
            for attempt in range(3):
                try:
                    response = await client.post(url, headers=headers, json=body)
                    if response.status_code == 429 and b"PerDay" in response.content:
                        response.raise_for_status()                 # daily quota: retrying cannot help
                    if response.status_code in RETRY_STATUS and attempt < 2:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    return _extract_text(response.json())
                except httpx.TransportError as exc:
                    last = exc
                    await asyncio.sleep(1.0 * (attempt + 1))
            raise last or RuntimeError("request failed")

    async def _fallback(self, reason: str, context: dict, evidence: dict, regenerate: bool) -> list[dict]:
        from app.llm.providers.fake import FakeLLMProvider

        self.last_error = reason
        logger.error('"llm":"gemini_fallback","reason":"%s"', reason)
        candidates = await FakeLLMProvider().generate_root_causes(context, evidence, regenerate)
        return [{**c, "model_version": f"fallback-fake (gemini failed: {reason})"} for c in candidates]


# ---- helpers (module level so they can be unit-tested) -----------------------------------
def _system_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return ("You are a quality engineering expert. Use only the provided evidence. Output ONLY JSON: "
            '{"candidates":[{"cause","rationale","effect","corrective_actions","preventive_actions","precautions","citations"}]}')


def _user_message(context: dict, evidence: dict, regenerate: bool) -> str:
    sources = evidence.get("sources", [])[:10]
    sources_text = "\n".join(f"[{s.get('chunk_id')}]: {s.get('text_excerpt', '')}" for s in sources) or "(no evidence retrieved)"
    out_of_tol = context.get("out_of_tolerance") or []
    return (
        f"Part: {context.get('part_number')} ({context.get('part_name')})\n"
        f"Material: {context.get('material')}, Process: {context.get('process')}\n"
        f"Defects detected: {json.dumps(context.get('defects'), default=str)}\n"
        f"Out-of-tolerance features: {json.dumps(out_of_tol, default=str)}\n\n"
        f"Evidence from the knowledge base (the ONLY allowed sources; cite them by the id in brackets):\n{sources_text}\n\n"
        + ("IMPORTANT: the previous answer was invalid. Regenerate with strict JSON and valid citations.\n" if regenerate else "")
        + "Return the 3 most likely root causes in the required JSON format."
    )


def _extract_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        block = (payload.get("promptFeedback") or {}).get("blockReason")
        raise ValueError(f"no candidates returned{f' (blocked: {block})' if block else ''}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        raise ValueError(f"empty response (finishReason={candidates[0].get('finishReason')})")
    return text


def _parse_candidates(text: str, evidence: dict) -> list[dict]:
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fenced:
        text = fenced.group(1)
    data = json.loads(text)
    items = data.get("candidates", data) if isinstance(data, dict) else data
    valid_ids = {s.get("chunk_id") for s in evidence.get("sources", [])}
    out: list[dict] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not item.get("cause"):
            continue
        if _PLACEHOLDER.search(str(item["cause"])):          # "Insufficient evidence ..." is not a cause
            continue
        cand = {k: item.get(k) for k in ("cause", "rationale", "effect", "verification")}
        for field in LIST_FIELDS:
            value = item.get(field) or []
            cand[field] = [str(v) for v in value] if isinstance(value, list) else [str(value)]
        # keep only citations that exist in the evidence the model was given (plus seed ids)
        cand["citations"] = [c for c in cand["citations"] if c in valid_ids or c.startswith("seed-")]
        cand["precautions"] = cand["precautions"] or (cand["corrective_actions"] + cand["preventive_actions"])
        cand["effect"] = cand["effect"] or ""
        cand["rationale"] = cand["rationale"] or ""
        out.append(cand)
    return out


def _safe_error(exc: Exception, key: str) -> str:
    """Short error text that cannot contain the API key."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429 and b"PerDay" in exc.response.content:
            return "HTTP 429: daily free-tier quota used up for this model (set GEMINI_MODEL to another model or enable billing)"
        hint = {400: "bad request (check GEMINI_MODEL)", 401: "unauthorised", 403: "key rejected or API not enabled",
                404: "model not found (check GEMINI_MODEL)", 429: "rate limited / quota exceeded"}.get(code, "HTTP error")
        return f"HTTP {code}: {hint}"
    text = f"{type(exc).__name__}: {exc}"
    return text.replace(key, "***")[:160]


def _can_try_next_model(exc: httpx.HTTPStatusError) -> bool:
    """Model availability and quota can differ, while credential errors affect every model."""
    return exc.response.status_code in {404, 429}
