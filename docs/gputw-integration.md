# GPUtw 雲端 GPU

GPUtw 出租獨佔 GPU 的容器，開機（RUNNING）就計費，不論有沒有在用。研究台只把模型請求送到它上面的 Ollama；研究協議、資料集與結果都留在本機。

## 一次性設定

### 1. 用固定版本的 Ollama 映像開機器

**不要用 GPUtw 的「Ollama + Open WebUI」範本。** 範本把模型存在容器自己的磁碟，不讀 `/vault`，每次重開機模型清單都是空的，只能重新下載約 20 GB；範本的 Ollama 也是 `latest`，版本會變。

改用「自帶映像」（GPUtw 控制台 → 部署 → Custom image，或 API `customImage`）：

| 欄位 | 值 |
|---|---|
| 映像 | `ollama/ollama:0.35.0`（固定版本，不要用 `latest`） |
| 環境變數 | `OLLAMA_MODELS=/vault/ollama/models`、`OLLAMA_HOST=0.0.0.0:11434`、`OLLAMA_KEEP_ALIVE=24h`、`OLLAMA_NUM_PARALLEL=4` |
| Web UI | 開啟，連接埠 `11434` |
| SSH | **關閉**（Ollama 映像開 SSH 會讓部署直接失敗） |
| GPU | RTX 5090 32GB 可跑 `qwen3:32b` |

模型存在 `/vault`，跨執行個體保留；第一次開機後在研究台以外執行一次 `ollama pull qwen3:32b`（或透過 API `POST /api/pull`），之後任何一台用同樣設定的機器都讀得到。

### 2. 保護連接埠

在執行個體的連接埠設定把 `11434` 設為 **unlisted（未公開＋密碼）**。不要設成 public：Ollama 本身沒有驗證。

### 3. 填入 `.env.research`

```text
GPUTW_API_KEY=...            # instances:read，只查狀態
GPUTW_INSTANCE_ID=<執行個體 ID>
GPUTW_OLLAMA_BASE_URL=https://11434-<執行個體 ID>.gputw.ai
GPUTW_OLLAMA_PASSWORD=...    # 上一步設定的連接埠密碼
GPUTW_MANAGE_API_KEY=...     # 選填，instances:manage，讓研究台在佇列閒置時自動關機
RESEARCH_GPUTW_AUTOSTOP_MINUTES=15
```

改完重新啟動研究服務。金鑰與密碼只放在 `.env.research`（Git 忽略），不要貼到聊天或 issue。

## 每次跑實驗

1. 在 GPUtw 控制台開機（「重新啟動」選原機器）。
2. 等約 **10 分鐘**：Ollama 要從 `/vault` 讀 20 GB 的模型進顯示卡記憶體。研究台右上角的模型狀態變綠後才能排入工作；關機時它會直接說「遠端 GPU 目前連不上」。
3. 確認模型版本：`/api/models` 列出的 `qwen3:32b` digest 應為 `030ee887880f…`（E2 與 E2′ 使用的版本）。
4. 在網頁最上方「正式實驗」排入批次、看進度。
5. 佇列清空 15 分鐘後，若設定了 `GPUTW_MANAGE_API_KEY`，研究台會自動關機；否則請自己在控制台停止。

## 費用參考（RTX 5090，2026-10）

| 項目 | 時間 | 約略費用 |
|---|---|---|
| 開機到模型可用 | 10 分鐘 | $0.13 |
| 季度 180 案（逐一處理） | 6.5 小時 | $5 |
| 季度 180 案（`RESEARCH_OLLAMA_PARALLEL=4`） | 約 3 小時 | $2.4 |

價格以 GPUtw 當時的報價為準。

## 終端檢查

```powershell
.\research.ps1 gputw-status
.\research.ps1 gputw-resources
.\research.ps1 models
```

這些都是唯讀操作。唯一會改變執行個體狀態的是自動關機，而且只會「停止」，從不開機。
