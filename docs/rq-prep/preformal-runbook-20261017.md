# RQ2／RQ3 正式實驗前操作單（2026-10-17）

目前目標是將候選設計、資料與程式準備好，交由真實模型資格與 pilot 驗收後再登記。沒有建立新正式登記或排入正式案例。最新研究報告為 v9；其中 RQ2／RQ3 與分析 family 仍為提案。本操作單與 analysis-plan-20261015.json 是本次選定的執行候選，並非已登記或已完成研究。

## 固定候選設計

| 項目 | 設定 |
|---|---|
| 資料 | 已見的 9 股票 × 20 日期，共 180 案；屬回溯延伸 |
| 模型 | A＝qwen3:32b，B＝gemma3:27b；研究／裁決用 A |
| RQ2 | AA／AB／BA／BB；正式 seeds 905／906／907；報告庫 seed 904 |
| RQ3 | fixed，C／C_domain／C_budget／C_partition；單一 seed 905，單 protocol 分析 |
| 主端點 | candidate、60 日、Corwin–Schultz 成本；RQ2 四端點、RQ3 六端點各自共同 Holm |
| Bootstrap | 日期區塊 2、日報酬區塊 20、1999 次、seed 905；預定敏感性見完整 JSON |
| 記憶與失敗 | 同 seed／ticker／arm、嚴格成熟、按日期順序；正式協議任一案 paused/cancelled 即停止認領該協議後續案 |

三個 RQ2 seed 在案例內平均再推論；RQ3 不套用 RQ2 的跨 seed 合併。不得把三 seed 當三倍市場樣本。正式停止後修復並續跑原 job，不另建工作取代失敗結果；cancelled 案仍會阻擋該協議，須保留並處理，不能跳過。

## 1. 本機環境與離線封裝

