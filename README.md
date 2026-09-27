# Stance Shift Research v3

[![CI](https://github.com/paul931130/stance-shift-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/paul931130/stance-shift-lab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

這是一個用 AI 模型做股票回測的研究台：先蒐集某檔股票在某個日期之前能取得的技術面、基本面、新聞、總經資料，再讓模型用四種方式做買賣判斷，比較哪一種比較準：

- **A 單次判斷**：問一次。
- **B 獨立投票**：同樣問題問 7 次再投票。
- **C 固定立場辯論**：看多、看空各自辯論 3 輪後裁決。
- **D 立場交換辯論**：辯論中途讓雙方交換立場。

四組用的是同一份資料，差別只在決策方式。整個研究台是一個網頁，在瀏覽器操作。

## 快速開始

有三種跑法，擇一即可。下表比較前兩種；已經有 Python、只接 GPUtw 或本機 Ollama 的人，也可以用[跑法三：直接 pip 安裝](#跑法三不用-docker直接-pip-安裝)。

| | 在 GitHub 上開（Codespaces） | 在自己電腦跑（Docker） |
| --- | --- | --- |
| 要安裝什麼 | 什麼都不用，只要瀏覽器 | Docker Desktop |
| 研究台網址 | `https://<codespace 名稱>-8000.app.github.dev` | <http://127.0.0.1:8000/> |
| 可用的模型 | 雲端模型 API、GPUtw 租 GPU | 雲端模型 API、GPUtw 租 GPU、自己電腦的 Ollama |
| 資料存哪裡 | 那一台 Codespace（開新的一台就沒了） | 自己電腦 |
| 費用 | 用自己 GitHub 帳號的 Codespaces 額度 | 免費 |

不論哪種跑法，都要先準備下面的金鑰。

### 事前準備：金鑰

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
| 雲端租 GPU（GPUtw） | 依 [GPUtw 整合指南](docs/gputw-integration.md) 開好 Ollama 執行個體並下載 `qwen3:14b`，記下位址與存取 key | 想用正式協議的 `qwen3:14b`、又沒有顯示卡 |
| 自己電腦的 Ollama | 裝 [Ollama](https://ollama.com/) 並執行 `ollama pull qwen3:14b`，或讓 Docker 一起跑 Ollama（見跑法二）；建議 16 GB 以上顯示卡記憶體 | 有好顯示卡；只能在本機 Docker 跑法使用 |

詳細比較見 [選擇模型來源](docs/model-sources.md)。

> **金鑰只填在研究台的設定區、`.env.research` 或 Codespaces Secrets，不要貼到聊天、issue 或 commit 裡。** 不小心外流了，就到申請的網站把那把作廢、重新產生。

### 跑法一：在 GitHub 上開（Codespaces）

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/paul931130/stance-shift-lab)

Codespace 是 GitHub 借你的一台雲端電腦，研究台在上面用同一個 Docker 映像執行。Codespace 沒有顯示卡，模型只能用雲端模型 API 或 GPUtw。

#### 第一次：建立 Codespace（只做一次）

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

#### 之後每次：打開「原本那台」

> **不要再按上面的按鈕或 Create codespace。** 那會開一台全新的 Codespace，裡面沒有你的資料集、上傳的 CSV、設定與實驗結果，全部要重來，還會多吃一份額度。

1. 到 <https://github.com/codespaces>，點你已經建立的那一台（名稱是隨機的兩三個英文字）。
2. 研究台會自動啟動，資料都還在。沒自動開的話，從「連接埠」分頁開。
3. 用完直接關分頁，閒置約 30 分鐘會自動停機，資料保留；想立刻停機省額度，在 codespaces 頁面該台的「⋯」→ Stop codespace。

| 開啟方式 | `research-inputs/` 上傳的 CSV | 資料集、設定、實驗結果 |
| --- | --- | --- |
| 從 github.com/codespaces 點既有的 Codespace（含停機後再開） | 保留 | 保留 |
| 在 Codespace 內執行 Rebuild Container | 保留 | **消失** |
| 按上方按鈕或 Create codespace 開新的 | **消失** | **消失** |

#### Codespace 注意事項

- **改了 Secrets**：到 <https://github.com/codespaces> 把這台 Stop 再打開就會套用。不要用 Rebuild Container，會清掉資料集。
- **備份**：要刪除 Codespace 前，瀏覽器開 `https://<codespace 名稱>-8000.app.github.dev/api/backup` 下載整個研究資料庫 ZIP。上傳過的 CSV 請自己保留原檔。
- **更新程式**：在 VS Code 終端機執行 `git pull`，再執行 `./research.sh start`，資料不受影響。
- **存取**：8000 連接埠預設為私人，只有你的 GitHub 帳號登入後看得到；不要改成公開。

### 跑法二：在自己電腦跑（Docker）

Windows、macOS（Intel／Apple Silicon）、Linux 都用同一個 Docker 映像，電腦上不需要安裝 Python。資料存在自己電腦，關機重開都還在。

#### 第一次（只做一次）

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

   `setup` 的模型選項：`1` 自己電腦的 Ollama、`2` GPUtw（填遠端位址與存取 key）、`3` 雲端模型 API（選供應商、貼金鑰、填模型名稱）。每一題直接按 Enter 會保留原值。
   - PowerShell 出現「已停用指令碼執行」：先執行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 再重試，或直接雙擊 `start-research.cmd` 啟動。
   - Linux 用本機 Ollama：要讓 Ollama 監聽 `0.0.0.0`，做法見 [Clone 後首次啟動](docs/getting-started.md)；Windows／macOS 不需要。
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

#### 之後每次

1. 打開 Docker Desktop。
2. 在專案資料夾執行 `.\research.ps1 start`（macOS／Linux：`./research.sh start`），開 <http://127.0.0.1:8000/>。
3. 用完執行 `.\research.ps1 stop`（macOS／Linux：`./research.sh stop`），資料會留著。

#### 本機注意事項

- **更新程式**：`git pull` 後再 `start`，資料不受影響。
- **備份**：Windows 執行 `.\research.ps1 backup`（存到 `backups\`）；macOS／Linux 瀏覽器開 <http://127.0.0.1:8000/api/backup> 下載 ZIP。
- **不要執行 `docker compose down -v`**，那會刪掉所有研究資料。

### 跑法三：不用 Docker，直接 pip 安裝

適合已經有 Python、只打算接**雲端租 GPU（GPUtw）或自己電腦的 Ollama**（也可接雲端模型 API）的人。少了 Docker，本機 Ollama 直接用 `127.0.0.1:11434` 連，不用任何網路設定。

1. **安裝 Python 3.12 以上**（[python.org](https://www.python.org/downloads/)；Windows 安裝時勾選「Add python.exe to PATH」）。
2. **下載程式並安裝**：

   ```bash
   git clone https://github.com/paul931130/stance-shift-lab.git
   cd stance-shift-lab
   python -m venv .venv
   # 啟用虛擬環境：Windows 用 .venv\Scripts\activate；macOS／Linux 用 source .venv/bin/activate
   pip install .
   ```

   要用 FinBERT 分析新聞情緒（正式實驗需要），改成 `pip install ".[finbert]"`，會多下載約 1–2 GB。
3. **準備模型（二選一）**：
   - 自己電腦的 Ollama：安裝 [Ollama](https://ollama.com/) 並執行 `ollama pull qwen3:14b`，保持 Ollama 開著。
   - GPUtw 雲端 GPU：照 [GPUtw 整合指南](docs/gputw-integration.md) 開好執行個體，記下遠端 Ollama 位址與存取 key。
4. **啟動研究台**（在專案資料夾、虛擬環境已啟用）：

   ```bash
   stance-shift serve
   ```

   瀏覽器開 <http://127.0.0.1:8000/>。這個視窗要保持開著，按 Ctrl+C 停止。
5. **填設定**：按「資料準備」頁的「設定模型與金鑰」：
   - 資料來源金鑰：`SEC_USER_AGENT`、`FRED_API_KEY`、`ALPHA_VANTAGE_API_KEY`。
   - 用 GPUtw：在「GPUtw／遠端 Ollama」填 `GPUTW_OLLAMA_BASE_URL` 與 `GPUTW_OLLAMA_API_KEY`。
   - 用本機 Ollama：不用填，預設就是 `ollama/qwen3:14b`。
   - FNSPID 新聞檔：放在 `research-inputs/Stock_news.csv`，並把 `FNSPID_NEWS_PATH` 填成 `research-inputs/Stock_news.csv`。

   按「儲存設定」立即生效，設定存在專案的 `research-data/` 資料夾，下次啟動還在。
6. 接著照下方「[確認模型並開始研究](#確認模型並開始研究)」。

**之後每次**：進專案資料夾 → 啟用虛擬環境 → `stance-shift serve`。**更新程式**：`git pull` 後再執行一次 `pip install .`。**備份**：研究資料全部在 `research-data/`，複製這個資料夾即可。

pip 跑法與 Docker 用的是同一份程式，但 CI 的完整啟動檢查以 Docker 為準；遇到安裝問題，改用跑法二最省事。

### 確認模型並開始研究

兩種跑法打開研究台後都一樣：

1. **確認模型**：看頁面上方的模型狀態。
   - 顯示「雲端模型 · … · 已設定」或「Ollama 已連線」：可以開始。
   - 顯示「模型未連線」或「缺少 … key」：按「資料準備」頁標題下方的「設定模型與金鑰」，在「回測模型」填模型名稱（例如 `gemini/gemini-2.5-flash`、`ollama/qwen3:14b`），在「雲端模型金鑰」或「GPUtw／遠端 Ollama」填金鑰，按「儲存設定」，立即生效、不用重啟。
2. **（選用）加入 FNSPID 新聞**：把已授權、[篩選過](docs/quickstart-v3.md)的 `Stock_news.csv` 放進專案的 `research-inputs/` 資料夾（Codespace 可直接拖進 VS Code 左側檔案樹）。沒有也能只用 Alpha Vantage 新聞。
3. **建立資料集**：「資料準備」頁選股票與研究分析日，按「啟動資料 Agent」。
4. **跑實驗**：「建立實驗」頁選剛建好的資料集，按「開始研究實驗」。
5. **看結果**：「Agent 執行」頁看進度，每個實驗可按「下載研究產物 ZIP」；完成後到「統計結果」比較 A/B/C/D。

**換模型**：隨時在「設定模型與金鑰」改，或重新執行 `setup`。只影響之後新建立的實驗，已建立的實驗不會變。

**常見問題**

- **一直出現 429（被限流）**：雲端 API 每分鐘次數有限，把 `RESEARCH_PARALLEL_WORKERS` 調成 1 或 2。研究台遇到 429 也會自動等待後重試。
- **GPUtw 會一直計費**：研究結束後到 GPUtw 控制台停止執行個體。
- **只想看介面、不接模型**：把 `RESEARCH_DEMO_MODE` 設為 `true` 後重新 `start`。展示模式會放入一筆固定的合成 NVDA 資料集，回應由內建程式產生，不呼叫任何外部服務，也不算正式研究結果；看完改回 `false`。

### 正式研究用的模型

正式協議使用 `ollama/qwen3:14b`（本機 Ollama 或 GPUtw）；OpenRouter 的 `openrouter/qwen/qwen3-14b` 是同一個模型。`ollama/qwen3:8b` 已通過本專案的相容性測試（canary），也可用於正式研究；其他 14B 以下的模型只算測試。改用 Gemini 等其他雲端模型時，需在研究紀錄中註明。

### 進階：終端機指令

網頁負責研究操作與看結果；終端機負責安裝設定、啟停、檢查、日誌與批次工作。Windows 的 `research.ps1` 指令最完整：

```powershell
.\research.ps1 help                      # 全部指令
.\research.ps1 collect NVDA 2024-12-31   # 建立資料集；加 -Refresh 強制重新下載
.\research.ps1 run NVDA 2024-12-31       # 跑實驗
.\research.ps1 jobs
.\research.ps1 logs
```

macOS／Linux 的 `research.sh` 提供 `setup`、`start`、`stop`、`status`、`logs`、`test`、`doctor`。`power-plan`、`model-canary` 等工具在容器內執行，例如
`docker compose -f compose.research.yaml run --rm --no-deps research python -m research_service.cli model-canary`；它們只做設計模擬或合成格式檢查，不會建立正式案例。pip 安裝後也可以直接執行 `stance-shift power-plan`、`stance-shift model-canary`。

## 回測資料

| 研究面向 | 正式來源 | 建立資料集時的處理 |
| --- | --- | --- |
| 技術面 | Yahoo Finance adjusted OHLC | 下載分析日前行情與 30/60/90 日回測需要的未來行情 |
| 基本面 | SEC XBRL | 依 filing date 保存分析日前可得的財報證據 |
| 情緒面 | Alpha Vantage、FNSPID、可選本機 FinBERT | 使用分析日前 90 天的標題／摘要；Alpha Vantage 以目標 ticker 相關性排序並過濾，FNSPID 本機檔只保存必要欄位；FinBERT 對標題離線評分 |
| 總經面 | FRED/ALFRED | 依 vintage date 保存當時可取得的總經資料 |

四個面向的資料在「建立資料集」時一次取得，存進 SQLite 資料庫；之後跑 A/B/C/D 實驗只讀取選定的資料集，不會再呼叫市場資料 API。重跑模型時請重用同一個資料集，比較才公平。資料就緒度分開顯示：四個面向齊全、SEC 基本面可比較、FinBERT／新聞品質、60 日主要回測與 90 日次要回測。正式實驗需要可比較的 SEC 指標、所有新聞標題都完成 FinBERT 評分，且新聞提及目標公司的比例至少 50%；舊版 SEC 基本面或品質不足的新聞，只能在勾選例外後作為敏感性測試。

行情會下載分析日前 900 個日曆日，讓 60 個交易日、互不重疊的基準窗口至少有 8 個。舊版只下載 400 日的資料集仍可查看，但用於目前版本的正式研究前應重新蒐集。版本差異與遷移方式見 [版本紀錄](CHANGELOG.md)。

## 憑證與資料安全

`.\research.ps1 setup` 會隱藏秘密輸入並寫入 Git 忽略的 `.env.research`。網頁只顯示來源是否就緒，不把 API key 寫入瀏覽器儲存空間。公開部署時，憑證屬於伺服器營運者；若未來改成多使用者服務，必須另做使用者身分、加密憑證庫、額度與隔離，不能共用目前的單一研究室設定。

以下內容不會進入 Git 或 Docker 映像：

- `.env.research` 與所有 API key
- `research-inputs/*.csv`、原始 FNSPID 檔
- SQLite 研究資料、工作輸出與本機模型

資料授權仍由部署者負責。不要把 Yahoo、FNSPID 或其他來源的原始資料直接提交到公開儲存庫。

## 專案結構

- `research_service/`：正式 FastAPI 後端、研究流程與網頁工作台
- `research-inputs/`：本機唯讀資料輸入；大型檔案由 Git 忽略
- `scripts/`：FNSPID 整理、CLI 與驗證工具
- `docs/`：研究口徑、操作、部署與審查文件
- `compose.research.yaml`、`Dockerfile.research`：正式執行封裝
- `compose.ollama.yaml`、`compose.ollama-gpu.yaml`：選用，讓 Ollama 以容器一起執行（CPU／NVIDIA GPU）
- `CHANGELOG.md`：各協議版本的行為變更紀錄

更完整的整理原則見 [專案結構](docs/project-layout.md)，目前驗證結果、正式研究缺口與公開發布優先序見 [v3-0912.1 最終審查](docs/final-review-2026-09-12.md)。

**Repo 大小**：git 歷史約 7 MB、追蹤的程式碼約 1.5 MB（`research_service/`、`scripts/`、`docs/`）；`research-inputs/`、下載的行情快照、備份 zip 等大型檔案都被 `.gitignore` 排除，不會進 repo，clone 下來很小。**Docker image 約 2.3 GB**——主要是 PyTorch（CPU 版）＋ transformers，用來跑本機 FinBERT 離線評分；這是刻意的取捨（不需要外部 GPU 或付費 API 就能評分新聞情緒），不是意外堆出來的體積，但 build 時第一次要下載這些套件，網路慢的話會花一點時間。

更細的首次啟動說明見 [Clone 後首次啟動](docs/getting-started.md)。只想驗證回測流程，可照 [本機回測 Demo](docs/demo-backtest.md) 操作；這份流程會固定在歷史資料模式，並說明如何辨認完整資料集 ID、暫停續跑與匯出研究產物。

若要把模型推論移到 GPUtw，請參考 [GPUtw 整合指南](docs/gputw-integration.md)。研究台可讀取 GPUtw 執行個體狀態並使用受保護的遠端 Ollama；部署或停止 GPU 執行個體仍在 GPUtw 控制台手動完成。

## 驗證與部署

```powershell
docker compose -f compose.research.yaml build research
docker compose -f compose.research.yaml run --rm --no-deps -v "${PWD}:/app:ro" research python -m unittest discover -s research_service/tests -p test_*.py
Get-ChildItem research_service\static\js\*.js | ForEach-Object { node --check $_.FullName }
```

### 全新環境可重現性驗證

每次重大變更後，會另外把當時的最新 commit clone 到暫存目錄，模擬「別人第一次拿到這個 repo」的情況，確認流程本身沒有依賴任何本機殘留狀態：

```powershell
git clone https://github.com/paul931130/stance-shift-lab.git <暫存路徑>
cd <暫存路徑>
docker compose -f compose.research.yaml build research
docker compose -f compose.research.yaml run --rm --no-deps -v "${PWD}:/app:ro" research python -m unittest discover -s research_service/tests -p test_*.py
docker run -d --rm -p 127.0.0.1:8020:8000 -e RESEARCH_CONTAINER_LOCAL=true -v <暫存卷>:/data <image>
curl http://127.0.0.1:8020/health   # 應為 {"status":"ok",...}
curl http://127.0.0.1:8020/api/datasets   # 應為空陣列，確認初始狀態乾淨
```

最近一次（`c94c88a`，2026-09-15）結果：103/103 Python 測試通過、10/10 JS 測試通過、全新容器啟動後資料集數為 0、0/180 正式案例（符合全新環境預期）、無 `.env`／API key／原始新聞 CSV outside `.gitignore` 範圍。驗證完成後會刪除暫存 clone、容器、image 與 volume，不留殘留。

公開伺服器需使用 HTTPS 反向代理、至少 32 字元的研究室存取金鑰與持久化備份。GitHub Pages、純 Cloudflare Workers 以及靜態網站無法執行此 Python/Ollama 後端。詳見 [部署指南](docs/deploy-v3.md) 與 [GitHub 發布檢查表](docs/github-release-checklist.md)。

本系統只用於研究與教育，不執行交易。單筆試跑與合成測試不能當成投資績效結論。

## 授權

程式碼採 [MIT License](LICENSE)。Yahoo、SEC、FNSPID、FRED 等第三方資料與 FinBERT 等模型權重各自受其原始授權條款拘束，不在本授權範圍內；使用者需自行確認資料與模型的再散布權限。
