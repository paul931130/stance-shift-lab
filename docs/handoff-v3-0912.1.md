# v3-0912.1 交接清單

## 交付範圍

本次提供兩種壓縮包：

- `stance-shift-backtest-v3-0912.1.zip`：精簡程式包，適合只交接程式或整理成公開 release。
- `stance-shift-lab-full-handoff-v3-0912.1.zip`：私人完整資料夾包，包含原始碼、Git metadata、相依套件、本機快取、原始與篩選新聞資料、研究產物，以及最新版 Docker 資料庫備份。

兩種包都不包含券商下單。完整資料夾包只排除 `.env.research`，因為它含現用 API key；接手者須執行 `.\research.ps1 setup` 設定自己的憑證。Ollama 模型存在使用者層級，不在專案資料夾內，因此仍需在接手電腦另外安裝。

完整資料夾包含可能受再散布條款限制的資料與研究輸出，只能作私人交接，不應直接上傳公開 GitHub。

## 接手後第一次啟動

1. 在 Windows 安裝並啟動 Docker Desktop；若用本機模型，再安裝 Ollama。
2. 解壓縮後，在專案根目錄執行：

```powershell
.\research.ps1 setup
.\research.ps1 doctor
.\research.ps1 start
```

3. 將已授權的 FNSPID 篩選檔放到 `research-inputs\Stock_news.csv`。沒有此檔仍可使用 Alpha Vantage；系統會明確顯示缺少哪個來源。
4. 開啟 <http://127.0.0.1:8000/>，確認健康版本是 `v3-0912.1`。
5. 正式 pilot 先安裝 14B 以上模型，例如：

```powershell
ollama pull qwen3:14b
.\research.ps1 models
```

6. 建立新版資料並開始單案驗收：

```powershell
.\research.ps1 collect NVDA 2024-12-31 -Refresh -UseFinbert
.\research.ps1 readiness
.\research.ps1 datasets
```

只有 `formal_experiment_ready=true` 的資料集可進主實驗。完整操作見 [本機回測 Demo](demo-backtest.md)。

## 驗證交付檔

交付訊息會提供整個 ZIP 的 SHA-256：

```powershell
Get-FileHash .\stance-shift-backtest-v3-0912.1.zip -Algorithm SHA256
```

解壓後的 `PACKAGE_MANIFEST.json` 另外保存每個檔案的大小與 SHA-256；封裝腳本在產生 ZIP 後會逐一重算並驗證。

接手人可重跑：

```powershell
docker compose -f compose.research.yaml build research
docker compose -f compose.research.yaml run --rm --no-deps research `
  python -m unittest discover -s research_service/tests -p test_*.py -v
node --check research_service\static\app.js
```

## 目前已驗證狀態

2026-09-12 的本機驗收結果：

- 服務健康，Web 與 CLI 均回報 `v3-0912.1`。
- Python 79/79、舊展示層 Node 18/18、ESLint、靜態 JavaScript 語法與 Docker 建置通過。
- NVDA 2024-12-31 新快照 ID：`75cc717ffbef74701ef0cee99cf9c44aba42ed35aa22562107afa97fad2fc61c`。
- 該快照有 619 個分析日前交易日、149 個未來交易日、4/4 筆可比較 SEC 指標、50/50 筆合法 FinBERT 分數，且沒有分析日當天或未來證據。
- 資料庫目前有 1/180 個正式就緒案例；這足以做 demo，不能形成論文結論。
- 本機最大模型是 12.2B，尚無符合正式門檻的 14B 模型；小模型結果只算冒煙測試。
- 既有 NVDA 8B 冒煙工作產生 A=Hold、B=Sell、C=Hold、D=Hold，可確認系統沒有把四組硬編碼成 Hold；這不代表 prompt 已通過正式 pilot。
- Finnhub 未設定且不在本次歷史回測交付範圍。

## 資料與研究延續

正式研究的下一步依序是：

1. 建立 9 檔 × 20 季，共 180 個正式就緒資料集。
2. 用 14B 以上模型先跑 3 檔 × 4 季 pilot，檢查 Hold 率、D 對 A 分歧率、B 投票一致度和帶外方向準確率。
3. 通過停止規則後凍結 preregistration、study manifest、dataset ID、protocol hash、模型 digest 與原始碼 commit。
4. 再執行正式批次；不得把舊協議、小模型、資料品質覆寫或 degraded 摘要併入主分析。

## 維運與故障處理

- 升級或交接前執行 `.\research.ps1 backup`；不要執行 `docker compose down -v`。
- Docker Desktop 若出現 `sailor-ingest.sock.stale`，先由 Docker Desktop 的 Troubleshoot 重啟，仍失敗再重新開機。Factory reset 會清除本機容器與資料卷，不應作為第一步。
- 模型或資料 API 失敗會讓工作停在可重試狀態；確認來源後執行 `resume`，不要把錯誤當成 NoTrade。
- 對外部署前依 [GitHub 發布檢查表](github-release-checklist.md) 建立乾淨 Git 歷史、選定 LICENSE、加 CI，再配置 HTTPS、強存取金鑰與持久化備份。
