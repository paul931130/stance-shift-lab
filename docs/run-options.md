# 執行方式：網頁研究台、Docker 與 Codespaces

這份文件是 [README](../README.md) 的詳細版，說明 CLI 以外的三種跑法。只想在終端機跑一個案例，照 README 的「安裝與 CLI」即可。

網頁研究台能做 CLI 做不到的事：180 個案例的資料就緒度、批次排程、四組配對統計、試跑檢查與事前登記、匯出研究產物 ZIP。三種跑法都能開網頁研究台，擇一即可。模型來源有三種：雲端模型 API、GPUtw 雲端 GPU、Ollama；Codespaces 沒有顯示卡，只接前兩種。

| | 跑法一：GitHub Codespaces | 跑法二：自己電腦 Docker | 跑法三：自己電腦 pip |
| --- | --- | --- | --- |
| 要安裝什麼 | 什麼都不用，只要瀏覽器 | Docker Desktop | Python 3.12 以上 |
| 研究台網址 | `https://<codespace 名稱>-8000.app.github.dev` | <http://127.0.0.1:8000/> | <http://127.0.0.1:8000/> |
| 雲端模型 API | ✅ | ✅ | ✅ |
| GPUtw 雲端 GPU | ✅ | ✅ | ✅ |
| Ollama | ❌ | ✅ 電腦上的 Ollama，或由 Docker 一起跑 | ✅ 電腦上的 Ollama |
| 資料存哪裡 | 那一台 Codespace（開新的一台就沒了） | 自己電腦 | 自己電腦（專案的 `research-data/`） |
| 費用 | 用自己 GitHub 帳號的 Codespaces 額度 | 免費 | 免費 |

不論哪種跑法，都要先準備下面的金鑰。

## 事前準備：金鑰

**資料來源（建立資料集要用，都免費）**

