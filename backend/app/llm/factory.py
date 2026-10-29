"""LLM provider factory."""
from __future__ import annotations

from app.core.config import get_config


def get_llm_provider(cfg=None):
    """Return the configured LLM provider."""
    if cfg is None:
        cfg = get_config()

    provider_name = cfg.get("prediction", "llm", "provider") or "fake"

    if provider_name == "fake" or cfg.is_mock:
        from app.llm.providers.fake import FakeLLMProvider
        return FakeLLMProvider()
    elif provider_name == "anthropic":
        from app.llm.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(cfg)
    elif provider_name == "openai":
        from app.llm.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(cfg)
    else:
        from app.llm.providers.fake import FakeLLMProvider
        return FakeLLMProvider()
