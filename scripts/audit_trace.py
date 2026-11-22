"""Validate a structured Agent trace's result-handle provenance without API calls.

This audit establishes whether source IDs refer to earlier successful tool results.
It does NOT prove that arbitrary final natural-language statements are correct.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


KNOWN_TOOLS = {
    "inspect_dataset", "calculate_statistics", "filter_data",
    "group_and_aggregate", "sort_and_rank",
}


def audit_trace(doc: dict[str, Any]) -> dict[str, Any]:
    events = doc.get("trace", [])
    if not isinstance(events, list):
        raise ValueError("Trace 的 trace 欄位必須為陣列。")
    known: set[str] = {"dataset"}
    observations: list[dict[str, Any]] = []
    issues: list[str] = []
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict) or event.get("event") != "observation":
            continue
        tool = event.get("tool")
        if tool not in KNOWN_TOOLS:
            issues.append(f"事件 {index}：未知 Tool {tool!r}")
        arguments = event.get("args", {})
        arguments = arguments if isinstance(arguments, dict) else {}
        source_id = arguments.get("source_id", "dataset")
        if source_id not in known:
            issues.append(f"事件 {index}：引用不存在或尚未產生的 source_id {source_id!r}")
        result = event.get("result", {})
        result = result if isinstance(result, dict) else {}
        ok = result.get("ok") is True
        data = result.get("data", {})
        data = data if isinstance(data, dict) else {}
        result_id = data.get("result_id") if ok else None
        if result_id is not None:
            if not isinstance(result_id, str) or not result_id:
                issues.append(f"事件 {index}：result_id 格式錯誤")
            elif result_id in known:
                issues.append(f"事件 {index}：重複的 result_id {result_id!r}")
            else:
                known.add(result_id)
        observations.append({
            "tool": tool,
            "source_id": source_id,
            "result_id": result_id,
            "ok": ok,
            "rows": data.get("rows", data.get("sample_rows", [])),
        })
    if doc.get("tool_executions") != len(observations):
        issues.append("tool_executions 與 Observation 數量不一致")
    successes = sum(o["ok"] for o in observations)
    if doc.get("successful_tools") != successes:
        issues.append("successful_tools 與 Observation 成功數不一致")
    if doc.get("failed_tools") != len(observations) - successes:
        issues.append("failed_tools 與 Observation 失敗數不一致")
    if doc.get("status") == "completed":
        for required in ("plan", "decision", "final"):
            if not any(isinstance(e, dict) and e.get("event") == required for e in events):
                issues.append(f"Completed Trace 缺少 {required!r} 事件")
        if successes == 0:
            issues.append("Completed Trace 沒有成功工具")
    return {
        "passed": not issues,
        "issues": issues,
        "known_sources": sorted(known),
        "observations": observations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="離線稽核 Agent Trace 的資料來源與工具計數")
    parser.add_argument("trace", type=Path, help="由 --trace-file 產生的 JSON")
    args = parser.parse_args(argv)
    try:
        doc = json.loads(args.trace.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("Trace 必須為 JSON 物件")
        report = audit_trace(doc)
    except (OSError, ValueError) as exc:
        print(f"無法稽核 Trace：{type(exc).__name__}")
        return 2
    for item in report["observations"]:
        print(f"{item['tool']}: {item['source_id']} -> {item['result_id'] or '-'} "
              f"(ok={item['ok']})")
    print("Source references:", ", ".join(report["known_sources"]))
    if report["issues"]:
        for issue in report["issues"]:
            print("ERROR:", issue)
    print("AUDIT PASS" if report["passed"] else "AUDIT FAIL")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
