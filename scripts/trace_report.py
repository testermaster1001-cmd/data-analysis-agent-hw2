"""Offline summary of a JSON Agent trace with sensitive content omitted.

Only prints event types, durations and registered tool names. Does not echo
source rows, prompts, tool arguments, or the natural-language answer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def summarize_trace(doc: dict) -> str:
    events = doc.get("trace", [])
    llm_events = [e for e in events if e.get("event") == "llm_call"]
    observations = [e for e in events if e.get("event") == "observation"]
    retries = sum(e.get("attempt", 1) > 1 for e in llm_events)
    lines = [
        f"狀態：{doc.get('status', 'unknown')}",
        f"模型：{doc.get('provider', '?')} / {doc.get('model', '?')}",
        f"工具：{doc.get('tool_executions', 0)} 次；成功 {doc.get('successful_tools', 0)}；失敗 {doc.get('failed_tools', 0)}",
        f"總耗時：{doc.get('elapsed_seconds', '?')} 秒",
        f"LLM 請求：{len(llm_events)} 次；重試：{retries} 次",
        "=== 精簡流程（不列出資料列、金鑰或工具參數） ===",
    ]
    for e in events:
        kind = e.get("event")
        if kind == "llm_call":
            desc = f"LLM {e.get('stage')} 第 {e.get('attempt')} 次：{e.get('status')}，耗時 {e.get('elapsed_seconds')}s"
            if e.get("status") == "error":
                error = e.get("error") or {}
                desc += f"（{error.get('code')}, HTTP {error.get('http_status')}）"
            lines.append(desc)
        elif kind == "decision":
            tools = [a.get("tool") for a in e.get("actions", [])]
            lines.append(f"Decision：{tools}")
        elif kind == "observation":
            lines.append(f"Observation：{e.get('tool')}，ok={e.get('result', {}).get('ok')}，{e.get('elapsed_seconds', '?')}s")
        elif kind == "error":
            lines.append(f"Error：{e.get('code')}，原因 {e.get('cause', '?')}，HTTP {e.get('http_status', '?')}")
        elif kind in {"plan", "final"}:
            lines.append(kind)
    if observations and not llm_events:
        lines.append("注意：舊版 Trace 沒有 LLM 單次耗時事件，這裡不代表未呼叫模型。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="離線彙整 HW2 Agent Trace（不需要 API Key）")
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    try:
        doc = json.loads(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Trace 讀取失敗：{type(exc).__name__}")
        return 2
    if not isinstance(doc, dict):
        print("Trace 格式錯誤：根節點必須是 JSON Object")
        return 2
    print(summarize_trace(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
