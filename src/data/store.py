"""Per-run CSV dataset and temporary analysis result registry; never writes source files."""
from __future__ import annotations

from collections import Counter
import csv
from pathlib import Path
from typing import Any
import math

import pandas as pd

from src.data.errors import DataToolError

DEFAULT_MAX_BYTES = 15 * 1024 * 1024
DEFAULT_MAX_ROWS = 100_000
DEFAULT_MAX_COLUMNS = 100
MAX_STORED_RESULTS = 30


def json_value(value: Any) -> Any:
    """Convert a scalar to a bounded JSON-safe representation for the LLM."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, dict)):
        return str(value)[:160]
    try:
        if bool(pd.isna(value)):
            return None
    except (ValueError, TypeError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value  # Do not lose precision by converting large integers to float.
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return json_value(value.item())
        except (ValueError, TypeError):
            pass
    if isinstance(value, str):
        return value[:160]
    return str(value)[:160]


def preview_rows(data: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
    records = data.head(limit).to_dict(orient="records")
    return [{str(k): json_value(v) for k, v in row.items()} for row in records]


class DatasetStore:
    """An in-memory registry; built-in tools never write back to the source CSV."""

    def __init__(self, data: pd.DataFrame) -> None:
        if data.empty:
            raise DataToolError("EMPTY_DATASET", "CSV 沒有可分析的資料列。")
        if len(data.columns) > DEFAULT_MAX_COLUMNS:
            raise DataToolError("TOO_MANY_COLUMNS", "CSV 欄位數超過上限。")
        self._tables: dict[str, pd.DataFrame] = {"dataset": data.copy(deep=True)}
        self._next_id = 1

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_rows: int = DEFAULT_MAX_ROWS,
    ) -> "DatasetStore":
        file_path = Path(path).expanduser()
        if not file_path.is_file():
            raise DataToolError("FILE_NOT_FOUND", "找不到 CSV 檔案，請確認路徑。")
        if file_path.suffix.lower() != ".csv":
            raise DataToolError("UNSUPPORTED_FORMAT", "目前只支援 .csv 檔案。")
        if file_path.stat().st_size > max_bytes:
            raise DataToolError("FILE_TOO_LARGE", "CSV 大小超過安全限制。")
        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as fh:
                header = next(csv.reader(fh), [])
            if not header or any(not c.strip() for c in header):
                raise DataToolError("INVALID_HEADER", "CSV 欄位名稱不可為空。")
            if any(count > 1 for count in Counter(header).values()):
                raise DataToolError("DUPLICATE_COLUMNS", "CSV 欄位名稱不得重複。")
            if len(header) > DEFAULT_MAX_COLUMNS:
                raise DataToolError("TOO_MANY_COLUMNS", "CSV 欄位數超過上限。")
            data = pd.read_csv(
                file_path,
                encoding="utf-8-sig",
                nrows=max_rows + 1,
                on_bad_lines="error",
                low_memory=False,
            )
        except (UnicodeDecodeError, csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            raise DataToolError("INVALID_CSV", "CSV 無法解析；請檢查 UTF-8 編碼及格式。") from exc
        if len(data) > max_rows:
            raise DataToolError("TOO_MANY_ROWS", "CSV 資料列數超過安全限制。")
        return cls(data)

    def table(self, source_id: str = "dataset") -> pd.DataFrame:
        try:
            return self._tables[source_id]
        except KeyError as exc:
            raise DataToolError("SOURCE_NOT_FOUND", f"分析結果代號不存在：{source_id}") from exc

    def save(self, data: pd.DataFrame) -> str:
        if len(self._tables) - 1 >= MAX_STORED_RESULTS:
            raise DataToolError("RESULT_LIMIT", "分析結果數已達上限。")
        # Create a new handle; do not overwrite any previous result or the original data.
        result_id = f"result_{self._next_id:03d}"
        self._next_id += 1
        self._tables[result_id] = data.copy(deep=True)
        return result_id

    def schema(self, source_id: str = "dataset") -> dict[str, Any]:
        data = self.table(source_id)
        return {
            "source_id": source_id,
            "row_count": int(len(data)),
            "column_count": int(len(data.columns)),
            "columns": [
                {
                    "name": str(col),
                    "dtype": str(data[col].dtype),
                    "missing_count": int(data[col].isna().sum()),
                }
                for col in data.columns
            ],
            "sample_rows": preview_rows(data, 3),
        }
