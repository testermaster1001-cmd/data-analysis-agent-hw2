"""Offline graph integration tests using fake model responses (no paid API calls)."""
import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage, ToolMessage
from src.agent.graph import build_graph, run_analysis
from src.llm.reliability import RetryPolicy


class FakeLLM:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.seen = []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.seen.append(messages)
        answer = next(self.answers)
        # A real LLM raises API failures; returning an Exception would instead
        # make LangGraph treat it as an unsupported chat message.
        if isinstance(answer, Exception):
            raise answer
        return answer


def fake_call(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def test_graph_multistep_success_and_trace(sales_store):
    fake = FakeLLM([
        AIMessage(content="先按類別彙總，再排名。"),
        fake_call("group_and_aggregate", {"group_columns": ["Category"], "metric": "Revenue", "operation": "sum"}, "c1"),
        fake_call("sort_and_rank", {"column": "Revenue_sum", "direction": "desc", "top_n": 1, "source_id": "result_001"}, "c2"),
        AIMessage(content="總營收最高為 Tech，總額 6000。"),
    ])
    graph = build_graph(fake, sales_store)
    output = run_analysis(graph, sales_store, "哪個商品類別總營收最高？")
    assert output["status"] == "completed"
    assert output["tool_executions"] == 2
    assert output["successful_tools"] == 2
    # v2 adds a safe timing event before each model response.
    workflow = [e["event"] for e in output["trace"] if e["event"] != "llm_call"]
    assert workflow == [
        "plan", "decision", "observation", "decision", "observation", "decision", "final"
    ]
    assert len([e for e in output["trace"] if e["event"] == "llm_call"]) == 4
    assert any(isinstance(msg, ToolMessage) for msg in output["messages"])
    assert "Tech" in output["answer"]


def test_graph_failure_no_hallucinated_success(sales_store):
    fake = FakeLLM([
        AIMessage(content="計算平均值。"),
        fake_call("calculate_statistics", {"column": "NoSuchColumn", "operation": "mean"}, "c1"),
        AIMessage(content="無法計算，欄位不存在。"),
    ])
    output = run_analysis(build_graph(fake, sales_store), sales_store, "請分析不存在的欄位")
    assert output["failed_tools"] == 1
    assert output["successful_tools"] == 0
    assert output["status"] == "needs_clarification"
    observation = next(e for e in output["trace"] if e["event"] == "observation")
    assert observation["result"]["error"]["code"] == "COLUMN_NOT_FOUND"


def test_graph_no_tool_answer_is_unverified(sales_store):
    fake = FakeLLM([AIMessage(content="請檢查欄位。"), AIMessage(content="我需要你確認營收欄位。")])
    output = run_analysis(build_graph(fake, sales_store), sales_store, "請問營收")
    assert output["status"] == "needs_clarification"
    assert "未經數值驗證" in output["answer"]


def test_graph_planner_failure_returns_error(sales_store):
    class BrokenLLM:
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            raise RuntimeError("sensitive API key must not appear")

    output = run_analysis(build_graph(BrokenLLM(), sales_store), sales_store, "總營收？")
    assert output["status"] == "error"
    assert "sensitive" not in output["answer"]


def test_graph_agent_failure_preserves_earlier_observation(sales_store):
    class TemporaryHTTPError(Exception):
        code = 503

    fake = FakeLLM([
        AIMessage(content="先進行分組統計。"),
        fake_call("group_and_aggregate", {"group_columns": ["Category"], "metric": "Revenue", "operation": "sum"}, "c1"),
        TemporaryHTTPError("secret never in trace"),
    ])
    output = run_analysis(
        build_graph(fake, sales_store, retry_policy=RetryPolicy(max_retries=0)),
        sales_store, "各類別營收是多少？"
    )
    assert output["status"] == "error"
    assert output["tool_executions"] == 1
    assert output["successful_tools"] == 1
    assert any(e["event"] == "observation" and e["result"]["ok"] for e in output["trace"])
    error = next(e for e in output["trace"] if e["event"] == "error")
    assert error["stage"] == "decision"
    assert error["http_status"] == 503
    assert error["cause"] == "SERVICE_UNAVAILABLE"
    assert "secret" not in str(output["trace"])


def test_graph_planner_retry_recovers(sales_store):
    class TemporaryHTTPError(Exception):
        code = 503

    fake = FakeLLM([
        TemporaryHTTPError(),
        AIMessage(content="使用分組工具。"),
        fake_call("group_and_aggregate", {"group_columns": ["Category"], "metric": "Revenue", "operation": "sum"}, "c1"),
        AIMessage(content="Tech 營收最高。"),
    ])
    result = run_analysis(build_graph(
        fake, sales_store, retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0),
    ), sales_store, "哪個商品類別營收最高？")
    assert result["status"] == "completed"
    assert sum(1 for e in result["trace"] if e["event"] == "llm_call" and e["status"] == "error") == 1
    assert result["tool_executions"] == 1
