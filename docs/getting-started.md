# 從 GitHub Clone 後首次啟動

## 取得原始碼

```bash
git clone https://github.com/<你的帳號>/stance-shift-lab.git
cd stance-shift-lab
```

Repo 只包含原始碼、腳本與文件；不含 API key、SQLite 資料、原始新聞 CSV 或本機模型。這些都要在自己的電腦上另外準備。

## 第一次啟動

1. 在 Windows 安裝並啟動 Docker Desktop；若用本機模型，再安裝 [Ollama](https://ollama.com/)。
2. 在專案根目錄執行：

```powershell
.\research.ps1 setup
.\research.ps1 doctor
.\research.ps1 start
```

`setup` 會建立 `.env.research` 並引導輸入自己的 API key；`doctor` 檢查 Docker、模型與資料來源是否就緒；`start` 建置並啟動容器。

3. 若要使用 FNSPID 新聞資料，將已授權的篩選檔放到 `research-inputs\Stock_news.csv`。沒有此檔仍可只用 Alpha Vantage；系統會明確顯示缺少哪個來源。
4. 開啟 <http://127.0.0.1:8000/>，確認健康版本是目前的協議版本。
5. 正式 pilot 需先安裝 14B 以上模型，例如：

```powershell
ollama pull qwen3:14b
.\research.ps1 models
```

6. 建立資料並開始單案驗收：

```powershell
.\research.ps1 collect NVDA 2024-12-31 -Refresh -UseFinbert
.\research.ps1 readiness
.\research.ps1 datasets
```

只有 `formal_experiment_ready=true` 的資料集可進主實驗。完整操作見 [本機回測 Demo](demo-backtest.md)。

## 驗證原始碼

```powershell
docker compose -f compose.research.yaml build research
docker compose -f compose.research.yaml run --rm --no-deps research `
  python -m unittest discover -s research_service/tests -p test_*.py -v
node --check research_service\static\app.js
node --test research_service\tests_js\*.test.js
```

## 資料與研究延續

正式研究的下一步依序是：

1. 建立 9 檔 × 20 季，共 180 個正式就緒資料集。
2. 用 14B 以上模型先跑 3 檔 × 4 季 pilot，檢查 Hold 率、D 對 A 分歧率、B 投票一致度和帶外方向準確率。
3. 通過停止規則後凍結 preregistration、study manifest、dataset ID、protocol hash、模型 digest 與原始碼 commit。
4. 再執行正式批次；不得把舊協議、小模型、資料品質覆寫或 degraded 摘要併入主分析。

## 維運與故障處理

- 升級前執行 `.\research.ps1 backup`；不要執行 `docker compose down -v`。
- Docker Desktop 若出現 `sailor-ingest.sock.stale`，先由 Docker Desktop 的 Troubleshoot 重啟，仍失敗再重新開機。Factory reset 會清除本機容器與資料卷，不應作為第一步。
- 模型或資料 API 失敗會讓工作停在可重試狀態；確認來源後執行 `resume`，不要把錯誤當成 NoTrade。
- 對外部署（讓其他人透過網域存取，而非只在自己電腦跑）前依 [GitHub 發布檢查表](github-release-checklist.md) 建立乾淨 Git 歷史、選定 LICENSE、加 CI，再配置 HTTPS、強存取金鑰與持久化備份。
