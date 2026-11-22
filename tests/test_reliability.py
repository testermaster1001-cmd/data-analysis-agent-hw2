"""Deterministic LLM retry tests; these never call Gemini or OpenAI."""

import pytest

from src.llm.reliability import RetryPolicy, classify_llm_error, invoke_with_retry


class HTTPFailure(Exception):
    def __init__(self, status_code, secret="SENSITIVE-API-KEY-DO-NOT-LOG"):
        super().__init__(f"provider failure {status_code}: {secret}")
        self.code = status_code


class SequenceModel:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value


def test_503_retry_then_success_without_extra_calls():
    model = SequenceModel([HTTPFailure(503), HTTPFailure(503), "RESULT"])
    delays = []
    output = invoke_with_retry(
        model, [], stage="decision", policy=RetryPolicy(2, 1.0, 8.0),
        sleeper=delays.append,
    )
    assert output.response == "RESULT"
    assert output.failure is None
    assert output.attempts == 3
    assert model.calls == 3
    assert delays == [1.0, 2.0]
    assert [e["status"] for e in output.events] == ["error", "error", "success"]
    assert output.events[0]["error"]["http_status"] == 503


def test_503_stops_after_limit_and_no_raw_exception_leak():
    model = SequenceModel([HTTPFailure(503), HTTPFailure(503), HTTPFailure(503)])
    output = invoke_with_retry(model, [], stage="planner", policy=RetryPolicy(2, 0, 0))
    assert output.response is None
    assert output.failure.code == "SERVICE_UNAVAILABLE"
    assert output.attempts == 3
    assert "SENSITIVE-API-KEY" not in str(output.events)
    assert "SENSITIVE-API-KEY" not in output.failure.user_message
    assert output.events[-1]["retry_delay_seconds"] == 0


@pytest.mark.parametrize("status,expected", [
    (429, "RATE_LIMITED"), (401, "AUTHENTICATION_FAILED"),
    (403, "PERMISSION_DENIED"), (404, "MODEL_NOT_FOUND"),
    (400, "INVALID_REQUEST"),
])
def test_nontransient_status_never_retry(status, expected):
    model = SequenceModel([HTTPFailure(status)])
    delays = []
    output = invoke_with_retry(model, [], stage="decision", policy=RetryPolicy(4), sleeper=delays.append)
    assert model.calls == 1
    assert not delays
    assert output.failure.code == expected
    assert output.events[0]["error"]["retryable"] is False


def test_timeout_classification_and_retry():
    model = SequenceModel([TimeoutError("secret details"), "ready"])
    output = invoke_with_retry(model, [], stage="planner", policy=RetryPolicy(1, 0, 0))
    assert output.response == "ready"
    assert output.events[0]["error"]["code"] == "REQUEST_TIMEOUT"


def test_unknown_exception_is_not_retried_or_exposed():
    output = invoke_with_retry(
        SequenceModel([RuntimeError("secret prompt and API key")]), [],
        stage="planner", policy=RetryPolicy(2),
    )
    assert output.failure.code == "UNKNOWN_LLM_ERROR"
    assert "secret" not in str(output.events)


def test_elapsed_seconds_per_attempt_is_nonnegative():
    model = SequenceModel(["hello"])
    output = invoke_with_retry(model, [], stage="planner")
    assert output.events[0]["elapsed_seconds"] >= 0
    assert output.events[0]["stage"] == "planner"
    assert output.events[0]["status"] == "success"


def test_response_status_field_is_understood():
    class Error(Exception):
        def __init__(self):
            self.response = type("Response", (), {"status_code": 502})()
    err = classify_llm_error(Error())
    assert err.http_status == 502
    assert err.retryable


def test_retry_policy_rejects_unbounded_settings():
    with pytest.raises(ValueError):
        RetryPolicy(max_retries=100)
    with pytest.raises(ValueError):
        RetryPolicy(base_delay_seconds=-1)
    with pytest.raises(ValueError):
        RetryPolicy(max_delay_seconds=1000)


def test_invalid_stage_rejected_without_request():
    model = SequenceModel(["data"])
    with pytest.raises(ValueError):
        invoke_with_retry(model, [], stage="unknown")
    assert model.calls == 0
