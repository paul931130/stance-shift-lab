# Model qualification before formal runs

## Synthetic canary

先驗證模型能否遵守最小引用與立場格式，再把它放進正式佇列：

```powershell
python scripts\run_model_canary.py --model ollama/qwen3:14b
```

通過 canary 的 `ollama/qwen3:8b` 也可用同一指令驗證；它是唯一不需 `allow_small_model` 覆寫即可進正式協議的 14B 以下模型。

canary 只建立 in-memory synthetic report，檢查：

- JSON schema、`action`、`confidence`、`expected_return_pct`
- 引用的 evidence ID 全部存在
- switched round 的 BEAR prompt 必須輸出 Sell 與負向 forecast
- provider attempts 與 audit seed 是否回傳

`status=pass` 只代表格式與最小立場遵循通過，不代表模型有足夠的金融推理品質、速度或不洩漏能力。canary 不寫 SQLite、不建立正式 job、不納入 study report。

## Runtime settings

模型呼叫的 operational settings 不改變 `StudyProtocol` 或 protocol hash：

- `RESEARCH_MODEL_TIMEOUT_SECONDS`：10–3600 秒，預設 240。
- `RESEARCH_MODEL_CONTEXT_LENGTH`：1024–131072，預設 8192；Ollama request 明確寫入 `options.num_ctx`。

每次 audit 會記錄實際 timeout 與 context，方便區分「模型不合格」和「執行環境太小」。
