# 給 GPT／Codex 的任務：執行 E2′（qwen3:32b，新版季度 180 案）

把下面「提示詞」整段貼給執行的 GPT／Codex。它只負責**執行與監控**，不改協議、不改程式、不寫論文。

---

## 提示詞

你要在 Windows 上的專案 `C:\Users\paul9\Desktop\114-2\專題\stance-shift-lab`（git 倉庫，分支 `protocol/monthly-v3-0929.2`，執行前先用 `git -c safe.directory=* log -1` 確認包含提交 `a389bb1`，且 `docs/e2prime-batch-payload.json` 與 `docs/e2prime-preregistration.md` 存在）替一個已事前登記的實驗跑完 180 個案例，並回報結果。這是研究專題（股票決策的立場交換辯論實驗，模型 qwen3:32b，遠端 GPU 在 GPUtw），執行方式與資料已固定，你的工作是照步驟執行、監控、記錄，不要自己更動任何設計。

### 已固定的事實（不要更動）

- 實驗 E2′：qwen3:32b、季度設計、協議版本 v3-0930.3。protocol_hash：`a3d65c6d056155d75c83536ab5106d826477b3f8c9d36913c49902e3884a2609`。事前登記時間 2026-09-30T03:42:09Z，180 個資料集，紀錄在 `docs/e2prime-preregistration.md`，請先讀。
- 服務：容器 `stance-shift-lab-research-qwen-v2-1`，位址 `http://127.0.0.1:8003`，映像 `stance-shift-lab-research-qwen:v3-0930.3`，資料庫 volume `stance-shift-lab_research-data-qwen-v2`，由 `compose.qwen-v2.yaml` 啟動。健康檢查 `GET /health` 應回傳 `"version":"v3-0930.3"`。
- 180 個案例的請求內容已存在 `docs/e2prime-batch-payload.json`（格式 `{"cases":[{dataset_id, analysis_date, model}, ...]}`），對應事前登記的同一批資料集。
- 遠端模型：GPUtw 執行個體 `37060bb7-c968-4446-8f74-f8c718b79173`（RTX 5090，約 $0.77／小時，開機才計費）。Ollama 埠 11434 是「unlisted＋密碼」，服務已用 `.env.research` 的設定自己登入。**不要讀取、印出或複製 `.env.research` 的任何值**（含 API key、密碼）。

### 絕對不能做

- 不要修改 `research_service/` 程式碼、協議、提示詞、資料集，也不要重新事前登記或改事前登記檔。
- 不要啟動、停止或寫入其他服務或 volume：`:8000`（`stance-shift-lab-research-gemini-1`）、`:8001`（E2，唯讀封存 volume `stance-shift-lab_research-data-qwen`）、`:8002`（`stance-shift-lab-research-monthly-1`）、`stance-shift-lab_research-data`、`…-data-monthly`。
- 不要提交資料檔或資料庫；不要用 `git push --force`；不要提交或推送任何東西，除非我另外要求。
- 不要複製、重試或改參數來「修復」失敗的案例（不要用 `/api/jobs/{id}/clone`）。失敗只記錄並回報。
- 不要留著 GPU 空轉。任何原因停下時，都先關機再回報。

### 環境提醒

- 在 Git Bash 執行 docker 時，容器內路徑要加 `MSYS_NO_PATHCONV=1`；用 heredoc 餵 Python 給 `docker exec` 要加 `-i`。
- 不要用會空等很久的 `sleep`；用「直到條件成立」的迴圈，並且設上限。

### 步驟

1. **檢查現況（唯讀）**：`docker ps`；確認 `:8003` 容器在跑且版本為 v3-0930.3（若沒跑，用 `docker compose -p stance-shift-lab -f compose.qwen-v2.yaml up -d` 啟動）。確認 `:8000`、`:8001` 的容器沒有在跑（`:8002` 月度服務在跑是正常的，不用動）。查詢 `GET /api/studies/a3d65c6d056155d75c83536ab5106d826477b3f8c9d36913c49902e3884a2609`，確認 `preregistration.dataset_ids` 有 180 個、`frozen_at` 是 2026-09-30T03:42:09Z。再查 `GET /api/jobs`，確認這個 protocol_hash 底下**還沒有任何 job**（若已有，停下來回報，不要重複建立）。
2. **開 GPU**：用 GPUtw 啟動執行個體 `37060bb7-c968-4446-8f74-f8c718b79173`（重啟模式用「same」），等到狀態 RUNNING。記下開機時間。
3. **確認模型**：透過服務容器呼叫 Ollama（用 `docker exec -i stance-shift-lab-research-qwen-v2-1 python` 載入 `research_service.models.gputw_urlopen`，讀 `GPUTW_OLLAMA_BASE_URL` 環境變數，請求 `/api/tags`；密碼登入由該函式處理，你不需要也不要接觸密碼）。**必須看到 `qwen3:32b`，且 digest 為 `030ee887880fc378860c2dd35101da424377520441ae4bfe7be6deff8ade7840`。** 若清單是空的（重開機後可能發生），用 `/api/pull`（`{"model":"qwen3:32b"}`）重新拉取，約 7 分鐘；拉完再確認 digest 完全相同。digest 不同就停下、關機、回報。
4. **建立批次**：把 `docs/e2prime-batch-payload.json` 的內容 `POST` 到 `http://127.0.0.1:8003/api/batches`，應回傳 180 個 job id。存下這些 id。**只送一次**。
5. **監控到跑完**：每隔幾分鐘查 `GET /api/jobs`（不要更頻繁），統計 完成／執行中／失敗／暫停 的數量，記錄進度與已用時間。案例會自己依序執行，你不用手動逐一觸發。
   - 若有案例卡在暫停或因供應商逾時失敗，只能用 `POST /api/jobs/{id}/resume` 恢復，最多對同一個案例恢復 2 次；仍失敗就記錄它的 id、ticker、日期、錯誤訊息，不要再處理。
   - 若 GPU 或 Ollama 中途斷線，重新確認 `/api/tags` 與 digest，再對暫停的案例 `resume`。
6. **收尾**：全部案例都到終態（完成或已記錄的失敗）後，**立刻關閉 GPU 執行個體**，確認狀態為 STOPPED，記下總開機時數與估計費用。
7. **驗證與匯出**：`GET /api/studies/a3d65c6d…a2609` 存成 `E2prime-study.json`（放在 repo 之外，例如你的暫存資料夾）；並匯出 `GET /api/studies/a3d65c6d…a2609/summary.csv`。不要解讀顯著性、不要寫結論。

### 最後回報（繁體中文，簡潔）

- 完成／失敗案例數；失敗案例清單（id、股票、日期、錯誤）。
- 開機到關機的總時數與估計費用；模型 digest 是否與 E2 相同。
- 服務回報的資料：四組各自的案例數、被移除數字（redaction）的呼叫數、任何「未達正式樣本」或品質阻擋的提示原文。
- 你有沒有做任何上面「絕對不能做」以外的動作，以及任何不確定的地方。
- 結果檔的位置。

---

## 備註（給你自己看，不用貼）

- 這個 GPU 每次重開機後 Ollama 的模型清單可能是空的（2026-09-30 已發生一次，重拉後 digest 與 E2 相同）。提示詞已把重拉寫進第 3 步。
- E2 當年的 180 案約需 5–7 小時 GPU。
- 執行前，`compose.qwen-v2.yaml`、`docs/e2prime-preregistration.md`、本檔與批次檔要先提交，這樣 GPT 讀到的倉庫狀態才和預註冊一致。
