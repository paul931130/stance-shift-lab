# 從 GitHub Clone 後首次啟動

## 取得原始碼

```bash
git clone https://github.com/<你的帳號>/stance-shift-lab.git
cd stance-shift-lab
```

Repo 只包含原始碼、腳本與文件；不含 API key、SQLite 資料、原始新聞 CSV 或本機模型。這些都要在自己的電腦上另外準備。

## 第一次啟動

建議用 Docker 執行，所有作業系統跑的是同一個 Linux 映像，電腦上不需要安裝 Python。已經有 Python 3.12 以上、只接 GPUtw 或本機 Ollama 的人，也可以不用 Docker、直接 `pip install .` 後執行 `stance-shift serve`，步驟見 README 的「跑法三」。

1. 安裝並啟動 Docker：Windows／macOS 用 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（Apple Silicon 也支援）；Linux 用 Docker Engine 加 Compose plugin。
2. 準備模型，三選一：本機 [Ollama](https://ollama.com/)、自己的 GPUtw 遠端 Ollama（見 [GPUtw 整合指南](gputw-integration.md)），或雲端模型金鑰。只想看介面可先跳過，改用展示模式（`.env.research` 設 `RESEARCH_DEMO_MODE=true`）。
3. 在專案根目錄執行：

Windows（PowerShell）：

```powershell
.\research.ps1 setup
.\research.ps1 doctor
.\research.ps1 start
```

macOS／Linux：

```bash
./research.sh setup
./research.sh doctor
./research.sh start
```

Windows 的 `setup` 會互動式引導輸入 API key；macOS／Linux 的 `setup` 會從範本建立 `.env.research`，金鑰可用文字編輯器填入，或啟動後在網頁設定區填寫。`doctor` 檢查 Docker 與模型連線；`start` 建置並啟動容器。第一次建置要下載約 2 GB 的套件，需要一些時間。

Linux 使用本機 Ollama 時，Ollama 預設只聽 `127.0.0.1`，容器連不到；請以 `OLLAMA_HOST=0.0.0.0` 啟動 Ollama（systemd 服務可用 `sudo systemctl edit ollama` 加上 `Environment="OLLAMA_HOST=0.0.0.0"`），並確認防火牆不對外開放 11434。Windows／macOS 的 Docker Desktop 不需要這一步。

4. 若要使用 FNSPID 新聞資料，將已授權的篩選檔放到 `research-inputs\Stock_news.csv`。沒有此檔仍可只用 Alpha Vantage；系統會明確顯示缺少哪個來源。
5. 開啟 <http://127.0.0.1:8000/>，確認健康版本是目前的協議版本。
6. 正式研究建議使用 14B 以上的模型，例如 `qwen3:14b`；`qwen3:8b` 已通過本專案的相容性測試（canary），是唯一可用於正式研究的小模型。也可以改用 GPUtw 或雲端模型 API，見 [選擇模型來源](model-sources.md)：

```powershell
ollama pull qwen3:14b
.\research.ps1 models
```

7. 建立資料並開始單案驗收：

```powershell
.\research.ps1 collect NVDA 2024-12-31 -Refresh -UseFinbert
.\research.ps1 readiness
.\research.ps1 datasets
```

只有 `formal_experiment_ready=true` 的資料集可進主實驗。完整操作見 [本機回測 Demo](demo-backtest.md)。

## 哪些設定可以在網頁完成，哪些要在本機做

**可以在網頁完成**：開啟 <http://127.0.0.1:8000/>，在「01/資料」面板展開「設定資料來源與模型」，可直接填入並儲存：

- `SEC_USER_AGENT`、`FRED_API_KEY`、`ALPHA_VANTAGE_API_KEY`
- `OPENROUTER_API_KEY`、`OPENAI_API_KEY`、`GEMINI_API_KEY`（雲端模型）
- `RESEARCH_MODEL`（預設模型名稱）、`FNSPID_NEWS_PATH`（容器內路徑字串）

按「儲存設定」會呼叫 `/api/settings`，寫進伺服器端的 `research-data/private/settings.json`，立即生效、不需要重啟服務或編輯 `.env.research`。金鑰輸入框會遮住內容，介面只顯示「已設定／未設定」，不會把已存的值送回瀏覽器。

**不能在網頁完成，需要在使用者自己電腦上做**：

- **安裝 Ollama、下載模型**——瀏覽器沒有權限在使用者電腦裝軟體或拉幾 GB 的模型檔，仍要照上面步驟 5 手動 `ollama pull`。裝好後網頁的模型下拉選單會自動偵測到。
- **放置 FNSPID 原始 CSV**——`FNSPID_NEWS_PATH` 欄位填的是容器內路徑字串，不是上傳按鈕；實際檔案（通常上百 MB、有再散布限制）要照步驟 3 手動放進 `research-inputs/`，再跑 `scripts/prepare_fnspid_news.py` 篩選。只用 Alpha Vantage 的話可以完全跳過這步。

## 驗證原始碼

```powershell
docker compose -f compose.research.yaml build research
docker compose -f compose.research.yaml run --rm --no-deps -v "${PWD}:/app:ro" research `
  python -m unittest discover -s research_service/tests -p test_*.py -v
Get-ChildItem research_service\static\js\*.js | ForEach-Object { node --check $_.FullName }
```

macOS／Linux 用 `./research.sh test` 在容器內執行同一套單元測試。

## 資料與研究延續

正式研究的下一步依序是：

1. 建立 9 檔 × 20 季，共 180 個正式就緒資料集。
2. 先用 3 檔 × 4 季做試跑（pilot），在統計頁的「試跑檢查」確認 Hold 比例、D 與 A 的決策差異、B 組投票一致度，以及明確看多／看空時的準確率都正常。
3. 試跑通過後，在統計頁按「鎖定目前的研究樣本」（事前登記），並記下資料集清單、協議版本、模型版本與程式碼 commit，之後才開始看正式結果。
4. 再執行正式批次；不得把舊協議、小模型、資料品質覆寫或 degraded 摘要併入主分析。

## 維運與故障處理

- 升級前執行 `.\research.ps1 backup`（備份存到 `backups\`）；不要執行 `docker compose down -v`。
- Docker Desktop 若出現 `sailor-ingest.sock.stale`，先由 Docker Desktop 的 Troubleshoot 重啟，仍失敗再重新開機。Factory reset 會清除本機容器與資料卷，不應作為第一步。
- 模型或資料 API 失敗會讓工作停在可重試狀態；確認來源後執行 `resume`，不要把錯誤當成 NoTrade。
- 對外部署（讓其他人透過網域存取，而非只在自己電腦跑）前依 [GitHub 發布檢查表](github-release-checklist.md) 建立乾淨 Git 歷史、選定 LICENSE、加 CI，再配置 HTTPS、強存取金鑰與持久化備份。