專案根目錄執行，Python 需至少 3.12。以下端點只是實驗室 SSH 通道範例；GPUtw 使用實際受保護的 Ollama 端點。Open WebUI 是操作介面，研究程式連的是 Ollama API。

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/check_experiment_environment.py --output work/runtime-new.json
.\.venv\Scripts\python.exe scripts/prepare_experiment_launch.py --source-db work/preformal-20261017/rq1-source-backup.sqlite3 --registration-hash b1da80ee8dbc9c372d9eab02455734a140714a233c2d669bb0177fe9ab267cd6 --plan docs/rq-prep/analysis-plan-20261015.json --output work/launch-new --model-a-base http://127.0.0.1:11435 --model-b-base http://127.0.0.1:11436
```

每次 output 使用新路徑，保留先前紀錄。封裝會驗證原始登記的完整 180 案、內容 digest、資料 coverage，輸出完整計畫、frame、報告庫／pilot／RQ3 案例、RQ3 runtime 與 SHA256 manifest。這些操作不聯網、不建立工作或登記。`formal_launch_ready=false` 是預期狀態。

## 2. 接真實模型前先排除環境問題

GPUtw 上次失敗是 Qwen canary 的 HTTP 524，後續呼叫未執行，不能算模型不會完成研究任務。重測先在 Ollama 所在主機完成模型載入並確認請求可完成，再跑外部 API；若反向代理不容許長請求，將研究 runner 放在同主機，或使用經驗證的通道。不可持續重試相同冷載入路徑。

GPUtw 官方範本內觀察到的 Open WebUI Python 3.11 不符合本專案要求；另建 Python 3.12 以上環境並安裝專案依賴，再執行 environment check。保存實際 image digest、Ollama 版本、兩模型完整 digest／量化格式、context=8192、parallel=1、timeout、硬體與套件版本。相同 tag 不代表相同權重。

GPUtw 與實驗室都要核對模型 inventory、兩模型的基礎 canary 與 recall/identify 探針；指令與樣本範圍見 experiment-launch-20261015.md 第 2 節。這些通過後仍須完整設計 pilot，不能用舊同質 canary 取代。憑證只放環境或本機設定，不加入案例或 manifest。

## 3. 固定最早日期三案 pilot

先跑離線兩種設計，確認整合成功；實機時改新 output 並加 `--execute`。

```powershell
$runtime = Get-Content work/launch-new/rq3-runtime.json -Raw | ConvertFrom-Json
$env:OLLAMA_BASE_URL = $runtime.required_environment.OLLAMA_BASE_URL
$env:GPUTW_OLLAMA_BASE_URL = $runtime.required_environment.GPUTW_OLLAMA_BASE_URL
.\.venv\Scripts\python.exe scripts/run_design_pilot.py --source-db work/preformal-20261017/rq1-source-backup.sqlite3 --cases work/launch-new/rq2-pilot.cases.json --output work/rq2-pilot-new --mode pilot
.\.venv\Scripts\python.exe scripts/run_design_pilot.py --source-db work/preformal-20261017/rq1-source-backup.sqlite3 --cases work/launch-new/rq3-pilot.cases.json --output work/rq3-pilot-new --mode pilot
```

RQ2 端點由案例的路由設定指定；RQ3 必須套用 rq3-runtime.json 的 A 環境設定，案例不可帶 RQ2 的 model_endpoints 欄位。若服務已有持久化模型設定，核對其未覆蓋本次端點。實際模型 digest 由 preflight 與逐步檢查核對。

實機驗收逐項記錄：所有 arms 完整、原始回應可追溯、無引用／schema／namespace／模型降級；28 提案整合提示未截斷；每次 tokens、重試與延遲齊備；pause/resume 不換 digest／程式；無未完成早案造成記憶缺漏。pilot 的 complete 只表示程式完成，不自動通過以上資格。不得依 accuracy／Sharpe 挑設定。pilot 失敗留存輸出；修碼後重做受影響資格，不能以舊 source manifest 續認。

## 4. 報告庫與正式案例綁定

實機 pilot 通過且程式凍結後，才用 launch-new/report-bank.cases.json、`--mode report-bank --execute` 建立 180 案報告庫。其輸出 data/ 是正式 RQ2 服務必須沿用的資料庫，來源工作保持 neutral_report_locked、paused、無 owner／wants_run／決策／回測。禁止對報告庫工作按整批 resume。

```powershell
# 僅在前述真實資格與 pilot 通過後執行；會呼叫模型
.\.venv\Scripts\python.exe scripts/run_design_pilot.py --source-db work/preformal-20261017/rq1-source-backup.sqlite3 --cases work/launch-new/report-bank.cases.json --output work/report-bank-new --mode report-bank --execute
```

在沒有其他 writer 的情況下，用 SQLite backup 建立報告庫 standalone 快照（或服務的 `/api/backup` ZIP 內 research.sqlite3）；不要直接複製活動 WAL 主檔。接著離線綁定：

```powershell
.\.venv\Scripts\python.exe scripts/bind_rq2_launch.py --launch-dir work/launch-new --bank-db work/bank-backup.sqlite3 --output work/rq2-bound-new
```

工具核對來源、逐案鎖定狀態與報告 hash，產生三份 rq2-formal.seed-*.cases.json，仍不建立登記／工作。bank job IDs 僅能在含同一報告庫的 Store 使用。不要將報告快照獨自另建空服務後直接引用 IDs。更動程式、分析計畫或執行設定時，重新產生封裝與受影響資格，不修改既有 manifest。

## 5. 正式啟動前最後停點

只有下列證據全部備齊才能正式登記：

- 本輪完整單元／整合／瀏覽器測試通過；執行主機 environment check 通過。
- A/B 權重與 runtime/image、原始 frame、程式與所有執行／分析腳本 hashes 凍結。
- 基礎 canary、記憶探針、RQ2／RQ3 三案完整設計 pilot 的原始輸出與具名驗收完成。
- RQ2 的 180 案鎖定報告庫及三 seed 正式批次核對完成；RQ3 單 seed 180 案／兩控制組核對完成。
- 分析計畫狀態、family、區塊與敏感性、失敗／成本缺失／記憶邊界確認並隨登記封存。

下一階段啟動服務時，RESEARCH_DEMO_MODE=false、RESEARCH_DATA_DIR 指向上述 bank/data；一次只開一個服務程序。先對批次每案呼叫 POST /api/jobs/preflight（不建立 job），確認 ready 與 formal_readiness，再 POST /api/studies/preregister。保存回傳的完整 protocol hash；RQ2 三個 hash 必須各異。登記後才 POST /api/studies/{hash}/enqueue。先 RQ2，再切換確認 A runtime 後處理 RQ3。這份操作單本身不執行以上寫入。

```powershell
$env:RESEARCH_DEMO_MODE = 'false'
$env:RESEARCH_DATA_DIR = (Resolve-Path work/report-bank-new/data).Path
.\.venv\Scripts\python.exe -m research_service.cli serve --host 127.0.0.1 --port 8000
```

逐案預檢可使用下面的 PowerShell；它只探測模型與準備配置，不呼叫生成、不建立工作。apiBase 是研究服務，不是 Ollama。若服務設有 access key，從環境讀取作為 Bearer，勿把金鑰寫進指令或輸出。任一案例失敗立即停止；輸出不是完整模型資格證明。

```powershell
$apiBase = 'http://127.0.0.1:8000'
$headers = @{}
if ($env:RESEARCH_ACCESS_KEY) { $headers.Authorization = 'Bearer ' + $env:RESEARCH_ACCESS_KEY }
$batch = Get-Content work/rq2-bound-new/rq2-formal.seed-905.cases.json -Raw | ConvertFrom-Json
$checks = foreach ($case in $batch.cases) {
    $body = $case | ConvertTo-Json -Depth 30
    $check = Invoke-RestMethod -Method Post -Uri "$apiBase/api/jobs/preflight" -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
    if (-not $check.ready -or -not $check.formal_readiness.eligible) { throw "Preflight stopped: $($case.dataset_id)" }
    [PSCustomObject]@{ dataset_id=$case.dataset_id; analysis_date=$case.analysis_date; ready=$true }
}
$checks | ConvertTo-Json -Depth 5 | Set-Content work/preflight-905-new.json -Encoding utf8
```

某案暫停時正式協議不再認領後案；不要用 clone 或新 job 繞過。完成後 SQLite backup，再跑 analyze_rq2_snapshot.py（三 protocol hashes）或 analyze_rq3_snapshot.py（單 hash），固定 date-block-length=2、daily-block-length=20。保留完整共同 180 案、失敗與不可估計端點，不能縮小 family 或以部分結果挑結論。

RQ2 名義決策呼叫 34,560；RQ3 14,580；研究層、重試與輸入庫另計。費用與時間由真實 pilot 實測估計，不能沿用舊 GPU 報價或把名義呼叫數當 token 匹配。
