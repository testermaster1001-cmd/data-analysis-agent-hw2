"""Provider initialization only; graph layer owns explicit retry/timing trace."""
from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from src.config import AppConfig


def create_llm(config: AppConfig) -> BaseChatModel:
    if config.provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=config.model,
            api_key=config.api_key,
            vertexai=False,
            # Use the provider default sampling configuration.
            timeout=config.llm_timeout_seconds,
            max_retries=0,  # Graph owns the bounded retry strategy and trace.
        )
    if config.provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=config.model,
            api_key=config.api_key,
            timeout=config.llm_timeout_seconds,
            max_retries=0,  # Graph owns the bounded retry strategy and trace.
        )
    raise ValueError(f"Unsupported LLM provider: {config.provider}")
