"""LangGraph state; messages reducer preserves provider-specific tool metadata."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    user_query: str
    schema: dict[str, Any]
    plan: str
    messages: Annotated[list[AnyMessage], add_messages]
    trace: Annotated[list[dict[str, Any]], operator.add]
    tool_executions: int
    successful_tools: int
    failed_tools: int
    answer: str
    status: str
    error: str
