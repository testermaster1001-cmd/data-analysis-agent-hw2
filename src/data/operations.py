"""Deterministic, unit-testable pandas operations. No LLM dependency."""
from __future__ import annotations

from typing import Literal
from decimal import Decimal, InvalidOperation
import math

import pandas as pd
from pandas.api.types import is_bool_dtype, is_integer_dtype, is_numeric_dtype

from src.data.errors import DataToolError
from src.data.store import DatasetStore, json_value, preview_rows

StatsOp = Literal["sum", "mean", "min", "max", "count"]
FilterOp = Literal["eq", "ne", "gt", "ge", "lt", "le", "contains"]


def _require_column(data: pd.DataFrame, column: str) -> None:
    if column not in data.columns:
        raise DataToolError("COLUMN_NOT_FOUND", f"欄位不存在：{column}")


def _require_numeric(data: pd.DataFrame, column: str) -> None:
    _require_column(data, column)
    dtype = data[column].dtype
    if not is_numeric_dtype(dtype) or is_bool_dtype(dtype):
        raise DataToolError("TYPE_MISMATCH", f"欄位 {column} 不是數值型態，無法運算。")


def _require_nonempty(data: pd.DataFrame) -> None:
    if data.empty:
        raise DataToolError("EMPTY_RESULT", "分析結果為空，沒有可運算的資料列。")


def inspect_dataset(store: DatasetStore, source_id: str = "dataset") -> dict:
    return store.schema(source_id)


def calculate_statistics(
    store: DatasetStore,
    column: str,
    operation: StatsOp,
    source_id: str = "dataset",
) -> dict:
    data = store.table(source_id)
    _require_column(data, column)
    if operation != "count":
        _require_numeric(data, column)
        if data[column].notna().sum() == 0:
            raise DataToolError("NO_NUMERIC_VALUES", f"欄位 {column} 沒有有效的數值。")
    if operation not in {"sum", "mean", "min", "max", "count"}:
        raise DataToolError("INVALID_OPERATION", f"不支援的統計操作：{operation}")
    result = getattr(data[column], operation)()
    return {
        "source_id": source_id,
        "column": column,
        "operation": operation,
        "value": json_value(result),
        "valid_count": int(data[column].notna().sum()),
    }


def filter_data(
    store: DatasetStore,
    column: str,
    operator: FilterOp,
    value: str,
    source_id: str = "dataset",
) -> dict:
    data = store.table(source_id)
    _require_column(data, column)
    if operator not in {"eq", "ne", "gt", "ge", "lt", "le", "contains"}:
        raise DataToolError("INVALID_OPERATOR", f"不支援的篩選條件：{operator}")
    series = data[column]
    if operator == "contains":
        if is_numeric_dtype(series.dtype):
            raise DataToolError("TYPE_MISMATCH", "contains 只適用於文字欄位。")
        mask = series.astype("string").str.contains(value, regex=False, case=False, na=False)
    else:
        if is_numeric_dtype(series.dtype) and not is_bool_dtype(series.dtype):
            try:
                if len(value) > 128:
                    raise ValueError("numeric literal is too long")
                if is_integer_dtype(series.dtype):
                    # Do not round int64 identifiers through float (precision is
                    # lost above 2**53, causing incorrect equality matches).
                    wanted = Decimal(value)
                    if not wanted.is_finite():
                        raise ValueError("not finite")
                else:
                    wanted = float(value)
                    if not math.isfinite(wanted):
                        raise ValueError("not finite")
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise DataToolError("TYPE_MISMATCH", f"欄位 {column} 要求數值篩選條件。") from exc
        else:
            if operator in {"gt", "ge", "lt", "le"}:
                raise DataToolError("TYPE_MISMATCH", "文字欄位只允許 eq、ne、contains。")
            wanted = value
        masks = {
            "eq": lambda: series.eq(wanted),
            "ne": lambda: series.ne(wanted),
            "gt": lambda: series.gt(wanted),
            "ge": lambda: series.ge(wanted),
            "lt": lambda: series.lt(wanted),
            "le": lambda: series.le(wanted),
        }
        mask = masks[operator]().fillna(False) & series.notna()
    result = data.loc[mask].copy()
    result_id = store.save(result)
    return {
        "source_id": source_id,
        "result_id": result_id,
        "row_count": int(len(result)),
        "sample_rows": preview_rows(result),
    }


def group_and_aggregate(
    store: DatasetStore,
    group_columns: list[str],
    metric: str,
    operation: StatsOp,
    source_id: str = "dataset",
) -> dict:
    data = store.table(source_id)
    if not group_columns or len(group_columns) > 3 or len(set(group_columns)) != len(group_columns):
        raise DataToolError("INVALID_GROUPING", "分組欄位必須是 1～3 個不重複欄位。")
    for col in [*group_columns, metric]:
        _require_column(data, col)
    if metric in group_columns:
        raise DataToolError("INVALID_GROUPING", "統計欄位不可同時作為分組欄位。")
    if operation != "count":
        _require_numeric(data, metric)
    if operation not in {"sum", "mean", "min", "max", "count"}:
        raise DataToolError("INVALID_OPERATION", f"不支援的統計操作：{operation}")
    _require_nonempty(data)
    grouped_series = data.groupby(group_columns, dropna=False, sort=True)[metric]
    # A group containing only missing values must not become an invented zero.
    aggregated = grouped_series.sum(min_count=1) if operation == "sum" else grouped_series.agg(operation)
    grouped = aggregated.reset_index(name=f"{metric}_{operation}")
    if grouped.empty:
        raise DataToolError("EMPTY_RESULT", "分組統計沒有結果。")
    result_id = store.save(grouped)
    return {
        "source_id": source_id,
        "result_id": result_id,
        "result_column": f"{metric}_{operation}",
        "row_count": int(len(grouped)),
        "sample_rows": preview_rows(grouped),
        "note": "如果群組超過預覽筆數，請使用 sort_and_rank 對 result_id 排序，勿依預覽自行猜測最高值。",
    }


def sort_and_rank(
    store: DatasetStore,
    column: str,
    direction: Literal["asc", "desc"] = "desc",
    top_n: int = 5,
    source_id: str = "dataset",
) -> dict:
    data = store.table(source_id)
    _require_column(data, column)
    if direction not in {"asc", "desc"}:
        raise DataToolError("INVALID_DIRECTION", "排序方向只能是 asc 或 desc。")
    if top_n < 1 or top_n > 50:
        raise DataToolError("INVALID_TOP_N", "top_n 必須介於 1～50。")
    _require_nonempty(data)
    ranked = data.sort_values(column, ascending=(direction == "asc"), na_position="last", kind="stable")
    ranked = ranked.head(top_n).copy()
    result_id = store.save(ranked)
    return {
        "source_id": source_id,
        "result_id": result_id,
        "row_count": int(len(ranked)),
        "sort_column": column,
        "direction": direction,
        "rows": preview_rows(ranked, limit=50),
    }
