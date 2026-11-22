"""CLI entry point for a single CSV analysis session."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import sys
import time

from src.data.errors import DataToolError
from src.data.store import DatasetStore


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="具備 Tool Use / Planning 的智慧 CSV 資料分析 Agent")
    parser.add_argument("--csv", required=True, help="CSV 檔案路徑")
    parser.add_argument("--question", help="自然語言分析問題（--inspect-only 時可省略）")
    parser.add_argument("--inspect-only", action="store_true", help="離線讀取 CSV Schema，不呼叫 LLM")
    parser.add_argument("--trace-file", type=Path, help="將執行過程寫入本機 JSON 檔（包含分析資料摘要）")
    return parser


def format_terminal_answer(answer: str) -> str:
    """Remove common Markdown markup for readable plain-text terminal output.

    The original answer is retained unchanged in the structured JSON trace.
    """
    answer = re.sub(r"\*\*(.+?)\*\*", r"\1", answer, flags=re.DOTALL)
    answer = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", answer)
    return answer


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    started = time.monotonic()
    try:
        store = DatasetStore.from_csv(args.csv)
        if args.inspect_only:
            print(json.dumps(store.schema(), ensure_ascii=False, indent=2, allow_nan=False))
            return 0
        if not args.question:
            print("請提供 --question，或改用 --inspect-only。", file=sys.stderr)
            return 2
        # Defer provider imports: CSV inspection remains available without API packages.
        from src.config import AppConfig
        from src.llm.factory import create_llm
        from src.agent.graph import build_graph, run_analysis
        from src.llm.reliability import RetryPolicy

        config = AppConfig.from_env()
        graph = build_graph(
            create_llm(config), store, max_tool_calls=config.max_tool_calls,
            retry_policy=RetryPolicy(
                max_retries=config.llm_max_retries,
                base_delay_seconds=config.llm_retry_base_seconds,
            ),
        )
        result = run_analysis(graph, store, args.question, max_tool_calls=config.max_tool_calls)
        print(f"\n[狀態] {result.get('status', 'unknown')}\n")
        print(format_terminal_answer(result.get("answer", "沒有回答。")))
        print(
            f"\n工具呼叫：{result.get('tool_executions', 0)}，"
            f"成功：{result.get('successful_tools', 0)}，"
            f"失敗：{result.get('failed_tools', 0)}"
        )
        # Count API attempts separately from tool calls; one Tool Call may involve
        # several distinct model requests and/or bounded retry attempts.
        trace = result.get("trace", [])
        llm_calls = [e for e in trace if e.get("event") == "llm_call"]
        retry_count = sum(e.get("attempt", 1) > 1 for e in llm_calls)
        llm_seconds = sum(e.get("elapsed_seconds", 0.0) for e in llm_calls)
        tool_seconds = sum(e.get("elapsed_seconds", 0.0)
                           for e in trace if e.get("event") == "observation")
        print(f"LLM 請求次數：{len(llm_calls)}（其中重試 {retry_count} 次）")
        print(f"LLM 等待：{llm_seconds:.2f} 秒；工具執行：{tool_seconds:.4f} 秒")
        errors = [e for e in trace if e.get("event") == "error"]
        if errors:
            last = errors[-1]
            print(f"診斷：{last.get('code', 'UNKNOWN')}；"
                  f"原因：{last.get('cause', 'N/A')}；"
                  f"HTTP：{last.get('http_status') or 'N/A'}")
        if args.trace_file:
            # Never save API keys or provider's private thinking; only our structured trace.
            trace_doc = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "provider": config.provider,
                "model": config.model,
                "dataset_filename": Path(args.csv).name,
                "question": args.question,
                "schema": store.schema(),
                "plan": result.get("plan", ""),
                "status": result.get("status", "unknown"),
                "answer": result.get("answer", ""),
                "tool_executions": result.get("tool_executions", 0),
                "successful_tools": result.get("successful_tools", 0),
                "failed_tools": result.get("failed_tools", 0),
                "elapsed_seconds": round(time.monotonic() - started, 4),
                "trace_version": 2,
                "llm_request_attempts": len(llm_calls),
                "llm_retries": retry_count,
                "llm_elapsed_seconds": round(llm_seconds, 4),
                "tool_elapsed_seconds": round(tool_seconds, 4),
                "trace": trace,
            }
            args.trace_file.parent.mkdir(parents=True, exist_ok=True)
            args.trace_file.write_text(
                json.dumps(trace_doc, ensure_ascii=False, indent=2, default=str, allow_nan=False),
                encoding="utf-8",
            )
            print(f"執行紀錄：{args.trace_file}")
        return 0 if result.get("status") == "completed" else 1
    except DataToolError as exc:
        print(f"資料錯誤 [{exc.code}]：{exc.message}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"設定錯誤：{exc}", file=sys.stderr)
        return 2
    except (OSError, PermissionError) as exc:
        print(f"檔案操作失敗：{type(exc).__name__}", file=sys.stderr)
        return 2
    except Exception as exc:
        # Fail closed: avoid dumping SDK internals / accidental credentials in a traceback.
        print(
            f"執行失敗 [{type(exc).__name__}]：請檢查 README 中的套件版本、"
            "模型設定、API 配額與執行環境。",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
