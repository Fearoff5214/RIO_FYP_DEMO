"""Gemini provider, provider selection, RCA pipeline and RCA document tests (no real API calls)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.llm.factory import get_llm_provider, resolve_provider_name
from app.llm.providers.fake import FakeLLMProvider
from app.llm.providers.gemini_provider import GeminiProvider

KEY = "test-key-123456"
EVIDENCE = {"sources": [{"chunk_id": "c1", "text_excerpt": "Over bending force causes deformation."},
                        {"chunk_id": "c2", "text_excerpt": "Hardness variation causes cracks."}]}
CONTEXT = {"part_number": "MS-4505-001", "defects": [{"type": "crack"}]}
ANSWER = {"candidates": [
    {"cause": "Over bending force", "rationale": "Deformation matches c1.", "effect": "Deformation",
     "corrective_actions": ["Reset force"], "preventive_actions": ["Calibrate monthly"], "precautions": ["Check dies"],
     "verification": "Re-inspect 30 parts", "citations": ["c1", "made-up-id"]},
    {"cause": "Hardness variation", "rationale": "Cracks match c2.", "effect": "Cracking",
     "corrective_actions": ["Quarantine batch"], "preventive_actions": ["Incoming test"], "citations": ["c2"]},
]}


def cfg(key=KEY, provider="", fallback_model=""):
    return SimpleNamespace(
        settings=SimpleNamespace(
            gemini_api_key=key,
            gemini_model="gemini-test",
            gemini_fallback_model=fallback_model,
            novaliseo_llm_provider=provider,
        ),
        get=lambda *a, **k: None,
    )


def gemini_reply(payload) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": payload if isinstance(payload, str) else json.dumps(payload)}]}}]}


def provider_with(handler, key=KEY):
    return GeminiProvider(cfg(key), transport=httpx.MockTransport(handler))


# ---- provider selection ---------------------------------------------------------------------
def test_auto_uses_fake_without_key_and_gemini_with_key():
    assert resolve_provider_name(cfg(key="")) == "fake"
    assert resolve_provider_name(cfg(key=KEY)) == "gemini"
    assert isinstance(get_llm_provider(cfg(key="")), FakeLLMProvider)
    assert isinstance(get_llm_provider(cfg(key=KEY)), GeminiProvider)


def test_env_override_wins():
    assert resolve_provider_name(cfg(key=KEY, provider="fake")) == "fake"


# ---- Gemini provider --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_parses_answer_and_filters_unknown_citations():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["headers"], seen["body"] = str(request.url), request.headers, json.loads(request.content)
        return httpx.Response(200, json=gemini_reply(ANSWER))

    out = await provider_with(handler).generate_root_causes(CONTEXT, EVIDENCE)
    assert [c["cause"] for c in out] == ["Over bending force", "Hardness variation"]
    assert out[0]["citations"] == ["c1"]                       # the made-up id was dropped
    assert out[0]["corrective_actions"] == ["Reset force"] and out[0]["rationale"]
    assert out[0]["model_version"] == "gemini:gemini-test"
    # the key goes in a header, never in the URL
    assert seen["headers"]["x-goog-api-key"] == KEY and KEY not in seen["url"]
    assert "gemini-test:generateContent" in seen["url"]
    assert "c1" in seen["body"]["contents"][0]["parts"][0]["text"]


@pytest.mark.asyncio
async def test_tries_fallback_model_when_primary_is_unavailable():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "gemini-test" in str(request.url):
            return httpx.Response(404, json={"error": {"message": "model not found"}})
        return httpx.Response(200, json=gemini_reply(ANSWER))

    provider = GeminiProvider(
        cfg(fallback_model="gemini-fallback-test"),
        transport=httpx.MockTransport(handler),
    )
    out = await provider.generate_root_causes(CONTEXT, EVIDENCE)

    assert len(seen) == 2
    assert "gemini-test:generateContent" in seen[0]
    assert "gemini-fallback-test:generateContent" in seen[1]
    assert out[0]["model_version"] == "gemini:gemini-fallback-test"


@pytest.mark.asyncio
async def test_placeholder_candidates_are_dropped():
    answer = {"candidates": ANSWER["candidates"] + [{"cause": "Insufficient Evidence for Alternative Causes", "rationale": "-", "effect": "-",
                                                      "corrective_actions": [], "preventive_actions": [], "citations": ["c1"]}]}
    out = await provider_with(lambda r: httpx.Response(200, json=gemini_reply(answer))).generate_root_causes(CONTEXT, EVIDENCE)
    assert [c["cause"] for c in out] == ["Over bending force", "Hardness variation"]


@pytest.mark.asyncio
async def test_accepts_json_in_code_fence():
    fenced = "```json\n" + json.dumps(ANSWER) + "\n```"
    out = await provider_with(lambda r: httpx.Response(200, json=gemini_reply(fenced))).generate_root_causes(CONTEXT, EVIDENCE)
    assert out[0]["cause"] == "Over bending force"


@pytest.mark.asyncio
async def test_retries_rate_limit_then_succeeds(monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr("app.llm.providers.gemini_provider.asyncio.sleep", no_sleep)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429) if calls["n"] == 1 else httpx.Response(200, json=gemini_reply(ANSWER))

    out = await provider_with(handler).generate_root_causes(CONTEXT, EVIDENCE)
    assert calls["n"] == 2 and out[0]["model_version"].startswith("gemini:")


@pytest.mark.asyncio
async def test_http_error_falls_back_and_never_leaks_key():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(403, json={"error": {"message": f"bad key {KEY}"}})

    provider = GeminiProvider(cfg(fallback_model="gemini-fallback-test"), transport=httpx.MockTransport(handler))
    out = await provider.generate_root_causes(CONTEXT, EVIDENCE)
    assert calls["n"] == 1                               # credentials errors cannot be fixed by another model
    assert out and all(c["model_version"].startswith("fallback-fake") for c in out)
    assert KEY not in out[0]["model_version"] and KEY not in (provider.last_error or "")
    assert "403" in provider.last_error


@pytest.mark.asyncio
async def test_daily_quota_is_not_retried_and_is_explained():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}})

    provider = provider_with(handler)
    out = await provider.generate_root_causes(CONTEXT, EVIDENCE)
    assert calls["n"] == 1                                         # no pointless retries
    assert "daily" in provider.last_error and out[0]["model_version"].startswith("fallback-fake")


@pytest.mark.asyncio
async def test_missing_key_falls_back():
    out = await GeminiProvider(cfg(key="")).generate_root_causes(CONTEXT, EVIDENCE)
    assert out[0]["model_version"].startswith("fallback-fake") and "GEMINI_API_KEY" in out[0]["model_version"]


@pytest.mark.asyncio
async def test_garbage_answer_falls_back():
    out = await provider_with(lambda r: httpx.Response(200, json=gemini_reply("not json at all"))).generate_root_causes(CONTEXT, EVIDENCE)
    assert out[0]["model_version"].startswith("fallback-fake")


# ---- pipeline + documents ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_standalone_rca_with_offline_provider_and_documents(tmp_path):
    from docx import Document

    from app.reports.rca_document import render_rca_documents
    from app.workflow.rca_pipeline import build_report, run_rca

    state = {"job_id": "rca_test", "part_master": {"part_number": "MS-4505-001", "part_name": "Bracket", "material": "SPCC Steel", "process": "bending"},
             "defects": [{"defect_type": "crack", "confidence": 0.9, "note": "9.7 mm long"}], "measurements": []}
    state = await run_rca(state, db=None)
    assert state["top3"] and state["top3"][0]["corrective_actions"] and state["top3"][0]["rationale"]

    report = build_report(state)
    paths = await render_rca_documents(report, out_dir=tmp_path, stem="rca_test")
    text = "\n".join(p.text for p in Document(paths["docx"]).paragraphs)
    assert "Reason:" in text and "Corrective actions" in text and report["root_cause"]["cause"] in text
    assert "Reason:" in open(paths["md"], encoding="utf-8").read()
    assert open(paths["pdf"], "rb").read(5) == b"%PDF-"
    assert "AI model was not used" in open(paths["md"], encoding="utf-8").read()    # offline output is labelled
