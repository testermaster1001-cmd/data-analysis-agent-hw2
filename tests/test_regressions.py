import pandas as pd
import pytest

from src.data import operations as ops
from src.data.errors import DataToolError
from src.data.store import DatasetStore, json_value


def test_nulls_not_counted_as_zero_in_grouped_sum():
    store = DatasetStore(pd.DataFrame({"Category": ["A", "A", "B"], "Revenue": [None, None, 3.0]}))
    result = ops.group_and_aggregate(store, ["Category"], "Revenue", "sum")
    values = {row["Category"]: row["Revenue_sum"] for row in result["sample_rows"]}
    assert values == {"A": None, "B": 3.0}


def test_not_equal_filter_excludes_missing_values():
    store = DatasetStore(pd.DataFrame({"Category": ["A", None, "B"], "Revenue": [1, 2, 3]}))
    result = ops.filter_data(store, "Category", "ne", "A")
    assert result["row_count"] == 1
    assert result["sample_rows"][0]["Category"] == "B"


def test_json_safe_boolean():
    assert json_value(True) is True
    assert json_value(False) is False


def test_all_missing_numeric_column_rejected():
    store = DatasetStore(pd.DataFrame({"Category": ["A", "B"], "Revenue": [float("nan"), float("nan")]}))
    with pytest.raises(DataToolError) as info:
        ops.calculate_statistics(store, "Revenue", "sum")
    assert info.value.code == "NO_NUMERIC_VALUES"


def test_empty_csv_error(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DataToolError) as info:
        DatasetStore.from_csv(path)
    assert info.value.code == "INVALID_HEADER"


def test_filter_preserves_large_integer_identifier_precision():
    # Previously float(value) rounded 9007199254740993 to its neighbour.
    store = DatasetStore(pd.DataFrame({
        "OrderID": [9007199254740992, 9007199254740993, 9007199254740994],
        "Revenue": [11, 22, 33],
    }))
    answer = ops.filter_data(store, "OrderID", "eq", "9007199254740993")
    assert answer["row_count"] == 1
    assert answer["sample_rows"][0]["Revenue"] == 22
    greater = ops.filter_data(store, "OrderID", "gt", "9007199254740992.5")
    assert greater["row_count"] == 2
