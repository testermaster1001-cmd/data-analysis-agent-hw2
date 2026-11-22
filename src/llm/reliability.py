"""Safe LLM failure classification, bounded retries and per-attempt timing.

The provider's exception text may include secrets, prompts or user data. Never
persist ``str(exc)``: only stable, allowlisted error codes and HTTP statuses.

Retry policy applies to LLM calls only, never to pandas tools. We retry only
likely transient 5xx/timeout/network errors; a 429 may mean exhausted free-tier
quota, so automatic retries are intentionally disabled for 429.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable


@dataclass(frozen=True)
class LLMFailure:
    code: str
    http_status: int | None
    retryable: bool
    user_message: str

    def to_trace(self) -> dict[str, Any]:
        """Return a bounded, secret-free public diagnostic record."""
        return {"code": self.code, "http_status": self.http_status, "retryable": self.retryable}


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 1.5
    max_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if not 0 <= self.max_retries <= 4:
            raise ValueError("max_retries must be between 0 and 4")
        if not 0 <= self.base_delay_seconds <= 10:
            raise ValueError("base_delay_seconds must be between 0 and 10")
        if not 0 <= self.max_delay_seconds <= 30:
            raise ValueError("max_delay_seconds must be between 0 and 30")

    def delay_for_retry(self, retry_index: int) -> float:
        """retry_index = 1 for the first retry, 2 for the second, etc."""
        return min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (retry_index - 1)))


@dataclass
class LLMCallResult:
    response: Any | None
    events: list[dict[str, Any]]
    attempts: int
    failure: LLMFailure | None = None


def _http_status(exc: Exception) -> int | None:
    """Read structured status fields only; never parse or disclose error text."""
    response = getattr(exc, "response", None)
    for value in (
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        getattr(exc, "http_status", None),
        getattr(response, "status_code", None),
    ):
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and 100 <= value <= 599:
            return value
        if isinstance(value, str) and value.isascii() and value.isdigit():
            parsed = int(value)
            if 100 <= parsed <= 599:
                return parsed
    return None


def classify_llm_error(exc: Exception) -> LLMFailure:
    """Classify known API failures using structured status and safe class names."""
    status = _http_status(exc)
    if status in {500, 502, 503, 504}:
        return LLMFailure("SERVICE_UNAVAILABLE", status, True, "模型服務暫時無法使用，已停止本次分析。")
    if status == 429:
        return LLMFailure("RATE_LIMITED", status, False, "API 請求頻率或額度達上限，請檢查模型配額。")
    if status == 401:
        return LLMFailure("AUTHENTICATION_FAILED", status, False, "API 身分驗證失敗，請檢查 API Key。")
    if status == 403:
        return LLMFailure("PERMISSION_DENIED", status, False, "API 專案沒有權限使用指定模型。")
    if status == 404:
        return LLMFailure("MODEL_NOT_FOUND", status, False, "指定模型或 API 端點不存在。")
    if status == 408:
        return LLMFailure("REQUEST_TIMEOUT", status, True, "模型請求逾時。")
    if status == 400:
        return LLMFailure("INVALID_REQUEST", status, False, "LLM 請求格式或參數無效。")

    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError) or any(t in name for t in ("timeout", "deadlineexceeded")):
        return LLMFailure("REQUEST_TIMEOUT", status, True, "模型請求逾時。")
    if isinstance(exc, ConnectionError) or any(t in name for t in ("connectionerror", "connecterror", "networkerror")):
        return LLMFailure("NETWORK_ERROR", status, True, "無法連線到模型服務。")
    if "ratelimit" in name or "resourceexhausted" in name:
        return LLMFailure("RATE_LIMITED", status, False, "API 請求頻率或額度達上限，請檢查模型配額。")
    if "authentication" in name or "unauthorized" in name:
        return LLMFailure("AUTHENTICATION_FAILED", status, False, "API 身分驗證失敗，請檢查 API Key。")
    return LLMFailure("UNKNOWN_LLM_ERROR", status, False, "模型呼叫失敗，請查看安全診斷紀錄。")


def invoke_with_retry(
    model: Any,
    messages: list[Any],
    *,
    stage: str,
    policy: RetryPolicy | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> LLMCallResult:
    """Invoke model and record one sanitized timing event per request attempt.

    Does not retry on unsupported model/auth/quota/validation errors. An
    exception is captured into safe metadata; the full exception is discarded.
    """
    retry_policy = policy or RetryPolicy()
    if stage not in {"planner", "decision"}:
        raise ValueError("Unknown LLM call stage")
    events: list[dict[str, Any]] = []
    for attempt in range(1, retry_policy.max_retries + 2):
        started = clock()
        try:
            response = model.invoke(messages)
        except Exception as exc:
            failure = classify_llm_error(exc)
            can_retry = failure.retryable and attempt <= retry_policy.max_retries
            delay = retry_policy.delay_for_retry(attempt) if can_retry else 0.0
            events.append({
                "event": "llm_call",
                "stage": stage,
                "attempt": attempt,
                "status": "error",
                "elapsed_seconds": round(max(0.0, clock() - started), 4),
                "error": failure.to_trace(),
                "retry_delay_seconds": delay,
            })
            if not can_retry:
                return LLMCallResult(None, events, attempt, failure)
            sleeper(delay)
        else:
            events.append({
                "event": "llm_call",
                "stage": stage,
                "attempt": attempt,
                "status": "success",
                "elapsed_seconds": round(max(0.0, clock() - started), 4),
            })
            return LLMCallResult(response, events, attempt)
    raise AssertionError("Unreachable retry control flow")
