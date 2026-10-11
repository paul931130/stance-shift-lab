# 選擇模型來源

研究台一次使用一個模型來源。三種都走同一個 Docker 服務與同一套研究流程，差別只在模型在哪裡執行、誰付費。

| | 自己電腦 | 雲端租 GPU | 雲端模型 API |
| --- | --- | --- | --- |
| 模型在哪裡跑 | 本機 Ollama | GPUtw 遠端 Ollama | OpenRouter／OpenAI／Gemini |
| 需要準備 | 安裝 Ollama、下載模型 | GPUtw 帳號與執行個體 | 一把 API key |
| 費用 | 免費（電費） | 依 GPU 使用時間計費，用完要停機 | 依 token 用量計費 |
| 硬體 | 建議 16 GB 以上 VRAM；CPU 可跑但很慢 | 不需要 | 不需要 |
| Codespaces 可用 | 否（Codespace 沒有 GPU） | 是 | 是 |
| 不用 Docker（pip）可用 | 是 | 是 | 是 |
| 可跑本專題正式實驗的 `qwen3:32b` | 需 32 GB 顯示卡 | 是（RTX 5090） | 模型名稱不同，需在研究紀錄中註明 |

最簡單的是**雲端模型 API**：不用裝任何模型或租機器，填一把金鑰即可。

## 設定方式

在自己電腦上執行 setup，會問「模型要在哪裡執行？」，選 1／2／3 後只問該來源需要的欄位：

```powershell
.\research.ps1 setup      # Windows
```

```bash
./research.sh setup       # macOS／Linux／Codespace 終端機
```

設定完用 `doctor` 確認，輸出中的「模型來源」一行會顯示目前使用哪一種、是否連得上：

```bash
./research.sh doctor      # Windows：.\research.ps1 doctor
```

切換來源時重新執行 setup 即可；選本機或雲端 API 時會自動清除 GPUtw 位址，避免舊設定蓋過新選擇。改完執行 `start` 讓服務套用。

### 1. 自己電腦（本機 Ollama）

1. 安裝 [Ollama](https://ollama.com/)，執行 `ollama pull qwen3:14b`。
2. setup 選 `1`，模型保留 `ollama/qwen3:14b`。
3. Linux 需讓 Ollama 監聽 `0.0.0.0`（見 [Clone 後首次啟動](getting-started.md)）；Windows／macOS 不需要。
4. 不想在電腦安裝 Ollama：macOS／Linux 的 setup 選 `1` 後選「讓 Docker 一起跑」，或在 `.env.research` 設 `RESEARCH_OLLAMA_CONTAINER=true`（有 NVIDIA 顯示卡設 `gpu`），`start` 會自動下載模型。Windows 用 `docker compose -f compose.research.yaml -f compose.ollama.yaml up -d --build`。

### 2. 雲端租 GPU（GPUtw）

1. 依 [GPUtw 整合指南](gputw-integration.md) 建立 Ollama 執行個體並下載 `qwen3:14b`。
2. 先在瀏覽器開 `你的位址/api/tags`，看得到模型清單才代表位址正確。
3. setup 選 `2`，填入遠端 Ollama 位址與存取 key。
4. 研究結束後到 GPUtw 控制台停止執行個體，避免持續計費。

### 3. 雲端模型 API

1. 申請 [OpenRouter](https://openrouter.ai/)、OpenAI 或 Gemini 的 API key。
2. setup 選 `3`，選擇供應商並貼上金鑰。OpenRouter 預設 `openrouter/qwen/qwen3-14b`，與正式協議同一個模型。
3. 研究台每次呼叫都要求模型依固定 JSON schema 回答；seed 只傳給支援的供應商（Gemini 不支援，稽核欄位 `seed_applied=false`）。
4. Gemini：Flash／Flash-Lite 會關閉思考，與本機 Ollama 一致；Pro（例如 `gemini/gemini-3.1-pro-preview`）無法關閉思考，改為低強度思考並額外給 2048 token，稽核記錄 `max_tokens_sent` 與 `reasoning_effort`。以合成案例實測，Pro 比 Flash 更少違反「只用來源數字」規則，但仍會自行計算成長率或漏引來源，被拒的步驟需續跑。
5. 額度等級較低時（例如 Gemini 3.1 Pro 每分鐘 25 次），研究台遇到 429 會依供應商指示的秒數等待後重試（最多 6 次，記錄於 `rate_limit_waits`）；仍常被限流時，把 `RESEARCH_PARALLEL_WORKERS` 調成 1 或 2。

## 在 Codespaces 使用

Codespace 不讀 setup 的互動輸入，而是讀 GitHub → Settings → Codespaces → Secrets（授權給這個 repo），每次啟動寫入 `.env.research`：

| 來源 | 需要的 secrets |
| --- | --- |
| 雲端租 GPU | `GPUTW_OLLAMA_BASE_URL`、`GPUTW_OLLAMA_API_KEY`（端點有保護時） |
| 雲端模型 API | `OPENROUTER_API_KEY`（或 `OPENAI_API_KEY`／`GEMINI_API_KEY`）與 `RESEARCH_MODEL`，例如 `openrouter/qwen/qwen3-14b` |

另外把 `RESEARCH_DEMO_MODE` 設為 `false`（改值，不要只刪除）。改完 secrets 後，到 <https://github.com/codespaces> 把這台 Codespace 停止（Stop codespace）再打開，每次啟動都會重新寫入；也可以直接在終端機執行 `./research.sh setup` 或在網頁「設定模型與金鑰」填寫。不要用 Rebuild Container，重建會清掉資料集與實驗結果。
