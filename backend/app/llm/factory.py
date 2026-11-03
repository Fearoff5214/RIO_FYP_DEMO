"""LLM provider factory."""
from __future__ import annotations

from app.core.config import get_config


def resolve_provider_name(cfg) -> str:
    """Provider choice: env NOVALISEO_LLM_PROVIDER, else prediction.llm.provider; 'auto' = gemini if a key is set."""
    name = (cfg.settings.novaliseo_llm_provider or cfg.get("prediction", "llm", "provider") or "auto").strip().lower()
    if name == "auto":
        return "gemini" if (cfg.settings.gemini_api_key or "").strip() else "fake"
    return name


def get_llm_provider(cfg=None):
    """Return the configured LLM provider. The choice no longer depends on mock mode:
    set a key (or a provider) and AI root cause analysis is used; set `fake` to force the offline fake."""
    if cfg is None:
        cfg = get_config()

    name = resolve_provider_name(cfg)

    if name == "gemini":
        from app.llm.providers.gemini_provider import GeminiProvider
        return GeminiProvider(cfg)
    if name == "anthropic":
        from app.llm.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(cfg)
    if name == "openai":
        from app.llm.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(cfg)

    from app.llm.providers.fake import FakeLLMProvider
    return FakeLLMProvider()
