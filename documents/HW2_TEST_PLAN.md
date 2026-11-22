# HW2 測試方式與評估準則

## 1. 測試分層

| 類型 | 執行方式 | 目的 | 是否呼叫付費 API |
|---|---|---|---|
| pandas / CSV 單元測試 | `python -m pytest -q` | Schema、統計、篩選、分組、排序、邊界條件 | 否 |
| LangGraph 模擬整合測試 | `tests/test_graph.py` | 使用假 LLM 測試 ReAct、Error Handling、Trace 與重試 | 否 |
| 可重現 Failure Cases | `python scripts/failure_cases.py` | 使用 ScriptedLLM 引發指定工具錯誤並記錄處理 | 否 |
| 真實 OpenAI E2E | `python -m src.main ...` | 實際模型決策與 pandas 工具使用 | 是 |
| Podman 驗收 | `podman run ...` | 驗證容器中的程式、API 存取、Trace 掛載 | 使用 LLM 時是 |
| Trace 來源稽核 | `python scripts/audit_trace.py <file>` | 確認每個來源代號先前已由成功工具建立 | 否 |

## 2. 資料集與 Ground Truth

`data/sample_sales.csv` 含 14 筆模擬訂單、五個欄位：`OrderID`、`Category`、`Region`、`Revenue`、`Quantity`。

示範問題：「找出總營收最高的商品類別，並說明該類別在哪個地區營收最高。」

獨立 pandas Ground Truth：

- 各類別總營收：Food 2,000；Home 3,300；Tech 6,000。
- 最高類別：**Tech**，總營收 **6,000**。
- Tech 在各地區的營收：East 1,600；North 2,800；South 1,600。
- 最高地區：**North**，營收 **2,800**。

## 3. 完整 Agent Execution Trace

`documents/evidence/success_case/openai_podman_trace.json` 是由實際 Podman + OpenAI API 執行取得的紀錄，與模擬測試不同。

Trace 必須顯示：使用者問題 → Plan → Decision → Tool Call → Observation → Next Decision → Final。某一輪 Decision 可能同時呼叫多個 Tool；所有結果應由對應的 ToolMessage 回傳。

可執行：

```powershell
.\.venv\Scripts\python.exe scripts/trace_report.py documents/evidence/success_case/openai_podman_trace.json
.\.venv\Scripts\python.exe scripts/audit_trace.py documents/evidence/success_case/openai_podman_trace.json
```

上述稽核只檢查 **Trace 結構與來源引用**，不自動評定最終回答是否涵蓋所有子問題；數值正確性仍由獨立 Ground Truth 比對。

## 4. 失敗案例

| Case ID | 模擬輸入 | 預期錯誤 | 處理原則 |
|---|---|---|---|
| F01 | 對不存在的 `Money` 欄位求平均 | `COLUMN_NOT_FOUND` | 回報欄位不存在，要求確認，不強行視為 Revenue |
| F02 | 對文字 `Category` 欄位求平均 | `TYPE_MISMATCH` | 回報型態不合適，不編造數值平均 |

實驗執行：

```powershell
.\.venv\Scripts\python.exe scripts/failure_cases.py
```

測試由 ScriptedLLM **預先指定 LLM 回應與工具參數**，實際執行正式 LangGraph + pandas Tools，驗證系統收到錯誤後是否能適當結束並回報。此測試不代表真實 GPT 在相同提問下會選擇相同的錯誤工具。證據與原因／解決方式在 `documents/evidence/failure_cases/failure_cases_report.md`。

## 5. 評估方式與限制

- **Task Success Rate：** 多筆完整任務中，符合所有使用者要求的比例。
- **Numerical Accuracy：** 主要數值與獨立 pandas Ground Truth 的一致比例。
- **Completeness：** 多子任務完成的比例。
- **Tool Success Rate：** 成功工具呼叫數 / 所有工具呼叫數。
- **Latency：** 從任務開始到最後輸出的時間；Trace 中也記錄 LLM／工具耗時。

本次示範資料集只能證明指定案例已成功，不代表模型在所有資料集或問題上的成功率。`completed` 表示程序完成，不應直接視為 Task Success 的判定依據。公開證據只使用合成資料，避免洩漏私人 CSV 和 API Key。