| 名稱 | 用途 | 去哪裡拿 |
| --- | --- | --- |
| `SEC_USER_AGENT` | 下載美國上市公司財報 | 不用申請，填 `你的名字 你的email` |
| `FRED_API_KEY` | 下載總經資料 | [FRED 申請頁](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `ALPHA_VANTAGE_API_KEY` | 下載新聞 | [Alpha Vantage 申請頁](https://www.alphavantage.co/support/#api-key) |

**模型（三選一）**

| 模型來源 | 要準備什麼 | 適合誰 |
| --- | --- | --- |
| 雲端模型 API（最簡單） | 一把 API key：[Gemini](https://aistudio.google.com/apikey)、[OpenRouter](https://openrouter.ai/) 或 OpenAI；模型名稱例如 `gemini/gemini-2.5-flash` | 大多數人；依用量付費 |
| 雲端租 GPU（GPUtw） | 依 [GPUtw 整合指南](gputw-integration.md) 開好 Ollama 執行個體並下載 `qwen3:14b`，記下位址與存取 key | 想用 `qwen3:32b` 等大模型、又沒有大顯示卡 |
| Ollama | 在電腦裝 [Ollama](https://ollama.com/) 並執行 `ollama pull qwen3:14b`；或讓 Docker 一起跑 Ollama，連安裝都不用（跑法二）。`qwen3:14b` 建議 16 GB 以上顯示卡記憶體 | 有好顯示卡；不想付 API 或租 GPU 的費用 |

詳細比較見 [選擇模型來源](model-sources.md)。

> **金鑰只填在研究台的設定區、`.env.research` 或 Codespaces Secrets，不要貼到聊天、issue 或 commit 裡。** 不小心外流了，就到申請的網站把那把作廢、重新產生。

## 跑法一：在 GitHub 上開（Codespaces）

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/paul931130/stance-shift-lab)

Codespace 是 GitHub 借你的一台雲端電腦，研究台在上面用同一個 Docker 映像執行。Codespace 沒有顯示卡，模型請用雲端模型 API 或 GPUtw。

### 第一次：建立 Codespace（只做一次）

1. **把金鑰存成 Codespaces Secrets（建議）**：GitHub 右上角頭像 → Settings → Codespaces → Secrets → New secret，逐一新增，Repository access 勾選 `stance-shift-lab`：
   - 資料來源：`SEC_USER_AGENT`、`FRED_API_KEY`、`ALPHA_VANTAGE_API_KEY`
   - 雲端模型 API：`GEMINI_API_KEY`（或 `OPENROUTER_API_KEY`／`OPENAI_API_KEY`）與 `RESEARCH_MODEL`
   - 或 GPUtw：`GPUTW_OLLAMA_BASE_URL`、`GPUTW_OLLAMA_API_KEY`
   - `RESEARCH_DEMO_MODE`，值填 `false`

   跳過也可以，開好後在研究台的「設定模型與金鑰」填，效果一樣。
2. **建立**：按上面的「Open in GitHub Codespaces」按鈕 → Create codespace。
3. **等它啟動**：第一次要下載約 2 GB，大約 5–10 分鐘。畫面是瀏覽器版的 VS Code，完成後會自動開新分頁，那就是研究台。
   - 沒有自動開：點 VS Code 下方的「連接埠（Ports）」分頁，在 8000 那一列按地球圖示。
   - 瀏覽器擋了彈出視窗：允許後再按一次地球圖示。
4. 接著照下方「[確認模型並開始研究](#確認模型並開始研究)」。

### 之後每次：打開「原本那台」

> **不要再按上面的按鈕或 Create codespace。** 那會開一台全新的 Codespace，裡面沒有你的資料集、上傳的 CSV、設定與實驗結果，全部要重來，還會多吃一份額度。

1. 到 <https://github.com/codespaces>，點你已經建立的那一台（名稱是隨機的兩三個英文字）。
2. 研究台會自動啟動，資料都還在。沒自動開的話，從「連接埠」分頁開。
3. 用完直接關分頁，閒置約 30 分鐘會自動停機，資料保留；想立刻停機省額度，在 codespaces 頁面該台的「⋯」→ Stop codespace。

| 開啟方式 | `research-inputs/` 上傳的 CSV | 資料集、設定、實驗結果 |
| --- | --- | --- |
| 從 github.com/codespaces 點既有的 Codespace（含停機後再開） | 保留 | 保留 |
| 在 Codespace 內執行 Rebuild Container | 保留 | **消失** |
| 按上方按鈕或 Create codespace 開新的 | **消失** | **消失** |

### Codespace 注意事項

- **改了 Secrets**：到 <https://github.com/codespaces> 把這台 Stop 再打開就會套用。不要用 Rebuild Container，會清掉資料集。
- **備份**：要刪除 Codespace 前，瀏覽器開 `https://<codespace 名稱>-8000.app.github.dev/api/backup` 下載整個研究資料庫 ZIP。上傳過的 CSV 請自己保留原檔。
- **更新程式**：在 VS Code 終端機執行 `git pull`，再執行 `./research.sh start`，資料不受影響。
- **存取**：8000 連接埠預設為私人，只有你的 GitHub 帳號登入後看得到；不要改成公開。

## 跑法二：在自己電腦跑（Docker）

Windows、macOS（Intel／Apple Silicon）、Linux 都用同一個 Docker 映像，電腦上不需要安裝 Python。資料存在自己電腦，關機重開都還在。

### 第一次（只做一次）

1. **安裝 Docker 並打開**：Windows／macOS 裝 [Docker Desktop](https://www.docker.com/products/docker-desktop/) 並啟動它（工具列看到鯨魚圖示）；Linux 裝 Docker Engine 加 Compose plugin。
2. **下載程式**：裝 [Git](https://git-scm.com/) 後執行下面指令；不想裝 Git，也可在 GitHub 頁面 Code → Download ZIP 後解壓縮。

   ```bash
   git clone https://github.com/paul931130/stance-shift-lab.git
   cd stance-shift-lab
   ```

3. **設定、檢查、啟動**（Windows 在專案資料夾開 PowerShell；macOS／Linux 開終端機）：

   ```powershell
   .\research.ps1 setup     # 依序填資料來源金鑰，再選模型來源 1／2／3
   .\research.ps1 doctor    # 檢查 Docker 與模型；「模型來源」一行是 [OK] 才算接上
   .\research.ps1 start     # 第一次會下載約 2 GB，需要幾分鐘
   ```

   ```bash
   ./research.sh setup
   ./research.sh doctor
   ./research.sh start
   ```

   `setup` 的模型選項：`1` Ollama、`2` GPUtw（填遠端位址與存取 key）、`3` 雲端模型 API（選供應商、貼金鑰、填模型名稱）。每一題直接按 Enter 會保留原值。macOS／Linux 選 `1` 後會再問 Ollama 要用電腦上裝好的，還是讓 Docker 一起跑（可選用 NVIDIA 顯示卡）；選 Docker 一起跑時，`start` 會自動下載模型。Windows 想讓 Docker 一起跑 Ollama，用下方的 docker compose 指令。
   - PowerShell 出現「已停用指令碼執行」：先執行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 再重試，或直接雙擊 `start-research.cmd` 啟動。
   - Linux 用本機 Ollama：要讓 Ollama 監聽 `0.0.0.0`，做法見 [Clone 後首次啟動](getting-started.md)；Windows／macOS 不需要。
   **不想用腳本？只用 docker compose 也可以**（任何作業系統都一樣）：

   ```bash
   cp research.env.example .env.research      # Windows：copy research.env.example .env.research
   # 用文字編輯器打開 .env.research，填入金鑰與 RESEARCH_MODEL
   docker compose -f compose.research.yaml up -d --build
   ```

   更新程式後用同一行指令重新建置；停止用 `docker compose -f compose.research.yaml stop`。

   **不想在電腦裝 Ollama？讓 Docker 一起跑 Ollama**：

   ```bash
   docker compose -f compose.research.yaml -f compose.ollama.yaml up -d --build
   docker compose -f compose.research.yaml -f compose.ollama.yaml exec ollama ollama pull qwen3:14b
   ```

   預設只用 CPU，14B 模型會很慢。有 NVIDIA 顯示卡（Linux，或 Windows 的 Docker Desktop 使用 WSL2）時，在兩行指令的 `-f compose.ollama.yaml` 後面再加 `-f compose.ollama-gpu.yaml`。macOS 的 Docker 用不到 Apple 晶片的 GPU，請直接在 Mac 安裝 Ollama。

4. **打開研究台**：瀏覽器開 <http://127.0.0.1:8000/>，接著照下方「[確認模型並開始研究](#確認模型並開始研究)」。

### 之後每次

1. 打開 Docker Desktop。
2. 在專案資料夾執行 `.\research.ps1 start`（macOS／Linux：`./research.sh start`），開 <http://127.0.0.1:8000/>。
3. 用完執行 `.\research.ps1 stop`（macOS／Linux：`./research.sh stop`），資料會留著。

### 本機注意事項

- **更新程式**：`git pull` 後再 `start`，資料不受影響。
- **備份**：Windows 執行 `.\research.ps1 backup`（存到 `backups\`）；macOS／Linux 瀏覽器開 <http://127.0.0.1:8000/api/backup> 下載 ZIP。
- **不要執行 `docker compose down -v`**，那會刪掉所有研究資料。

## 跑法三：pip 安裝後開網頁

照 README 的「[安裝](../README.md#安裝)」裝好後，三種模型來源都能接；少了 Docker，電腦上的 Ollama 直接用 `127.0.0.1:11434` 連，不用任何網路設定。

1. **啟動研究台**（在專案資料夾、虛擬環境已啟用）：

   ```bash
   stance-shift serve
   ```

   瀏覽器開 <http://127.0.0.1:8000/>。這個視窗要保持開著，按 Ctrl+C 停止。
2. **填設定**（已經用 `stance-shift` 或 `.env` 設過的可以跳過）：按「資料準備」頁的「設定模型與金鑰」：
   - 資料來源金鑰：`SEC_USER_AGENT`、`FRED_API_KEY`、`ALPHA_VANTAGE_API_KEY`。
   - 用雲端模型 API：在「雲端模型金鑰」填金鑰，「回測模型」填模型名稱（例如 `gemini/gemini-2.5-flash`）。
   - 用 GPUtw：在「GPUtw／遠端 Ollama」填 `GPUTW_OLLAMA_BASE_URL` 與 `GPUTW_OLLAMA_API_KEY`。
   - 用本機 Ollama：不用填，預設就是 `ollama/qwen3:14b`。
   - FNSPID 新聞檔：放在 `research-inputs/Stock_news.csv`，並把 `FNSPID_NEWS_PATH` 填成 `research-inputs/Stock_news.csv`。

   按「儲存設定」立即生效，設定存在專案的 `research-data/` 資料夾，下次啟動還在。
3. 接著照下方「[確認模型並開始研究](#確認模型並開始研究)」。

**之後每次**：進專案資料夾 → 啟用虛擬環境 → `stance-shift serve`（或直接用 `stance-shift` 在終端機跑）。**更新程式**：`git pull` 後再執行一次 `pip install .`。**備份**：研究資料全部在 `research-data/`，複製這個資料夾即可。

pip 跑法與 Docker 用的是同一份程式；遇到安裝問題，改用跑法二最省事。

## 確認模型並開始研究

三種跑法打開研究台後都一樣：

1. **確認模型**：看頁面上方的模型狀態。
   - 顯示「雲端模型 · … · 已設定」或「Ollama 已連線」：可以開始。
   - 顯示「模型未連線」或「缺少 … key」：按「資料準備」頁標題下方的「設定模型與金鑰」，在「回測模型」填模型名稱（例如 `gemini/gemini-2.5-flash`、`ollama/qwen3:14b`），在「雲端模型金鑰」或「GPUtw／遠端 Ollama」填金鑰，按「儲存設定」，立即生效、不用重啟。
2. **（選用）加入 FNSPID 新聞**：把已授權、[篩選過](quickstart-v3.md)的 `Stock_news.csv` 放進專案的 `research-inputs/` 資料夾（Codespace 可直接拖進 VS Code 左側檔案樹）。沒有也能只用 Alpha Vantage 新聞。
3. **建立資料集**：「資料準備」頁選股票與研究分析日，按「啟動資料 Agent」。
4. **跑實驗**：「建立實驗」頁選剛建好的資料集，按「開始研究實驗」。
5. **看結果**：「Agent 執行」頁看進度，每個實驗可按「下載研究產物 ZIP」；完成後到「統計結果」比較 A/B/C/D。

**換模型**：隨時在「設定模型與金鑰」改，或重新執行 `setup`。只影響之後新建立的實驗，已建立的實驗不會變。

**常見問題**

- **一直出現 429（被限流）**：雲端 API 每分鐘次數有限，把 `RESEARCH_PARALLEL_WORKERS` 調成 1 或 2。研究台遇到 429 也會自動等待後重試。
- **GPUtw 會一直計費**：研究結束後到 GPUtw 控制台停止執行個體。
- **只想看介面、不接模型**：把 `RESEARCH_DEMO_MODE` 設為 `true` 後重新 `start`。展示模式會放入一筆固定的合成 NVDA 資料集，回應由內建程式產生，不呼叫任何外部服務，也不算正式研究結果；看完改回 `false`。

## 正式研究用的模型

框架預設模型是 `ollama/qwen3:14b`（16 GB 顯示卡即可）；本專題的正式實驗（E2、E2′）使用 `ollama/qwen3:32b`（需 32 GB，見 [GPUtw 雲端 GPU](gputw-integration.md)）。OpenRouter 的 `openrouter/qwen/qwen3-14b` 與 `ollama/qwen3:14b` 是同一個模型。`ollama/qwen3:8b` 已通過本專案的相容性測試（canary），也可用於正式研究；其他 14B 以下的模型只算測試。改用 Gemini 等其他雲端模型時，需在研究紀錄中註明。

## 進階：終端機指令

研究操作用 `stance-shift`（見 README 的「[安裝與 CLI](../README.md#安裝與-cli)」）；用 Docker 時，`./research.sh cli`（Windows：`docker compose -f compose.research.yaml run --rm research python -m research_service.cli`）會在容器內執行同一個 `stance-shift`，和網頁研究台共用資料。

`research.sh`／`research.ps1` 負責 Docker 的安裝設定、啟停、檢查與日誌：`setup`、`start`、`stop`、`status`、`logs`、`doctor`、`test`，Windows 另有 `backup`。`research.ps1` 裡的 `collect`、`run`、`jobs` 等研究指令仍可使用，但之後會由跨平台的 `stance-shift` 取代。

`stance-shift power-plan`（研究設計模擬）與 `stance-shift model-canary`（用合成資料檢查模型是否相容）不會建立正式案例。
