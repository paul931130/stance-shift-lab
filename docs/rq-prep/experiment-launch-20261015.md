# 實驗推進手冊（2026-10-15；10-17 更新）

目前啟動與驗收入口改為 [正式實驗前操作單](preformal-runbook-20261017.md)；本頁保留方法說明。

這份手冊是目前的操作入口。10 月 8 日草稿保留歷史用途；不可直接複製其單 seed、optional BB、V=0 或舊費用預估。最新報告為 report/application-meeting-20261015_v9.tex／PDF；以下新分析 family 是待登記提案，尚未變更任何正式登記。

## 目前可做與尚不可宣稱

可以在隔離副本準備新版 RQ2／RQ3、做模型資格與最多 5 案 pilot。正式 180 案須先完成真實模型資格、pilot、分析規則與執行 manifest 凍結。播放器是前端示意，demo provider 是合成流程驗證，兩者都不是模型資格或研究結果。RQ1 是已見樣本的回溯比較；新 RQ2／RQ3 沿用這 180 案仍是回溯延伸。

10 月 15 日已在 GPUtw 嘗試 Qwen canary，因模型載入／反向代理 HTTP 524 中斷，未通過資格；10 月 16 日使用者確認主機已關閉。尚未登記或排入正式實驗。Claude 尚無獨立回覆。

## 1. 先確認兩個端點與來源身分

記錄實驗室／主機代稱、Ollama 版本、模型完整 tag／digest／量化格式、context length、parallel、逾時。qwen3:32b 為研究與裁決模型 A，gemma3:27b 為辯論模型 B。下列本機埠只是 SSH 通道範例，必須換成實際設定；不可把可連線當成模型已合格。

```powershell
# 由使用者在另一個終端開啟各自的 SSH 通道；替換帳號與主機
ssh -N -L 11435:127.0.0.1:11434 帳號@模型A主機
ssh -N -L 11436:127.0.0.1:11434 帳號@模型B主機
# 在本機確認各自 inventory，僅記錄 tag/digest，不記憑證
Invoke-RestMethod http://127.0.0.1:11435/api/tags
Invoke-RestMethod http://127.0.0.1:11436/api/tags
```

## 2. 使用獨立來源快照，做記憶探針與基礎 canary

已準備獨立備份 work/final-review-20261015/probe-snapshot/research.sqlite3，來源為 RQ1 既有 backup；原始 work/rq1-snapshot 不交給 Store 初始化。memory_probe 現在使用真正唯讀 SQLite，且拒絕有 WAL 的路徑。下列會呼叫實際模型，只在硬體／費用安排完成後執行；輸出使用新的名稱，保留每次嘗試。

```powershell
Remove-Item Env:GPUTW_OLLAMA_BASE_URL -ErrorAction SilentlyContinue
$env:OLLAMA_BASE_URL='http://127.0.0.1:11436'
.\.venv\Scripts\python.exe scripts/memory_probe.py --model ollama/gemma3:27b --mode recall --protocol-hash b1da80ee --data-dir work/final-review-20261015/probe-snapshot --out work/gemma-recall-new.json
.\.venv\Scripts\python.exe scripts/memory_probe.py --model ollama/gemma3:27b --mode identify --dates 2023-06-30 2024-06-30 --protocol-hash b1da80ee --data-dir work/final-review-20261015/probe-snapshot --out work/gemma-identify-new.json
.\.venv\Scripts\python.exe scripts/run_model_canary.py --model ollama/gemma3:27b
```

recall 預設七個分析日共 63 案；identify 指定與既有探針相同的兩個日期共 18 案。模型 A 換成其埠與 tag 另跑同樣三項。既有 canary 只測一般同質格式／引用，不涵蓋異質路由、Domain View、Aggregator 或兩個控制，不能以此宣稱新版設計已合格。記憶探針結果只說明這種問法下有無可見回想，不證明沒有訓練記憶。

## 3. 完整設計的隔離 pilot

scripts/run_design_pilot.py 接受 BatchInput JSON，將指定資料複製到新的輸出 Store，來源只以唯讀開啟。預設僅離線規劃，不聯網、不建立 job、不提供正式資格；加 --execute 才會實際 probe／呼叫模型。pilot 最多 5 案，全部標為 qualification，不登記、不中途跳過失敗案。使用固定的最早日期案例，不依績效挑選。

已產生三案範例，需先核對端點：
- work/final-review-20261015/rq2-pilot.example.json（AA／AB／BA／BB，seed 905）。
- work/final-review-20261015/rq3-pilot.example.json（fixed、兩 controls，seed 905）。
- work/final-review-20261015/rq2-report-bank-pilot.example.json（只做輸入庫，seed 904）。

