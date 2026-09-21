# 展示模式

展示模式用來讓沒有 API key、Ollama 或 GPU 的使用者檢查研究台介面與可追溯工作流。

在 `.env.research` 設定：

```text
RESEARCH_DEMO_MODE=true
```

重新啟動服務後，系統會建立一筆固定的合成 NVDA 資料集，並把模型選項切換成
`ollama/demo-synthetic`。這個 provider 只回傳固定的 schema-valid JSON，不讀取網路、
不呼叫模型、不使用正式資料，也不會被當成模型資格或績效證據。

展示結束後改回 `RESEARCH_DEMO_MODE=false`。保留在 demo 模式的工作只代表 UI／流程
檢查；正式案例仍必須通過真實模型資格預檢、資料品質門檻與研究協議規則。
