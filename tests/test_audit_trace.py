from scripts.audit_trace import audit_trace


def _case():
    return {
        "status": "completed", "tool_executions": 2,
        "successful_tools": 2, "failed_tools": 0,
        "trace": [
            {"event": "plan", "summary": "Group and rank"},
            {"event": "decision", "actions": []},
            {"event": "observation", "tool": "group_and_aggregate", "args": {"source_id": "dataset"},
             "result": {"ok": True, "data": {"result_id": "result_001"}}},
            {"event": "decision", "actions": []},
            {"event": "observation", "tool": "sort_and_rank", "args": {"source_id": "result_001"},
             "result": {"ok": True, "data": {"result_id": "result_002"}}},
            {"event": "final", "status": "completed"},
        ],
    }


def test_audit_valid_trace():
    result = audit_trace(_case())
    assert result["passed"]
    assert "result_002" in result["known_sources"]


def test_audit_unknown_source():
    trace = _case()
    trace["trace"][4]["args"]["source_id"] = "result_999"
    result = audit_trace(trace)
    assert not result["passed"]
    assert "result_999" in str(result["issues"])


def test_audit_mismatched_counts():
    trace = _case()
    trace["successful_tools"] = 1
    assert not audit_trace(trace)["passed"]


def test_audit_duplicate_result_id():
    trace = _case()
    trace["trace"][4]["result"]["data"]["result_id"] = "result_001"
    assert not audit_trace(trace)["passed"]
