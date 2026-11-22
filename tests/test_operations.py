from pathlib import Path
import pytest

from src.data.errors import DataToolError
from src.data.store import DatasetStore
from src.data import operations as ops


def test_sum_and_mean(sales_store):
    result = ops.calculate_statistics(sales_store, "Revenue", "sum")
    assert result["value"] == 11300  # Food 2000 + Tech 6000 + Home 3300
    assert ops.calculate_statistics(sales_store, "Revenue", "mean")["value"] == pytest.approx(11300 / 14)


def test_count_allows_non_numeric(sales_store):
    assert ops.calculate_statistics(sales_store, "Region", "count")["value"] == 14


def test_stats_invalid_column(sales_store):
    with pytest.raises(DataToolError) as info:
        ops.calculate_statistics(sales_store, "Money", "sum")
    assert info.value.code == "COLUMN_NOT_FOUND"


def test_stats_non_numeric_column():
    base = Path(__file__).resolve().parents[1]
    store = DatasetStore.from_csv(base / "data" / "sample_invalid_numeric.csv")
    with pytest.raises(DataToolError) as info:
        ops.calculate_statistics(store, "Revenue", "mean")
    assert info.value.code == "TYPE_MISMATCH"


def test_filter_then_stats(sales_store):
    filtered = ops.filter_data(sales_store, "Category", "eq", "Tech")
    assert filtered["row_count"] == 5
    assert ops.calculate_statistics(sales_store, "Revenue", "sum", filtered["result_id"])["value"] == 6000


def test_filter_contains_literal_not_regex(sales_store):
    result = ops.filter_data(sales_store, "Category", "contains", "Te")
    assert result["row_count"] == 5
    result2 = ops.filter_data(sales_store, "Category", "contains", ".*")
    assert result2["row_count"] == 0


def test_filter_numeric_type_mismatch(sales_store):
    with pytest.raises(DataToolError) as info:
        ops.filter_data(sales_store, "Revenue", "gt", "not-a-number")
    assert info.value.code == "TYPE_MISMATCH"


def test_group_then_rank(sales_store):
    grouped = ops.group_and_aggregate(sales_store, ["Category"], "Revenue", "sum")
    assert grouped["result_column"] == "Revenue_sum"
    ranked = ops.sort_and_rank(sales_store, "Revenue_sum", "desc", 1, grouped["result_id"])
    assert ranked["rows"][0]["Category"] == "Tech"
    assert ranked["rows"][0]["Revenue_sum"] == 6000


def test_multi_step_region_ranking(sales_store):
    filtered = ops.filter_data(sales_store, "Category", "eq", "Tech")
    groups = ops.group_and_aggregate(sales_store, ["Region"], "Revenue", "sum", filtered["result_id"])
    ranked = ops.sort_and_rank(sales_store, "Revenue_sum", "desc", 1, groups["result_id"])
    assert ranked["rows"] == [{"Region": "North", "Revenue_sum": 2800.0}]


def test_unknown_source_handle(sales_store):
    with pytest.raises(DataToolError) as info:
        ops.sort_and_rank(sales_store, "Revenue", source_id="result_500")
    assert info.value.code == "SOURCE_NOT_FOUND"


def test_empty_result_cannot_be_ranked(sales_store):
    filtered = ops.filter_data(sales_store, "Category", "eq", "nonexistent")
    with pytest.raises(DataToolError) as info:
        ops.sort_and_rank(sales_store, "Revenue", source_id=filtered["result_id"])
    assert info.value.code == "EMPTY_RESULT"


def test_invalid_grouping(sales_store):
    with pytest.raises(DataToolError) as info:
        ops.group_and_aggregate(sales_store, ["Category", "Category"], "Revenue", "sum")
    assert info.value.code == "INVALID_GROUPING"


def test_missing_count():
    base = Path(__file__).resolve().parents[1]
    store = DatasetStore.from_csv(base / "data" / "sample_missing.csv")
    assert ops.calculate_statistics(store, "Revenue", "count")["value"] == 2
