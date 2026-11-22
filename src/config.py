"""Explicit, validated application configuration. Secrets are never logged."""
from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    provider: str
    model: str
    api_key: str
    max_tool_calls: int = 8
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 2
    llm_retry_base_seconds: float = 1.5

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
        if provider not in {"gemini", "openai"}:
            raise ValueError("LLM_PROVIDER 僅能設定為 gemini 或 openai。")
        default_model = "gemini-3.6-flash" if provider == "gemini" else "gpt-5.4-mini"
        model = os.getenv("LLM_MODEL", default_model).strip()
        if not model:
            raise ValueError("LLM_MODEL 不可為空。")
        key_name = "GOOGLE_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
        api_key = os.getenv(key_name, "").strip()
        if not api_key or api_key.startswith("replace_"):
            raise ValueError(f"請在 .env 中提供 {key_name}；不要把金鑰上傳到 GitHub。")
        try:
            max_calls = int(os.getenv("MAX_TOOL_CALLS", "8"))
            timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
            retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
            base_delay = float(os.getenv("LLM_RETRY_BASE_SECONDS", "1.5"))
        except ValueError as exc:
            raise ValueError("LLM timeout／retries／delay 與工具限制必須為數字。") from exc
        if not 1 <= max_calls <= 20:
            raise ValueError("MAX_TOOL_CALLS 必須介於 1～20。")
        if not 5 <= timeout <= 180:
            raise ValueError("LLM_TIMEOUT_SECONDS 必須介於 5～180 秒。")
        if not 0 <= retries <= 4:
            raise ValueError("LLM_MAX_RETRIES 必須介於 0～4。")
        if not 0 <= base_delay <= 10:
            raise ValueError("LLM_RETRY_BASE_SECONDS 必須介於 0～10。")
        return cls(provider, model, api_key, max_calls, timeout, retries, base_delay)