```powershell
# 以下預設離線；每次 output 必須是新目錄
.\.venv\Scripts\python.exe scripts/run_design_pilot.py --source-db work/review-remediation-20261015/rq1-source-backup.sqlite3 --cases work/final-review-20261015/rq2-pilot.example.json --output work/rq2-offline-new --mode pilot
.\.venv\Scripts\python.exe scripts/run_design_pilot.py --source-db work/review-remediation-20261015/rq1-source-backup.sqlite3 --cases work/final-review-20261015/rq3-pilot.example.json --output work/rq3-offline-new --mode pilot
# 安排好實機後，換新 output 並加 --execute；RQ3 的預設模型端點由 OLLAMA_BASE_URL 指定
```

pilot 驗收：所有必要 arms／原始回應齊備、無 provider／schema／引用／namespace 降級；28 提案的整合提示未超 context、無截斷；tokens／重試／呼叫時間／總延遲可追溯；pause/resume 與模型 digest 維持一致。只看格式、失敗率、成本與延遲，不依準確率或 Sharpe 調方案。程式跑完不等於以上研究者檢核已通過。

## 4. 登記前鎖定的研究規則

| 項目 | 建議提案／必須明訂 |
|---|---|
| RQ2 | AA／AB／BA／BB；正式 seed 905／906／907；共用逐案報告 |
| RQ2 family | AA、BB 兩 homo baseline × accuracy、Sharpe 共四端點共同 Holm；不同 baseline 結果分列，不選較好者 |
| RQ3 | fixed、C_domain 對 C／C_budget／C_partition；不稱純分工或 token 匹配 |
| RQ3 family | 新離線入口提供三比較 × accuracy／Sharpe 六端點共同 Holm 的保守提案；若改 primary／secondary family，先改版、重驗並登記 |
| 推論 | accuracy 先在案例內平均 seed／ABBA，再保留同日期全部股票與條件做日期區塊；Sharpe 用同日 portfolio，不平均 Sharpe、不串接 seed |
| 日期區塊 | 日期區塊長度與日報酬區塊長度必須事前指定；本次執行候選固定為 2 與 20，分析計畫另列 1/2/4 與 10/20/40 敏感性；尚未正式登記。日期只有 20 群，須保留限制 |
| 失敗／缺失 | 保留失敗與重試，不依結果排除；正式分析要求完整共同 180 案。不能把缺成本當零，無法估計時顯示未知 |
| 記憶 | 同 seed、同條件／arm、同 ticker、已成熟 gated 記憶；一次排齊日期序列、同一 DB 只跑一個排程程序；早期案暫停時先暫停整批並修復，再繼續 |
| 凍結 | 程式／image／資料 IDs／模型 digests／seed／report hashes／配置／分析程式與family清單，保存實際 fingerprint。程式改動後不得續用舊資格與登記 |

報告 v9 已同步 RQ2 四端點與 RQ3 六端點的共同 family 提案；正式啟動前仍須確認並鎖定選定分析計畫。RQ2 已補逐 seed Sharpe interaction／樣本 SD；任一 seed 不可估計時 SD 為未知並列出可估計數，不以部分 seed 代替完整變異。

## 5. RQ2 輸入庫與正式執行的順序

輸入庫使用不在正式清單中的 seed（範例 904），其餘 protocol 設定必須與正式完全一致。用 runner 的 --mode report-bank --execute，只跑到 neutral_report_locked，保存 paused、無 owner／wants_run／決策／回測的來源工作。最多 180 案；來源一旦出現任何決策就拒絕綁定。不能讓輸入庫 seed 與任何正式 seed 重複，否則來源工作會佔用正式案例。

report-bank 位於 runner 輸出的 data/research.sqlite3。正式服務必須以這個含輸入庫的 Store 作為研究資料庫（先備份），或另做經驗證的完整匯入；來源 job ID 無法跨資料庫直接引用。不要只複製 dataset 就認為 report bank 已帶過去。

逐案正式 request 加 neutral_report_job_id 與 neutral_report_hash；905／906／907 各一個正式 protocol hash。先做三批 --preflight 等價檢查與 JSON 核對，再呼叫 /api/studies/preregister、/enqueue；目前 UI 的 plan 不能替你自動補逐案來源 ID／hash，正式 RQ2 請用已核對的 BatchInput 檔。RQ3 也應在整套 pilot 與分析規則定案後才登記。

## 6. 預算與分析

RQ2 名義決策呼叫：64 × 180 × 3＝34,560；研究輸入庫每案約 3 次 LLM 研究呼叫，重試另計。RQ3：81 × 180＝14,580，研究層、重試另計。資訊不足的領域會少呼叫，兩種架構不保證 token／牆鐘相等。GPU 小時與費用只能用這次 pilot 的實測估計，不沿用舊價格。

正式完成後，先 SQLite backup，再使用 scripts/analyze_rq2_snapshot.py（--protocol-hashes 三個完整 hash）或 scripts/analyze_rq3_snapshot.py（--protocol-hash 一個完整 hash）。兩者都指定 --date-block-length 與 --daily-block-length、全新 --output。RQ3 新入口使用完整共同四 arm 面板與六端點 family；若任何主端點不可估計，保留失敗狀態，不用部分端點挑選結論。

本手冊不代表硬體、真實模型或研究者分析規則已核准；它提供接下來可執行及驗收的順序。
