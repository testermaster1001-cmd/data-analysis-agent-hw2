from scripts.trace_report import summarize_trace


def test_summary_v2_skips_raw_data_and_has_retries():
    doc = {
        "status": "error", "provider": "gemini", "model": "a-model",
        "tool_executions": 1, "successful_tools": 1, "failed_tools": 0,
        "elapsed_seconds": 3.5,
        "trace": [
            {"event": "llm_call", "stage": "planner", "status": "error", "attempt": 1, "elapsed_seconds": 0.2, "error": {"code": "SERVICE_UNAVAILABLE", "http_status": 503}},
            {"event": "llm_call", "stage": "planner", "status": "success", "attempt": 2, "elapsed_seconds": 0.4},
            {"event": "decision", "actions": [{"tool": "filter_data", "args": {"value": "PRIVATE CELL VALUE"}}]},
            {"event": "observation", "tool": "filter_data", "result": {"ok": True, "data": {"secret": "PRIVATE CELL VALUE"}}},
            {"event": "error", "code": "LLM_AGENT_FAILED", "cause": "SERVICE_UNAVAILABLE", "http_status": 503},
        ],
    }
    summary = summarize_trace(doc)
    assert "503" in summary
    assert "重試：1 次" in summary
    assert "filter_data" in summary
    assert "PRIVATE CELL VALUE" not in summary


def test_old_trace_remains_readable():
    output = summarize_trace({"trace": [{"event": "observation", "tool": "inspect_dataset", "result": {"ok": True}}]})
    assert "舊版 Trace" in output
