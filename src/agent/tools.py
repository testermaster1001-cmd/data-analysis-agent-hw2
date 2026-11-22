"""Explicit LangChain tool schemas and their deterministic pandas implementations."""
from __future__ import annotations

from typing import Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.data import operations
from src.data.store import DatasetStore


class InspectArgs(BaseModel):
    source_id: str = Field(default="dataset", description="來源表格代號；原始 CSV 使用 dataset")


class StatisticsArgs(InspectArgs):
    column: str = Field(description="既有欄位名稱，大小寫與拼字必須與 Schema 相同")
    operation: Literal["sum", "mean", "min", "max", "count"] = Field(description="統計運算")


class FilterArgs(InspectArgs):
    column: str = Field(description="篩選欄位名稱")
    operator: Literal["eq", "ne", "gt", "ge", "lt", "le", "contains"] = Field(
        description="eq 等於；ne 不等於；gt 大於；ge 大於等於；lt 小於；le 小於等於；contains 包含文字"
    )
    value: str = Field(description="比較值，請以字串提供，例如 'North' 或 '1000'")


class AggregateArgs(InspectArgs):
    group_columns: list[str] = Field(min_length=1, max_length=3, description="要分組的 1～3 個欄位")
    metric: str = Field(description="要彙總的欄位")
    operation: Literal["sum", "mean", "min", "max", "count"] = Field(description="彙總運算")


class RankArgs(InspectArgs):
    column: str = Field(description="要排序的欄位；聚合後可用 Revenue_sum 等結果欄位")
    direction: Literal["asc", "desc"] = Field(default="desc", description="desc 由大到小；asc 由小到大")
    top_n: int = Field(default=5, ge=1, le=50, description="最多回傳的排序筆數")


def build_tools(store: DatasetStore) -> list[StructuredTool]:
    """Return tools scoped to one run; no global DataFrame or file-system access."""

    def inspect_dataset(source_id: str = "dataset") -> dict:
        return operations.inspect_dataset(store, source_id)

    def calculate_statistics(column: str, operation: str, source_id: str = "dataset") -> dict:
        return operations.calculate_statistics(store, column, operation, source_id)

    def filter_data(column: str, operator: str, value: str, source_id: str = "dataset") -> dict:
        return operations.filter_data(store, column, operator, value, source_id)

    def group_and_aggregate(
        group_columns: list[str], metric: str, operation: str, source_id: str = "dataset"
    ) -> dict:
        return operations.group_and_aggregate(store, group_columns, metric, operation, source_id)

    def sort_and_rank(
        column: str, direction: str = "desc", top_n: int = 5, source_id: str = "dataset"
    ) -> dict:
        return operations.sort_and_rank(store, column, direction, top_n, source_id)

    specs = [
        (inspect_dataset, InspectArgs, "檢查資料表欄位、型態、筆數、缺失值及前三筆樣本。"),
        (calculate_statistics, StatisticsArgs, "對指定欄位計算 sum、mean、min、max 或有效值 count。"),
        (filter_data, FilterArgs, "按欄位和值篩選資料；回傳 result_id，後續工具可繼續使用。"),
        (
            group_and_aggregate,
            AggregateArgs,
            "按 1～3 個欄位進行分組彙總，回傳 result_id 和 result_column，可供排序。",
        ),
        (sort_and_rank, RankArgs, "對指定來源的欄位排序並取前 N 筆；可接續聚合或篩選的 result_id。"),
    ]
    return [
        StructuredTool.from_function(func=func, name=func.__name__, description=desc, args_schema=arguments)
        for func, arguments, desc in specs
    ]
