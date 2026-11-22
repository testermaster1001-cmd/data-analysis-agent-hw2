# 真實 OpenAI + Podman 執行案例

## 測試資料與問題

- 資料集：`data/sample_sales.csv`（14 筆合成訂單、5 個欄位，無真實個資）。
- 模型：`gpt-5.4-mini`（OpenAI API）。
- 問題：找出總營收最高的商品類別，並說明該類別在哪個地區營收最高。
- 執行狀態：`completed`。
- 工具執行：6 次（成功 6 次、失敗 0 次）。
- LLM 請求嘗試：7 次（重試 0 次）。
- 總耗時：9.1516 秒；其中 LLM 請求約 7.5279 秒，工具合計約 0.0102 秒。

本報告依據本次提交的 `openai_podman_trace.json`，**與其他時間執行的終端機截圖可能具有不同的 Tool Call 數與耗時**。此 Trace 來自實際模型，而非 ScriptedLLM。

## Tool Call 與資料來源

| 順序 | Tool | source_id | 產生 result_id |
|---:|---|---|---|
| 1 | `group_and_aggregate` | `dataset` | `result_001` |
| 2 | `inspect_dataset` | `dataset` | `—` |
| 3 | `sort_and_rank` | `result_001` | `result_002` |
| 4 | `filter_data` | `dataset` | `result_003` |
| 5 | `group_and_aggregate` | `result_003` | `result_004` |
| 6 | `sort_and_rank` | `result_004` | `result_005` |

來源引用已使用 `scripts/audit_trace.py` 檢查：所有非 `dataset` 的 `source_id` 都在先前成功的工具結果中產生；工具成功／失敗計數與 Observation 紀錄一致。

## 獨立數值驗證

以 `data/sample_sales.csv` 直接使用 pandas 計算，不依賴 LLM 的文字結果：

| 項目 | Ground Truth | Trace 最終回答 |
|---|---|---|
| 最高營收商品類別 | Tech | Tech |
| 該類別總營收 | 6,000 | 6,000 |
| Tech 營收最高地區 | North | North |
| 該地區 Tech 營收 | 2,800 | 2,800 |

兩個排序工具的 Observation 中也分別保留了 `Tech / 6000` 與 `North / 2800`。

## 使用方式與限制

```powershell
.\.venv\Scripts\python.exe scripts/trace_report.py documents/evidence/success_case/openai_podman_trace.json
.\.venv\Scripts\python.exe scripts/audit_trace.py documents/evidence/success_case/openai_podman_trace.json
```

這是 **單一成功案例**，不能推論所有資料集的 Task Success Rate 都為 100%。`completed` 為 Workflow 結束狀態；是否回答所有子問題，需另以測試資料與 Ground Truth 比對。Trace 內包含合成樣本資料與工具參數；請勿用私人 CSV 的原始 Trace 直接取代。
