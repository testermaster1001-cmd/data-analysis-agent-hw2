# HW2 驗收摘要

## 功能與證據

| 作業項目 | 系統對應 | 驗證方式 |
|---|---|---|
| Working Agent | `src/main.py` + `src/agent/graph.py` | 真實 OpenAI + Podman Trace 的 `completed` 狀態 |
| Tool / Planning / ReAct | Planner、Decision、Tool Executor、Observation | `documents/evidence/success_case/openai_podman_trace.json` |
| Agent 功能 | 五個 pandas Tools、Result ID 資料流 | Unit Tests + 真實案例結果對照 |
| Error Handling | DataToolError、LLMFailure、有限重試 | `tests/test_reliability.py`、F01/F02 |
| Testing / Failure Evidence | `tests/`、`scripts/failure_cases.py` | `documents/evidence/failure_cases/` |
| README / Deployment | `README.md`、`Containerfile`、`Containerfile.test` | Podman build / run / pytest 指令 |

## 真實成功案例

依本專案附上的合成資料及真實 OpenAI Podman Trace：

- Provider：`openai`；Model：`gpt-5.4-mini`。
- Status：`completed`；Tool Calls：**6 次成功、0 次失敗**。
- LLM 請求嘗試：**7 次**（0 次重試）；完整耗時：**9.1516 秒**。
- 來源引用稽核：`scripts/audit_trace.py` 通過。
- pandas Ground Truth：Tech 總營收 6,000；Tech 最佳地區 North，營收 2,800。

詳細過程、Arguments 和 Observation 參見 `documents/evidence/success_case/`。

## 失敗證據

- F01 `COLUMN_NOT_FOUND`：欄位不存在；要求使用者確認欄位名稱。
- F02 `TYPE_MISMATCH`：文字欄位求平均；要求改用數值欄位或適當操作。

F01/F02 透過 ScriptedLLM 產生固定呼叫，實際運作的是本系統的 LangGraph 與 pandas Tool，**不是**付費 OpenAI API 的自然語言失敗實測。

## 重現方式

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/failure_cases.py
.\.venv\Scripts\python.exe scripts/audit_trace.py documents/evidence/success_case/openai_podman_trace.json
podman build -t data-analysis-agent:hw2 -f Containerfile .
podman run --rm data-analysis-agent:hw2 --csv data/sample_sales.csv --inspect-only
```

真實 LLM 測試需要在 `.env` 中設定合法 API Key，指令見 README。

**限制：** 一個成功案例不代表所有輸入都成功；`completed` 不能取代 Task Success Rate 或 Numerical Accuracy 的正式評估。系統目前未包含跨 Session Checkpoint、語意對應確信度模組，以及對最終回答的逐項程式化數值查核。
