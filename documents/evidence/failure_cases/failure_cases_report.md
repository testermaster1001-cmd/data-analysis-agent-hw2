# HW2 Failure Cases — 可重現執行證據

**測試方法：** 使用 ScriptedLLM 預先指定模型的工具呼叫與回覆；
實際執行的是正式 LangGraph Workflow 和 pandas Tool。**不是真實 OpenAI API 測試。**
所有測試資料為專案附帶的模擬 CSV，沒有真實個資。

## F01：欄位不存在

- 使用者輸入：請計算 Money 欄位的平均值。
- 指定 Tool：`calculate_statistics`
- Tool Arguments：`{"column": "Money", "operation": "mean", "source_id": "dataset"}`
- 預期錯誤代碼：`COLUMN_NOT_FOUND`
- 實際錯誤代碼：`COLUMN_NOT_FOUND`
- 根本原因：CSV Schema 沒有 Money 欄；不能推定 Money 與 Revenue 同義。
- 處理方法：回報缺少欄位，要求使用者確認實際欄位名稱。
- Agent 最終狀態：`needs_clarification`
- 工具成功 / 失敗：0 / 1
- 驗證結果：PASS

**Agent 回覆：**

> 尚未取得成功的資料分析工具結果，以下內容未經數值驗證：
> CSV 沒有 Money 欄位。請確認要分析哪個欄位；不能擅自將 Money 當成 Revenue。

詳細逐步紀錄：`f01_trace.json`。

## F02：非數值欄位求平均

- 使用者輸入：請計算 Category 欄位的平均值。
- 指定 Tool：`calculate_statistics`
- Tool Arguments：`{"column": "Category", "operation": "mean", "source_id": "dataset"}`
- 預期錯誤代碼：`TYPE_MISMATCH`
- 實際錯誤代碼：`TYPE_MISMATCH`
- 根本原因：Category 是文字型別（object），不符合 mean 運算需要數值的條件。
- 處理方法：回報資料型態不符，要求改用數值欄位或其他適合的統計方式。
- Agent 最終狀態：`needs_clarification`
- 工具成功 / 失敗：0 / 1
- 驗證結果：PASS

**Agent 回覆：**

> 尚未取得成功的資料分析工具結果，以下內容未經數值驗證：
> Category 是文字分類欄位，不能計算數值平均；請改用數值欄位。

詳細逐步紀錄：`f02_trace.json`。

## 執行指令與限制

在專案根目錄執行 `python scripts/failure_cases.py`，產生本報告與每個測試的 JSON Trace。
上述測試只證明正式 Graph 與資料工具遇到指定錯誤時的處理，不能用來宣稱 GPT-5.4 mini
在真實自然語言提問中一定會先呼叫錯誤工具。實際模型可能先依 Schema 要求確認，這也是合理的防錯處理。
