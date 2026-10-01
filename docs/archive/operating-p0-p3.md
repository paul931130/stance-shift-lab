# P0--P3 操作與交接

本系統是單一使用者的本機歷史回測研究工具，不會連接券商或下單。資料集、模型設定、提示詞版本與實驗結果都會留在本機資料庫。

## 先啟動與復原

```powershell
.\research.ps1 start
.\research.ps1 doctor
```

啟動腳本會偵測 Docker Desktop 的舊 `sailor-ingest.sock`，嘗試安全復原一次後再啟動。Docker 仍無法啟動時，先執行：

```powershell
.\research.ps1 repair-docker
```

Docker 不可用但已安裝 Python 3.12+ 時，可用獨立的本機備援服務：

```powershell
.\scripts\start-native.ps1 -Bootstrap
```

首次會建立 `.native-venv` 並安裝需求。備援使用 `research-data-native`，不會改寫 Docker 服務的資料庫。

## P0：查看與補齊資料缺口

網頁「研究就緒度」會列出每個未達正式主實驗條件的 ticker／日期、缺少的研究域或品質條件，以及可直接複製的蒐集指令。終端可使用：

```powershell
.\research.ps1 gaps
.\research.ps1 collect AAPL 2023-09-30 -UseFinbert
.\scripts\collect-quarters.ps1 -DailyBudget 10 -UseFinbert
```

缺口清單把「四域證據」、「FinBERT 與新聞相關性」、「60 日後續行情」分開列出。重新蒐集建立不可變的新資料集版本；既有實驗不會被混入新版資料。

免費 Alpha Vantage 的日／分鐘額度是外部限制。下載工作碰到限流會安全停止並保留 checkpoint；隔日用同一指令續跑。它不能取代 SEC、FRED、價格歷史或 FinBERT 的資料需求。

## P1：正式 pilot

```powershell
.\scripts\create-pilot-plan.ps1 -Cases 12 -Model ollama/qwen3:14b
```

產生的 `work\formal-pilot-plan.json` 可在網頁「批次研究」匯入。先檢查 action 分布、有效引用率、模型失敗率與每案例執行時間，再擴大到完整批次。

## P2：模型與資料操作一致性

網頁與 `research.ps1` 讀取同一個 Docker 服務，因此資料集、實驗工作、匯出與就緒度會一致。模型名稱以 Ollama 已安裝模型的完整名稱填寫，例如 `ollama/qwen3:14b`。金鑰留在伺服器端 `.env.research`，不要提交到 Git。

## P3：備份與交接封裝

```powershell
.\research.ps1 backup
.\scripts\create_release_package.ps1 -Version v3-0914.1
```

封裝含程式、測試、文件、啟動與資料蒐集腳本，以及 SHA-256 manifest；刻意不含 API 金鑰、SQLite 資料庫、原始新聞 CSV 與本機 Ollama 模型。

## 完整實驗的界線

180 個研究案例尚未因為加入此操作層而自動完成。只有就緒度標示 `formal_experiment_ready` 的資料集可進入正式主實驗；其餘可作 demo、除錯或對照，但不能當成完整論文結論。
