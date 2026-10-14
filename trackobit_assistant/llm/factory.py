from typing import Any
from trackobit_assistant.config.settings import Settings

def create_chat_model(settings: Settings, *, vision: bool = False) -> Any | None:
    """Return the configured LangChain chat model, or None for deterministic local demo mode."""
    provider = settings.llm_provider.strip().casefold()
    if provider in {'mock', 'none', ''}:
        return None
    if provider == 'openai':
        if not settings.openai_api_key:
            return None
        from langchain_openai import ChatOpenAI
        model = settings.openai_vision_model if vision else settings.openai_model
        return ChatOpenAI(model=model, api_key=settings.openai_api_key, temperature=0)
    if provider == 'anthropic':
        if not settings.anthropic_api_key:
            return None
        from langchain_anthropic import ChatAnthropic
        model = settings.anthropic_vision_model if vision else settings.anthropic_model
        return ChatAnthropic(model=model, api_key=settings.anthropic_api_key, temperature=0)
    raise ValueError(f'Unsupported LLM_PROVIDER={settings.llm_provider!r}; configure a provider in llm/factory.py')
