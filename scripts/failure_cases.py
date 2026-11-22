"""Reproducible HW2 failure evidence using a scripted LLM and real LangGraph/tools.

This program makes NO external API calls. It exercises the production workflow and
actual pandas tools while predefining model responses. It does NOT measure a real
OpenAI model's accuracy or spontaneous error recovery.

Run at project root:
    python scripts/failure_cases.py
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

# Running `python scripts/failure_cases.py` sets sys.path[0] to `scripts`.
# Make imports reliable without assuming an editable package installation.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_core.messages import AIMessage

from src.agent.graph import build_graph, run_analysis
from src.data.store import DatasetStore
from src.llm.reliability import RetryPolicy


class ScriptedLLM:
    """Minimal deterministic substitute for decision outputs, never a live model."""

    def __init__(self, messages: list[AIMessage]):
        self._messages = iter(messages)

    def bind_tools(self, tools: Any) -> "ScriptedLLM":
        return self

    def invoke(self, messages: Any) -> AIMessage:
        try:
            return next(self._messages)
        except StopIteration as exc:
            raise AssertionError("ScriptedLLM ran out of planned responses") from exc


def _model_tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


CASES = (
    {
        "id": "F01",
        "name": "欄位不存在",
        "question": "請計算 Money 欄位的平均值。",
        "tool": "calculate_statistics",
        "tool_args": {"column": "Money", "operation": "mean", "source_id": "dataset"},
        "expected_error": "COLUMN_NOT_FOUND",
        "expected_response": "CSV 沒有 Money 欄位。請確認要分析哪個欄位；不能擅自將 Money 當成 Revenue。",
        "root_cause": "CSV Schema 沒有 Money 欄；不能推定 Money 與 Revenue 同義。",
        "resolution": "回報缺少欄位，要求使用者確認實際欄位名稱。",
    },
    {
        "id": "F02",
        "name": "非數值欄位求平均",
        "question": "請計算 Category 欄位的平均值。",
        "tool": "calculate_statistics",
        "tool_args": {"column": "Category", "operation": "mean", "source_id": "dataset"},
        "expected_error": "TYPE_MISMATCH",
        "expected_response": "Category 是文字分類欄位，不能計算數值平均；請改用數值欄位。",
        "root_cause": "Category 是文字型別（object），不符合 mean 運算需要數值的條件。",
        "resolution": "回報資料型態不符，要求改用數值欄位或其他適合的統計方式。",
    },
)


def run_case(case: dict[str, Any], csv_path: Path) -> dict[str, Any]:
    """Run one graph with intentionally invalid tool args and validate its trace."""
    store = DatasetStore.from_csv(csv_path)
    model = ScriptedLLM([
        AIMessage(content="先依照使用者指定的欄位嘗試計算，遇到錯誤則回報。"),
        _model_tool_call(case["tool"], case["tool_args"], f"case-{case['id']}"),
        AIMessage(content=case["expected_response"]),
    ])
    output = run_analysis(
        build_graph(model, store, retry_policy=RetryPolicy(max_retries=0)),
        store,
        case["question"],
    )
    observations = [e for e in output.get("trace", []) if e.get("event") == "observation"]
    failure_codes = [
        e.get("result", {}).get("error", {}).get("code")
        for e in observations if e.get("result", {}).get("ok") is False
    ]
    checks = {
        "tool_call_was_executed": output.get("tool_executions") == 1,
        "tool_error_returned": failure_codes == [case["expected_error"]],
        "no_successful_data_tool": output.get("successful_tools") == 0,
        "failure_count_is_one": output.get("failed_tools") == 1,
        "did_not_claim_completed": output.get("status") != "completed",
        "answer_indicates_uncertainty": "未經數值驗證" in output.get("answer", ""),
    }
    doc = {
        "case_id": case["id"],
        "case_name": case["name"],
        "test_type": "offline_scripted_llm_langgraph_real_pandas_tools",
        "is_live_openai_test": False,
        "dataset": csv_path.name,
        "question": case["question"],
        "injected_tool_call": {"tool": case["tool"], "args": case["tool_args"]},
        "expected_error": case["expected_error"],
        "observed_failure_codes": failure_codes,
        "root_cause": case["root_cause"],
        "resolution": case["resolution"],
        "agent_status": output.get("status"),
        "agent_answer": output.get("answer"),
        "tool_executions": output.get("tool_executions"),
        "successful_tools": output.get("successful_tools"),
        "failed_tools": output.get("failed_tools"),
        "trace": output.get("trace", []),
        "checks": checks,
        "passed": all(checks.values()),
    }
    return doc


def make_markdown(results: list[dict[str, Any]]) -> str:
    """Write a readable report with explicit test-method limitations."""
    lines = [
        "# HW2 Failure Cases — 可重現執行證據",
        "",
        "**測試方法：** 使用 ScriptedLLM 預先指定模型的工具呼叫與回覆；",
        "實際執行的是正式 LangGraph Workflow 和 pandas Tool。**不是真實 OpenAI API 測試。**",
        "所有測試資料為專案附帶的模擬 CSV，沒有真實個資。",
        "",
    ]
    for doc in results:
        lines.extend([
            f"## {doc['case_id']}：{doc['case_name']}",
            "",
            f"- 使用者輸入：{doc['question']}",
            f"- 指定 Tool：`{doc['injected_tool_call']['tool']}`",
            f"- Tool Arguments：`{json.dumps(doc['injected_tool_call']['args'], ensure_ascii=False)}`",
            f"- 預期錯誤代碼：`{doc['expected_error']}`",
            f"- 實際錯誤代碼：`{', '.join(doc['observed_failure_codes']) or '無'}`",
            f"- 根本原因：{doc['root_cause']}",
            f"- 處理方法：{doc['resolution']}",
            f"- Agent 最終狀態：`{doc['agent_status']}`",
            f"- 工具成功 / 失敗：{doc['successful_tools']} / {doc['failed_tools']}",
            f"- 驗證結果：{'PASS' if doc['passed'] else 'FAIL'}",
            "",
            "**Agent 回覆：**",
            "",
            "> " + doc['agent_answer'].replace("\n", "\n> "),
            "",
            f"詳細逐步紀錄：`{doc['case_id'].lower()}_trace.json`。",
            "",
        ])
    lines.extend([
        "## 執行指令與限制",
        "",
        "在專案根目錄執行 `python scripts/failure_cases.py`，產生本報告與每個測試的 JSON Trace。",
        "上述測試只證明正式 Graph 與資料工具遇到指定錯誤時的處理，不能用來宣稱 GPT-5.4 mini",
        "在真實自然語言提問中一定會先呼叫錯誤工具。實際模型可能先依 Schema 要求確認，這也是合理的防錯處理。",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成可重現的兩個 HW2 Failure Cases 證據（不呼叫 API）")
    parser.add_argument("--csv", type=Path, default=ROOT / "data" / "sample_sales.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "documents" / "evidence" / "failure_cases")
    args = parser.parse_args(argv)
    results = [run_case(case, args.csv) for case in CASES]
    args.out.mkdir(parents=True, exist_ok=True)
    for doc in results:
        (args.out / f"{doc['case_id'].lower()}_trace.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
    (args.out / "failure_cases_report.md").write_text(
        make_markdown(results), encoding="utf-8"
    )
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "simulation_only": True,
        "case_results": [{"id": r["case_id"], "passed": r["passed"]} for r in results],
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for doc in results:
        print(f"{doc['case_id']}: {'PASS' if doc['passed'] else 'FAIL'} "
              f"| {doc['expected_error']} | status={doc['agent_status']} "
              f"| tools={doc['tool_executions']}")
    print(f"證據輸出目錄：{args.out}")
    return 0 if all(doc["passed"] for doc in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
