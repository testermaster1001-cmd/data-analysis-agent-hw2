from pathlib import Path

import pandas as pd
import pytest

from src.data.errors import DataToolError
from src.data.store import DatasetStore, preview_rows, json_value


def test_schema_and_missing_values(sales_store):
    schema = sales_store.schema()
    assert schema["row_count"] == 14
    assert schema["column_count"] == 5
    assert [col["name"] for col in schema["columns"]] == [
        "OrderID", "Category", "Region", "Revenue", "Quantity"
    ]
    assert len(schema["sample_rows"]) == 3


def test_missing_values_fixture():
    path = Path(__file__).resolve().parents[1] / "data" / "sample_missing.csv"
    store = DatasetStore.from_csv(path)
    assert next(c for c in store.schema()["columns"] if c["name"] == "Revenue")["missing_count"] == 1


def test_result_handle_and_immutability(sales_store):
    original_revenue = sales_store.table("dataset")["Revenue"].sum()
    new_id = sales_store.save(sales_store.table("dataset").head(1))
    assert new_id == "result_001"
    assert sales_store.table(new_id).shape == (1, 5)
    assert sales_store.table("dataset")["Revenue"].sum() == original_revenue


def test_unknown_result_id(sales_store):
    with pytest.raises(DataToolError, match="不存在"):
        sales_store.table("result_999")


def test_csv_unsupported_format(tmp_path):
    path = tmp_path / "x.txt"
    path.write_text("A,B\n1,2\n", encoding="utf-8")
    with pytest.raises(DataToolError) as info:
        DatasetStore.from_csv(path)
    assert info.value.code == "UNSUPPORTED_FORMAT"


def test_csv_missing_file(tmp_path):
    with pytest.raises(DataToolError) as info:
        DatasetStore.from_csv(tmp_path / "missing.csv")
    assert info.value.code == "FILE_NOT_FOUND"


def test_csv_duplicate_header(tmp_path):
    path = tmp_path / "duplicate.csv"
    path.write_text("A,A\n1,2\n", encoding="utf-8")
    with pytest.raises(DataToolError) as info:
        DatasetStore.from_csv(path)
    assert info.value.code == "DUPLICATE_COLUMNS"


def test_csv_row_limit(tmp_path):
    path = tmp_path / "long.csv"
    path.write_text("A,B\n1,2\n3,4\n", encoding="utf-8")
    with pytest.raises(DataToolError) as info:
        DatasetStore.from_csv(path, max_rows=1)
    assert info.value.code == "TOO_MANY_ROWS"


def test_csv_encoding_failure(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"A,B\n\xff,1\n")
    with pytest.raises(DataToolError) as info:
        DatasetStore.from_csv(path)
    assert info.value.code == "INVALID_CSV"


def test_empty_dataset_rejected():
    with pytest.raises(DataToolError) as info:
        DatasetStore(pd.DataFrame({"A": []}))
    assert info.value.code == "EMPTY_DATASET"


def test_json_value_handles_non_finite():
    assert json_value(float("nan")) is None
    assert json_value(float("inf")) is None
    assert preview_rows(pd.DataFrame({"A": [float("nan")]})) == [{"A": None}]
