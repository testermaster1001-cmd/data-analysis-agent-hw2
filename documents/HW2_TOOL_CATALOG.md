# HW2 工具定義與錯誤處理

所有工具由 `src/agent/tools.py` 註冊為 LangChain `StructuredTool`，參數由 Pydantic Schema 定義；實際運算在 `src/data/operations.py`。預設 `source_id="dataset"` 表示原始 CSV；其他有效 `source_id` 必須來自先前工具成功回傳的 `result_id`。

| Tool | 目的 | 必填參數 | 可選參數 | 主要輸出 |
|---|---|---|---|---|
| `inspect_dataset` | 檢查欄位、型態、筆數、缺失值 | — | `source_id` | `columns`、`row_count`、`sample_rows` |
| `calculate_statistics` | 基本統計 | `column`、`operation` | `source_id` | `value`、`valid_count` |
| `filter_data` | 條件篩選 | `column`、`operator`、`value` | `source_id` | `result_id`、`row_count`、`sample_rows` |
| `group_and_aggregate` | 分組統計 | `group_columns`、`metric`、`operation` | `source_id` | `result_id`、`result_column`、`sample_rows` |
| `sort_and_rank` | 排序與 Top-N | `column` | `direction`（`desc`）、`top_n`（5）、`source_id` | `result_id`、`rows` |

## 參數限制

- 統計操作：`sum / mean / min / max / count`。非 `count` 運算要求數值欄位；`count` 統計非空值數量。
- 篩選運算：`eq / ne / gt / ge / lt / le / contains`；比較值由 `value` 字串提供。`contains` 為大小寫不敏感的純文字比對，**不使用正規表達式**。
- 分組：1～3 個不重複的 `group_columns`；`metric` 不可同時為分組欄位。Sum 使用 `min_count=1` 避免缺失值全空的群組被寫為零。
- 排序：`direction` 僅接受 `asc / desc`；`top_n` 為 1～50。
- 所有欄位名稱與 Schema 必須完全一致，不自動更名或推測同義欄位。

## 工具回傳協定

成功：

```json
{"ok":true,"data":{"source_id":"dataset","column":"Revenue","operation":"sum","value":11300,"valid_count":14}}
```

失敗：

```json
{"ok":false,"error":{"code":"COLUMN_NOT_FOUND","message":"欄位不存在：Money"}}
```

此封裝由 `src/agent/graph.py` 的 Tool Executor 負責，並透過對應 `tool_call_id` 的 ToolMessage 交回模型。預期錯誤會以穩定代碼呈現，非預期錯誤不將完整 Python traceback 傳給 LLM。

## 常見錯誤與處理

| 代碼 | 發生原因 | 建議處理 |
|---|---|---|
| `FILE_NOT_FOUND` / `INVALID_CSV` | 路徑不存在或 CSV 格式無法解析 | 提醒使用者確認路徑、UTF-8 編碼 |
| `DUPLICATE_COLUMNS` / `INVALID_HEADER` | 欄位重複或標題不合法 | 修正 CSV 標題 |
| `COLUMN_NOT_FOUND` | Tool 傳入不存在的欄位 | 依 Schema 修正，無法確定則詢問使用者 |
| `SOURCE_NOT_FOUND` | 中間結果代號不存在 | 使用先前 Tool Result 的 `result_id` |
| `TYPE_MISMATCH` | 數值操作使用文字欄位等 | 更換欄位或合適的操作 |
| `EMPTY_RESULT` / `NO_NUMERIC_VALUES` | 結果無資料或無有效數值 | 說明缺少資料、不推測結果 |
| `INVALID_OPERATOR` / `INVALID_OPERATION` | 不支援的運算 | 使用白名單操作 |
| `INVALID_GROUPING` / `INVALID_TOP_N` | 分組或排序參數無效 | 修正工具參數 |
| `INVALID_TOOL_ARGS` | Pydantic 驗證未通過 | 根據 Schema 重新構造參數 |
| `UNKNOWN_TOOL` | 模型選擇未註冊 Tool | 拒絕執行，回報錯誤 |
| `TOOL_BUDGET_EXCEEDED` | 超過執行上限 | 停止新分析並說明限制 |

更多實際測試與失敗證據見 `documents/HW2_TEST_PLAN.md` 與 `documents/evidence/`。
