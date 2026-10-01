# 執行 E2′（qwen3:32b，新版季度 180 案）

## 自己跑（建議，約 3 個動作）

1. **開 GPU**：GPUtw 控制台 → 執行個體 `61159cf5`（`ollama/ollama:0.35.0`）→ 重新啟動（原機器）。
2. **等約 10 分鐘**，打開 <http://127.0.0.1:8003/>，右上角模型狀態變綠。
3. 最上方「正式實驗」→ `協議 a3d65c6d（尚未排入）` →「排入批次檔…」→ 選 `docs/e2prime-batch-payload.json`。

之後看同一張卡片的進度即可（約 6.5 小時）。佇列清空後 GPU 再運轉 15 分鐘會自動關機（GPUtw 金鑰需有 `instances:manage`；卡片上顯示「自動關機失敗」時，跑完請自己在 GPUtw 停止）。出錯的案例會自動暫停並列在卡片上，按「全部繼續」即可。

## 交給 GPT／Codex 跑

把下面整段貼給它。它只負責執行與監控，不改協議、不改程式、不寫論文。

````text
你要在 Windows 專案 C:\Users\paul9\Desktop\114-2\專題\stance-shift-lab（git，分支 protocol/monthly-v3-0929.2，先用 git -c safe.directory=* log -1 確認）執行一個已事前登記的實驗並回報。執行方式與資料都已固定，照步驟做，不要更動任何設計。

固定事實
- 實驗 E2′：qwen3:32b、季度、協議 v3-0930.3，protocol_hash a3d65c6d056155d75c83536ab5106d826477b3f8c9d36913c49902e3884a2609，180 個資料集，已於 2026-09-30T03:42:09Z 事前登記。先讀 docs/e2prime-preregistration.md 與 docs/running-experiments.md。
- 服務：容器 stance-shift-lab-research-qwen-v2-1，http://127.0.0.1:8003（experiments/e2prime-qwen.yaml）。GET /health 應回 "version":"v3-0930.3"。
- 批次檔：docs/e2prime-batch-payload.json。
- GPU：GPUtw 執行個體 61159cf5-ae75-4995-b917-de46564a7722（RTX 5090，約 $0.75／小時，開機才計費），自帶映像 ollama/ollama:0.35.0，模型在 /vault，開機後約 10 分鐘可用。服務用 .env.research 的設定連線；不要讀取、印出或複製 .env.research 的任何值。

不能做
- 不改 research_service/ 的程式、協議、提示詞、資料集；不重新事前登記。
- 不啟動、停止或寫入其他服務或 volume（:8000、:8001、:8002、stance-shift-lab_research-data*、stance-shift-lab_research-data-qwen）。
- 不用 /api/jobs/{id}/clone，不改參數重跑失敗案例；失敗只記錄。
- 不提交、不推送。
- 任何原因停下時，先確認 GPU 已關機再回報。

步驟
1. 唯讀檢查：docker ps；確認 :8003 在跑且版本正確（沒跑就 docker compose -p stance-shift-lab -f experiments/e2prime-qwen.yaml up -d）。GET /api/studies/a3d65c6d056155d75c83536ab5106d826477b3f8c9d36913c49902e3884a2609/progress：total 180、not_created 180 才繼續；若已有工作，停下回報。
2. 開 GPU：GPUtw 重啟執行個體（mode "same"），等 RUNNING。
3. 等模型：每 60 秒查一次 GET http://127.0.0.1:8003/api/models，直到 ready 為 true 且列出 ollama/qwen3:32b、digest 為 030ee887880fc378860c2dd35101da424377520441ae4bfe7be6deff8ade7840（約 10 分鐘）。20 分鐘仍不行，或 digest 不同：關機、回報。
4. 排入：POST http://127.0.0.1:8003/api/studies/a3d65c6d056155d75c83536ab5106d826477b3f8c9d36913c49902e3884a2609/enqueue，內容為批次檔。應回 created 180。可以重送：已建立的案例會略過。
5. 監控：每 5 分鐘查一次 progress，記錄完成數、錯誤與 eta_hours。有錯誤暫停時，先確認 /api/models 仍 ready，再 POST …/resume-all；同一個案例最多恢復 2 次，仍失敗就記錄。
6. 收尾：全部到終態後，GET /api/gputw/status 確認 GPU；若 15 分鐘內沒有自動停止（autostop.enabled 為 false 時不會），用 GPUtw 停止執行個體，確認 STOPPED。
7. 匯出：GET /api/studies/<hash> 存成 E2prime-study.json、GET /api/studies/<hash>/summary.csv，放在 repo 之外。不解讀結果。

最後回報（繁體中文）：完成／失敗數與失敗清單（id、股票、日期、錯誤）；開機到關機時數與費用；digest 是否相符；是否做了清單以外的事；結果檔位置。
````
