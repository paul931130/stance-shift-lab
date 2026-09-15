# Stance Shift Research v3

[![CI](https://github.com/paul931130/stance-shift-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/paul931130/stance-shift-lab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

可實際執行的多代理人立場交換回測研究台。正式入口是 Docker 化的 FastAPI 服務：四個資料 Agent 建立具時間邊界的不可變資料快照，A/B/C/D 使用同一份快照比較單次判斷、獨立投票、固定立場辯論與立場交換辯論。

## 快速開始

需求：Windows 10/11、Docker Desktop，以及 Ollama 或一組雲端模型金鑰。

```powershell
.\research.ps1 setup
.\research.ps1 start
```

開啟 <http://127.0.0.1:8000/>。也可直接雙擊 `start-research.cmd`。

網頁負責互動式研究操作與結果檢視；終端負責安裝設定、啟停、檢查、日誌與批次工作：

```powershell
.\research.ps1 doctor
.\research.ps1 collect NVDA 2024-12-31
.\research.ps1 run NVDA 2024-12-31
.\research.ps1 jobs
.\research.ps1 logs
```

研究執行預設使用 `ollama/qwen3:14b`。若只想用較小模型驗證流程，需明確加上 `-Model ollama/qwen3:8b -AllowSmallModel`；這類結果只算冒煙測試，不納入正式研究比較。

執行 `.\research.ps1 help` 可查看完整命令。`start` 會先檢查 Docker Linux engine，未啟動時嘗試開啟 Docker Desktop 並給出可操作的錯誤訊息。`collect` 會重用同股票、同分析日且四域完整的既有快照；加上 `-Refresh` 才會重新呼叫資料來源。

## 回測資料

| 研究域 | 正式來源 | 建立快照時的處理 |
| --- | --- | --- |
| 技術面 | Yahoo Finance adjusted OHLC | 下載分析日前行情與 30/60/90 日回測需要的未來行情 |
| 基本面 | SEC XBRL | 依 filing date 保存分析日前可得的財報證據 |
| 情緒面 | Alpha Vantage、FNSPID、可選本機 FinBERT | 使用分析日前 90 天的標題／摘要；Alpha Vantage 以目標 ticker 相關性排序並過濾，FNSPID 本機檔只保存必要欄位；FinBERT 對標題離線評分 |
| 總經面 | FRED/ALFRED | 依 vintage date 保存當時可取得的總經資料 |

四域資料在「建立資料集」時取得並寫入持久化 SQLite；執行 A/B/C/D 模型實驗時只讀選定的 dataset ID，不會再次呼叫市場資料 API。重跑模型時應重用同一資料集，才能維持公平比較。`v3-0912.1` 另外分開顯示四域完整、可比較 SEC 基本面、FinBERT／新聞品質、60 日主要回測及 90 日次要回測。正式主實驗需使用可比較 SEC 指標、所有新聞標題完成固定版本 FinBERT，且目標公司提及率至少 50%；舊點時基本面或低品質新聞只能以明確覆寫執行敏感性測試。

自動行情快照會下載分析日前 900 個日曆日，讓 60-session 非重疊基準能達到至少八窗。舊版 400 日快照仍可查看，但應重新採集後再用於目前版本的正式研究。版本差異與遷移方式見 [版本紀錄](CHANGELOG.md)。

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

## 驗證與部署

```powershell
docker compose -f compose.research.yaml build research
docker compose -f compose.research.yaml run --rm --no-deps research python -m unittest discover -s research_service/tests -p test_*.py
node --check research_service\static\app.js
node --test research_service\tests_js\*.test.js
```

### 全新環境可重現性驗證

每次重大變更後，會另外把當時的最新 commit clone 到暫存目錄，模擬「別人第一次拿到這個 repo」的情況，確認流程本身沒有依賴任何本機殘留狀態：

```powershell
git clone https://github.com/paul931130/stance-shift-lab.git <暫存路徑>
cd <暫存路徑>
docker compose -f compose.research.yaml build research
docker compose -f compose.research.yaml run --rm --no-deps research python -m unittest discover -s research_service/tests -p test_*.py
docker run -d --rm -p 127.0.0.1:8020:8000 -e RESEARCH_CONTAINER_LOCAL=true -v <暫存卷>:/data <image>
curl http://127.0.0.1:8020/health   # 應為 {"status":"ok",...}
curl http://127.0.0.1:8020/api/datasets   # 應為空陣列，確認初始狀態乾淨
```

最近一次（`c94c88a`，2026-09-15）結果：103/103 Python 測試通過、10/10 JS 測試通過、全新容器啟動後資料集數為 0、0/180 正式案例（符合全新環境預期）、無 `.env`／API key／原始新聞 CSV outside `.gitignore` 範圍。驗證完成後會刪除暫存 clone、容器、image 與 volume，不留殘留。

公開伺服器需使用 HTTPS 反向代理、至少 32 字元的研究室存取金鑰與持久化備份。GitHub Pages、純 Cloudflare Workers 以及靜態網站無法執行此 Python/Ollama 後端。詳見 [部署指南](docs/deploy-v3.md) 與 [GitHub 發布檢查表](docs/github-release-checklist.md)。

本系統只用於研究與教育，不執行交易。單筆試跑與合成測試不能當成投資績效結論。

## 授權

程式碼採 [MIT License](LICENSE)。Yahoo、SEC、FNSPID、FRED 等第三方資料與 FinBERT 等模型權重各自受其原始授權條款拘束，不在本授權範圍內；使用者需自行確認資料與模型的再散布權限。
