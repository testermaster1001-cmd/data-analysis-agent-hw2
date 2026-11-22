import pytest
from src.config import AppConfig


@pytest.mark.parametrize("key,value", [
    ("LLM_MAX_RETRIES", "6"),
    ("LLM_MAX_RETRIES", "abc"),
    ("LLM_RETRY_BASE_SECONDS", "-1"),
    ("LLM_TIMEOUT_SECONDS", "not-a-number"),
])
def test_rejects_invalid_retry_env(monkeypatch, key, value):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "TEST-KEY")
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        AppConfig.from_env()


def test_accepts_valid_retry_configuration(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "TEST-KEY")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("LLM_RETRY_BASE_SECONDS", "2.0")
    config = AppConfig.from_env()
    assert config.llm_max_retries == 2
    assert config.llm_retry_base_seconds == 2
