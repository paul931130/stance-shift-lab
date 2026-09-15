# GPUtw 雲端 GPU 整合

GPUtw 在這個研究台中扮演「遠端 GPU 執行個體」的角色。研究協議、資料集與結果仍由本機研究服務管理；GPUtw 的 Ollama／Open WebUI 範本提供較快的模型推論。研究服務目前只呼叫 GPUtw 的唯讀狀態 API，不會自動建立、停止、重啟或刪除執行個體。

## 建議的第一次設定

1. 在 [GPUtw Templates](https://gputw.ai/dashboard/templates) 建立 Ollama 範本執行個體，選擇足以載入研究模型的 GPU。
2. 在容器內確認 Ollama 已啟動並下載模型，例如 `qwen3:14b`。模型權重、資料集和輸出放在 `/vault`；`/workspace` 會隨執行個體生命週期消失。
3. 只開放必要的 HTTP 連接埠。把 Ollama 端點設成受保護、未公開或透過安全 tunnel 使用；不要把沒有驗證的 `11434` 直接暴露到網際網路。
4. 在研究台的「設定資料來源與模型」填入：

   - `GPUTW_API_URL`：保留 `https://gputw.ai`。
   - `GPUTW_API_KEY`：GPUtw API 金鑰。只需 `instances:read` 就能檢查狀態與資源。
   - `GPUTW_INSTANCE_ID`：GPUtw 執行個體 ID；不填時狀態按鈕會列出 active 執行個體。
   - `GPUTW_OLLAMA_BASE_URL`：遠端 Ollama 的 HTTP 位址，例如 `https://<受保護端點>`。
   - `GPUTW_OLLAMA_API_KEY`：只有遠端 Ollama 端點另外要求 Bearer key 時才填。

   也可以在本機終端執行 ` .\research.ps1 setup `，逐項按 Enter 略過不使用的欄位。
5. 重啟研究服務後，在網頁設定區按「檢查 GPUtw 狀態」，再按「模型」重新整理。若遠端 Ollama 回傳模型清單，模型欄位會顯示 `ollama/qwen3:14b`，研究流程不需要修改。
6. 先只跑一個既有完整案例。確認 `/api/models` 有模型、研究終端出現模型回應、結果可匯出後，再開始批次實驗。

## 終端檢查

```powershell
.\research.ps1 gputw-status
.\research.ps1 gputw-resources
.\research.ps1 gputw-active
.\research.ps1 models
```

`gputw-status`、`gputw-resources` 和 `gputw-active` 都是唯讀操作。沒有設定 key 時會清楚顯示「尚未設定」，不會把連線錯誤誤報為就緒，也不會把 API key 回傳到畫面或工作紀錄。

## 金鑰與額度

建議另外簽發一把只含 `instances:read` 的狀態金鑰；若只需要把資料推送到 Vault，使用只含 `vault:write` 的上傳權杖。部署與停止執行個體才需要 `instances:create`／`instances:manage`，而 `instances:exec` 會以 root 身分執行指令，應保留給你自己的專用金鑰。研究完成後在 GPUtw 控制台停止執行個體，避免持續計費。

大型資料（例如新聞 CSV）請放進 `/vault` 或使用可續傳上傳，不要把它放在 `/workspace`。本機研究台的 SQLite、研究快照與 API key 仍是另一套資料，不會因 GPUtw 狀態查詢而自動上傳。

## 這次整合的邊界

本版本不從研究台自動部署 GPUtw，也不自動上傳本機資料，避免在沒有明確確認時產生運算或儲存費用。若日後要做「按一下就建立 GPU、跑完自動停止」的工作流，需要另外加入明確的成本上限、執行個體範本 ID、佇列、逾時和 `instances:create`／`instances:manage` 金鑰。
