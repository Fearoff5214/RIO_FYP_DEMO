"""OpenAI LLM provider."""
from __future__ import annotations

import json


class OpenAIProvider:
    def __init__(self, cfg):
        self.cfg = cfg

    async def generate_root_causes(self, context: dict, evidence: dict, regenerate: bool = False) -> list[dict]:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.cfg.settings.openai_api_key)
            model = self.cfg.get("prediction", "llm", "model") or "gpt-4o"
            temp = float(self.cfg.get("prediction", "llm", "temperature") or 0.2)
            max_tokens = int(self.cfg.get("prediction", "llm", "max_tokens") or 2000)

            system = (
                "You are a quality engineering expert. Output ONLY valid JSON with schema: "
                '{"candidates":[{"cause":"...","rationale":"...","effect":"...","precautions":["..."],"citations":["id"]}]}'
            )
            user = f"Defects: {context.get('defects')}. Evidence: {evidence.get('sources', [])[:5]}"

            resp = await client.chat.completions.create(
                model=model,
                temperature=temp,
                max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            data = json.loads(resp.choices[0].message.content)
            return data.get("candidates", [])
        except Exception:
            from app.llm.providers.fake import FakeLLMProvider
            return await FakeLLMProvider().generate_root_causes(context, evidence, regenerate)
