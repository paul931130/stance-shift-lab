# Stance Shift Research v3

[![CI](https://github.com/paul931130/stance-shift-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/paul931130/stance-shift-lab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

可實際執行的多代理人立場交換回測研究台。正式入口是 Docker 化的 FastAPI 服務：四個資料 Agent 建立具時間邊界的不可變資料快照，A/B/C/D 使用同一份快照比較單次判斷、獨立投票、固定立場辯論與立場交換辯論。

## 快速開始

### 不用安裝：直接在 GitHub 開（Codespaces）

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/paul931130/stance-shift-lab)

按上面的按鈕（或 repo 頁面的 Code → Codespaces → Create），GitHub 會開一台雲端機器、用同一個 Docker 映像啟動研究台，並自動在瀏覽器開啟 `https://<codespace 名稱>-8000.app.github.dev`。第一次建立要下載約 2 GB 套件，需等幾分鐘；之後重新開啟會快很多。

- **金鑰**：到 GitHub → Settings → Codespaces → Secrets 新增，名稱與 `research.env.example` 相同（例如 `GPUTW_OLLAMA_BASE_URL`、`GPUTW_OLLAMA_API_KEY`、`FRED_API_KEY`），並授權給這個 repo；每次啟動會自動寫入 `.env.research`。也可以開啟後在網頁設定區填寫。
- **模型**：Codespace 沒有 GPU，請接自己的 GPUtw 遠端 Ollama 或雲端模型 API 金鑰（需要哪些 secrets 見 [選擇模型來源](docs/model-sources.md)）。只想看介面，新增 secret `RESEARCH_DEMO_MODE=true`。
- **存取**：8000 連接埠預設為私人，只有開 Codespace 的 GitHub 帳號登入後看得到；不要改成公開。
- **費用與資料**：使用的是各自 GitHub 帳號的 Codespaces 額度。閒置會自動停機、資料保留；刪除 Codespace 時資料一併刪除，研究結果請先匯出。

### 在自己電腦上用 Docker 執行

**唯一支援的執行方式是 Docker**，Windows、macOS（Intel／Apple Silicon）、Linux 都用同一個映像。需求只有 Docker Desktop（Linux 可用 Docker Engine + Compose plugin），以及一個模型來源：自己電腦的 Ollama、雲端租 GPU（GPUtw），或雲端模型 API 金鑰，`setup` 會讓你三選一，比較見 [選擇模型來源](docs/model-sources.md)；只想看介面可用下方展示模式，什麼都不用準備。電腦上不需要安裝 Python。

Windows（PowerShell）：

```powershell
.\research.ps1 setup
.\research.ps1 start
```

macOS／Linux：

```bash
./research.sh setup
./research.sh start
```

開啟 <http://127.0.0.1:8000/>。Windows 也可直接雙擊 `start-research.cmd`。CI 會在每次推送時於 x86-64 與 ARM64 兩種架構實際啟動這個 Docker 服務並驗證可用。

若只要展示介面與完整工作流、不使用 API key 或模型，可在 `.env.research` 暫時設定
`RESEARCH_DEMO_MODE=true` 後啟動服務。展示模式會自動放入一筆固定的合成 NVDA
資料集，所有回應都由內建確定性 provider 產生；它不會呼叫外部服務，也不算正式研究結果。
展示完畢後改回 `false`，避免把合成案例誤當成正式資料。

網頁負責互動式研究操作與結果檢視；終端負責安裝設定、啟停、檢查、日誌與批次工作：

```powershell
.\research.ps1 doctor
.\research.ps1 collect NVDA 2024-12-31
.\research.ps1 run NVDA 2024-12-31
.\research.ps1 jobs
.\research.ps1 logs
```

研究預設使用 `ollama/qwen3:14b`；也可以改用 GPUtw 或雲端模型 API，見 [選擇模型來源](docs/model-sources.md)。`ollama/qwen3:8b` 已通過本專案的相容性測試（canary），可用於正式研究；其他 14B 以下的模型需加上 `-AllowSmallModel`，只算測試。

`power-plan`、`model-canary` 等 CLI 工具同樣在容器內執行，例如
`docker compose -f compose.research.yaml run --rm --no-deps research python -m research_service.cli model-canary`；
它們只做設計模擬或合成格式檢查，不會建立正式案例。不走 Docker 的本機 Python 安裝只供開發者使用，不在支援範圍。

執行 `.\research.ps1 help` 可查看完整命令。`start` 會先檢查 Docker Linux engine，未啟動時嘗試開啟 Docker Desktop 並給出可操作的錯誤訊息。`collect` 會重用同股票、同分析日且四域完整的既有快照；加上 `-Refresh` 才會重新呼叫資料來源。

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
- `CHANGELOG.md`：各協議版本的行為變更紀錄

更完整的整理原則見 [專案結構](docs/project-layout.md)，目前驗證結果、正式研究缺口與公開發布優先序見 [v3-0912.1 最終審查](docs/final-review-2026-09-12.md)。

**Repo 大小**：git 歷史約 7 MB、追蹤的程式碼約 1.5 MB（`research_service/`、`scripts/`、`docs/`）；`research-inputs/`、下載的行情快照、備份 zip 等大型檔案都被 `.gitignore` 排除，不會進 repo，clone 下來很小。**Docker image 約 2.3 GB**——主要是 PyTorch（CPU 版）＋ transformers，用來跑本機 FinBERT 離線評分；這是刻意的取捨（不需要外部 GPU 或付費 API 就能評分新聞情緒），不是意外堆出來的體積，但 build 時第一次要下載這些套件，網路慢的話會花一點時間。

第一次 clone 這個 repo，先照 [Clone 後首次啟動](docs/getting-started.md) 走一遍。只想驗證回測流程，可照 [本機回測 Demo](docs/demo-backtest.md) 操作；這份流程會固定在歷史資料模式，並說明如何辨認完整資料集 ID、暫停續跑與匯出研究產物。

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
