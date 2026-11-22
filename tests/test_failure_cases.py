"""Verify deterministic failure evidence; no OpenAI API calls or API key required."""
import pytest
pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")

from scripts.failure_cases import CASES, run_case, make_markdown


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_failure_case_observation_and_clarification(case, sales_store):
    # Use the common actual CSV fixture, not an in-memory fabricated table.
    from pathlib import Path
    csv_path = Path(__file__).resolve().parents[1] / "data" / "sample_sales.csv"
    evidence = run_case(case, csv_path)
    assert evidence["passed"], evidence["checks"]
    assert evidence["observed_failure_codes"] == [case["expected_error"]]
    assert "Scripted" not in evidence["agent_answer"]


def test_failure_evidence_report_discloses_simulation():
    report = make_markdown([{
        "case_id": "FX", "case_name": "示範", "question": "Q", "expected_error": "ERR",
        "injected_tool_call": {"tool": "inspect_dataset", "args": {}},
        "observed_failure_codes": ["ERR"], "root_cause": "CAUSE", "resolution": "FIX",
        "agent_status": "needs_clarification", "successful_tools": 0, "failed_tools": 1,
        "passed": True, "agent_answer": "無法計算",
    }])
    assert "不是真實 OpenAI API 測試" in report
    assert "FX" in report
