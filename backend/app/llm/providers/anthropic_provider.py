"""Anthropic Claude LLM provider."""
from __future__ import annotations

import json
from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "root_cause.md"


class AnthropicProvider:
    def __init__(self, cfg):
        self.cfg = cfg

    async def generate_root_causes(
        self,
        context: dict,
        evidence: dict,
        regenerate: bool = False,
    ) -> list[dict]:
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.cfg.settings.anthropic_api_key)
            system_prompt = _load_system_prompt()
            user_message = _build_user_message(context, evidence, regenerate)

            model = self.cfg.get("prediction", "llm", "model") or "claude-3-5-sonnet-20241022"
            temp = float(self.cfg.get("prediction", "llm", "temperature") or 0.2)
            max_tokens = int(self.cfg.get("prediction", "llm", "max_tokens") or 2000)

            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temp,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            text = response.content[0].text
            data = json.loads(text)
            return data.get("candidates", [])

        except Exception as e:
            from app.core.logging import get_logger
            get_logger(__name__).error('"llm_error":"%s"', str(e))
            from app.llm.providers.fake import FakeLLMProvider
            return await FakeLLMProvider().generate_root_causes(context, evidence, regenerate)


def _load_system_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text()
    return (
        "You are a quality engineering expert. "
        "Analyze the provided defects and evidence to identify root causes. "
        "Output ONLY valid JSON with the schema: "
        '{"candidates":[{"cause":"...","rationale":"...","effect":"...","precautions":["..."],"citations":["chunk_id"]}]}'
    )


def _build_user_message(context: dict, evidence: dict, regenerate: bool) -> str:
    sources_text = "\n".join(
        f"[{s['chunk_id']}]: {s['text_excerpt']}"
        for s in evidence.get("sources", [])[:10]
    )
    return (
        f"Part: {context.get('part_number')} ({context.get('part_name')})\n"
        f"Material: {context.get('material')}, Process: {context.get('process')}\n"
        f"Defects detected: {context.get('defects')}\n"
        f"Out-of-tolerance features: {context.get('out_of_tolerance')}\n\n"
        f"Evidence from knowledge base:\n{sources_text}\n\n"
        f"{'IMPORTANT: Previous output was invalid. Please regenerate with strict citations.' if regenerate else ''}\n"
        "Output 3 root cause candidates in the required JSON format."
    )
