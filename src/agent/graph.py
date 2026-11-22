"""Planning -> decision -> Tool -> observation -> decision LangGraph workflow.

Calculations are delegated to tools, while model-written answers still require
independent evaluation. Native AIMessage and ToolMessage objects are preserved
so provider-specific tool metadata remains available.
"""
from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from src.agent.prompts import PLANNER_SYSTEM, agent_context, user_context
from src.agent.state import AgentState
from src.agent.tools import build_tools
from src.data.errors import DataToolError
from src.data.store import DatasetStore
from src.llm.reliability import RetryPolicy, invoke_with_retry


def _as_text(content: Any) -> str:
    """Extract only visible text blocks; never render model thinking blocks."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return ""


def build_graph(
    llm: Any, store: DatasetStore, *, max_tool_calls: int = 8,
    retry_policy: RetryPolicy | None = None,
):
    """Build a graph for one isolated CSV analysis session.

    Dependency injection of `llm` also supports deterministic offline tests.
    """
    if not 1 <= max_tool_calls <= 20:
        raise ValueError("max_tool_calls must be between 1 and 20")
    policy = retry_policy or RetryPolicy()
    tools = build_tools(store)
    tools_by_name = {tool.name: tool for tool in tools}
    llm_with_tools = llm.bind_tools(tools)

    def planner(state: AgentState) -> dict:
        outcome = invoke_with_retry(
            llm,
            [SystemMessage(content=PLANNER_SYSTEM),
             HumanMessage(content=user_context(state["user_query"], state["schema"]))],
            stage="planner", policy=policy,
        )
        if outcome.failure is not None:
            return {
                "status": "error",
                "error": "LLM_PLAN_FAILED",
                "answer": outcome.failure.user_message,
                "trace": [*outcome.events, {
                    "event": "error", "stage": "planner", "code": "LLM_PLAN_FAILED",
                    "cause": outcome.failure.code,
                    "http_status": outcome.failure.http_status,
                    "attempts": outcome.attempts,
                }],
            }
        plan = _as_text(outcome.response.content)
        if not plan:
            plan = "先檢查資料欄位，並使用對應工具完成使用者問題。"
        return {
            "plan": plan[:2000],
            "trace": [*outcome.events, {"event": "plan", "summary": plan[:2000]}],
        }

    def route_planner(state: AgentState) -> str:
        return "stop" if state.get("status") == "error" else "agent"

    def agent(state: AgentState) -> dict:
        remaining = max_tool_calls - state.get("tool_executions", 0)
        system = agent_context(state["schema"], state["plan"])
        if remaining <= 0:
            system += (
                "\n\n已到達工具呼叫上限。你不可再呼叫工具；請以現有 Observation 回答，"
                "未完成部分須明確指出，不能補造數值。"
            )
        history = [SystemMessage(content=system), *state["messages"]]
        model = llm_with_tools if remaining > 0 else llm
        outcome = invoke_with_retry(model, history, stage="decision", policy=policy)
        if outcome.failure is not None:
            return {
                "status": "error",
                "error": "LLM_AGENT_FAILED",
                "answer": outcome.failure.user_message,
                "trace": [*outcome.events, {
                    "event": "error", "stage": "decision", "code": "LLM_AGENT_FAILED",
                    "cause": outcome.failure.code,
                    "http_status": outcome.failure.http_status,
                    "attempts": outcome.attempts,
                }],
            }
        response = outcome.response
        calls = getattr(response, "tool_calls", None) or []
        invalid_calls = getattr(response, "invalid_tool_calls", None) or []
        if invalid_calls:
            return {
                "messages": [response],
                "status": "error",
                "error": "INVALID_MODEL_TOOL_CALL",
                "answer": "模型產生無法解析的工具參數，請重新描述問題或更換模型。",
                "trace": [*outcome.events, {"event": "error", "stage": "decision",
                    "code": "INVALID_MODEL_TOOL_CALL"}],
            }
        return {
            "messages": [response],
            "trace": [*outcome.events, {
                "event": "decision",
                "actions": [{"tool": c.get("name"), "args": c.get("args")} for c in calls],
                "action_type": "tool_call" if calls else "respond",
            }],
        }

    def route_agent(state: AgentState) -> str:
        if state.get("status") == "error":
            return "stop"
        last = state["messages"][-1]
        return "execute_tools" if getattr(last, "tool_calls", None) else "finalize"

    def execute_tools(state: AgentState) -> dict:
        message = state["messages"][-1]
        calls = getattr(message, "tool_calls", None) or []
        tool_messages: list[ToolMessage] = []
        events: list[dict[str, Any]] = []
        successful = state.get("successful_tools", 0)
        failures = state.get("failed_tools", 0)
        executed = state.get("tool_executions", 0)

        for call in calls:
            tool_started = time.monotonic()
            name = str(call.get("name", ""))
            args = call.get("args", {})
            call_id = str(call.get("id") or f"missing-id-{executed}")
            if executed >= max_tool_calls:
                result = {"ok": False, "error": {
                    "code": "TOOL_BUDGET_EXCEEDED",
                    "message": "超過當次分析的工具呼叫數限制。",
                }}
            elif name not in tools_by_name:
                result = {"ok": False, "error": {
                    "code": "UNKNOWN_TOOL", "message": f"未註冊工具：{name}"}}
            else:
                try:
                    output = tools_by_name[name].invoke(args)
                    result = {"ok": True, "data": output}
                except DataToolError as exc:
                    result = {"ok": False, "error": exc.to_dict()}
                except (ValidationError, TypeError, ValueError) as exc:
                    result = {"ok": False, "error": {
                        "code": "INVALID_TOOL_ARGS",
                        "message": "工具參數不符合定義或資料型態。",
                    }}
                except Exception:
                    result = {"ok": False, "error": {
                        "code": "TOOL_EXECUTION_FAILED",
                        "message": "工具出現非預期錯誤，未產生可用數據。",
                    }}
            executed += 1
            successful += int(result["ok"])
            failures += int(not result["ok"])
            # ToolMessage is kept verbatim in history so the provider's call IDs match.
            payload = json.dumps(result, ensure_ascii=False, default=str, allow_nan=False)
            tool_messages.append(ToolMessage(content=payload, name=name, tool_call_id=call_id))
            events.append({
                "event": "observation",
                "tool": name,
                "args": args,
                "result": result,
                "elapsed_seconds": round(max(0.0, time.monotonic() - tool_started), 4),
            })
        return {
            "messages": tool_messages,
            "trace": events,
            "tool_executions": executed,
            "successful_tools": successful,
            "failed_tools": failures,
        }

    def finalize(state: AgentState) -> dict:
        last = state["messages"][-1]
        answer = _as_text(last.content) if isinstance(last, AIMessage) else ""
        if state.get("successful_tools", 0) == 0:
            if answer:
                return {
                    "answer": "尚未取得成功的資料分析工具結果，以下內容未經數值驗證：\n" + answer,
                    "status": "needs_clarification",
                    "trace": [{"event": "final", "status": "needs_clarification"}],
                }
            return {
                "answer": "沒有成功的工具執行結果，無法提供可靠分析。",
                "status": "error",
                "trace": [{"event": "final", "status": "error"}],
            }
        if not answer:
            return {
                "answer": "工具已完成計算，但模型沒有產生可讀取的最終回答；請檢查 Observation。",
                "status": "error",
                "trace": [{"event": "final", "status": "error"}],
            }
        return {
            "answer": answer,
            "status": "completed",
            "trace": [{"event": "final", "status": "completed"}],
        }

    graph = StateGraph(AgentState)
    graph.add_node("planner", planner)
    graph.add_node("agent", agent)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", route_planner, {"stop": END, "agent": "agent"})
    graph.add_conditional_edges(
        "agent", route_agent, {"stop": END, "execute_tools": "execute_tools", "finalize": "finalize"}
    )
    graph.add_edge("execute_tools", "agent")
    graph.add_edge("finalize", END)
    return graph.compile()


def run_analysis(graph: Any, store: DatasetStore, question: str, *, max_tool_calls: int = 8) -> AgentState:
    question = question.strip()
    if not question:
        raise ValueError("使用者問題不可為空。")
    if len(question) > 2000:
        raise ValueError("使用者問題不可超過 2000 字。")
    initial: AgentState = {
        "user_query": question,
        "schema": store.schema(),
        "plan": "",
        "messages": [HumanMessage(content=question)],
        "trace": [],
        "tool_executions": 0,
        "successful_tools": 0,
        "failed_tools": 0,
        "status": "running",
        "answer": "",
    }
    # Two graph nodes per tool iteration plus a planner and a finalizer.
    return graph.invoke(initial, config={"recursion_limit": max(15, max_tool_calls * 4 + 8)})
