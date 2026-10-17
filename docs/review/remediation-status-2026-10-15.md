# 專題審查修正進度（2026-10-15）

## 工作邊界

本輪按 RQ1 證據重算、版本同步、統計入口、RQ2／RQ3 必要設計的順序處理。協作方式是與 Claude 共用此資料夾；交接紀錄在 `claude-codex-coordination.md`。目前沒有收到 Claude 的獨立複核回覆，不能稱為已完成雙方審核。

本輪不啟動付費 GPU、不執行新的真實模型實驗、不改舊登記、不部署或推送。新方案的程式驗證與真實模型／正式研究完成分開列示。

## RQ1 已核對

- 找到先前漏查的 `work/rq1-snapshot/research.sqlite3`，以唯讀連線做 SQLite backup，再分析獨立副本。原始庫不經 Store 初始化，不作 migration／backfill。
- 使用 `eb36a8a423183899cb8a2dfa250dc2a40e01bb1d` 的歷史 reporting 原始碼，確認 statistics／backtest／splits 的數值實作與該版本一致。
- 180 個註冊資料 ID 均通過內容雜湊核對；180 案通過正式資格與首次完成去重；3,960 筆決策均有原始回應，同案決策的 report hash 一致。
- 6,804 筆成熟記憶的同股、同組、同協議、期間、成本、層級與到期邊界均無違規。未對記憶的語意影響作因果推論。
- 主要日面板：2021-04-01 至 2026-03-31，1,219 日。C／D Sharpe＝0.5912556／0.5383993；McNemar p＝0.2101135，Holm＝0.4202271；LW p／Holm＝0.8015。與原報告四捨五入一致。
- 證據包：`work/review-remediation-20261015/rq1-audit/rq1-evidence.zip`，SHA-256 `9c606070a491f244a27c6bbbddad980c9c4e9f6c16dc8b1c34e2ff87bb2e8f9a`；另有 `audit.json`、`statistics.json`、`primary-daily-panel.csv`、`manifest.json`、`memory-audit.json`。ZIP 的每個 payload 已核對 manifest hash 與 CRC。
- 本次是歷史分析程式重算，不宣稱重新啟動了原 Docker image；伺服器版本、部分資料修訂版本等既有重現限制仍保留。回溯樣本不因補件而變成獨立樣本外結果。

重算工具：`scripts/audit_rq1_snapshot.py`。分析輸出與資料包刻意保留在 Git 忽略的 work 目錄，不公開原始資料。

## 系統已修改

| 項目 | 目前狀態 |
|---|---|
| RQ 專用摘要的正式資格／去重 | 使用與主報表相同的篩選，另外核對路由模型權重；回傳排除數與原因 |
| RQ2 完整配對 | 六組必要對比、或含 BB 的八組，使用同一完整案例集合；缺一組即排除整案 |
| RQ3 成本缺值 | 全樣本平均遇缺值顯示未知；另回傳 observed mean／n；成本比只用共同完整案例 |
| RQ2 BB | 新預設包含 AA/AB/BA/BB，正式登記要求全部對照；摘要分列 AA、BB interaction |
| RQ2 種子 | Job／Plan API 可鎖 inference seed；UI 可設定本批 seed；至少三 seed 的離線推論先在案例內平均，不增加市場案例數 |
| RQ2 共用研究輸入 | 可指定 Neutral Report 來源工作與 hash，重用四域研究輸出而不再呼叫研究模型；排入與直接建立工作均核對登記報告 hash |
| RQ2 成熟記憶 | 新版 `v3-1015.1` 中，AB/BA/BB 各自保存／讀取記憶，且核對路由權重，不再共用 AA 記憶 |
| RQ3 必要對照 | `rq3-1015.1` 固定立場可執行 C_budget（28 次獨立提案＋1 次裁決）與 C_partition（四域證據直接裁決，不辯論） |
| RQ3 可續跑與成本 | 控制組逐次保存、納入相同 Gatekeeper／回測、資源統計與三組配對比較；正式登記要求固定立場與兩對照 |
| Aggregator 資訊條件 | UI 與報告改為「View＋其引用證據＋基準率」；保留現有全棄權 fallback，不能稱為嚴格 View-only |
| 文件／報告 | README 與 rq-prep 指向目前狀態；v8 在 repo 另存，原 v7 不覆寫 |

新分析介面：`research_service/rq_repeats.py`；離線 CLI：`scripts/analyze_rq2_snapshot.py`。CLI 要求至少三個事前登記 hash、完整 180 案、八組配對、相同資料與報告內容身分、相同權重、對齊日面板；遇不一致拒絕合併。輸出含分析來源指紋、案例與 seed 清單、兩個 homo baseline、四端點 Holm family。此 family 是待登記的具體提案，不回溯套用 RQ1。

## 新方案的具體執行順序（尚未執行）

1. 凍結本輪程式、映像與實際模型 digest，先完成 qwen3:32b、gemma3:27b 的新版 canary／記憶與匿名辨識探針。指令與硬體需求見 `docs/rq-prep/gemma3-qualification-runbook.md`；不能沿用舊模型資格當作本次通過。
2. 先對 180 案建立研究輸入庫，停在 `neutral_report_locked`（尚未決策）；保存每案來源工作 ID 與 report hash，再供所有 seed 共用。共用報告須在各 seed 正式執行前固定，不依已見結果挑選。
3. RQ2 建議 seed 清單 905／906／907（正式登記前鎖定）、AA/AB/BA/BB，每 seed 一個登記 hash；每個 stock/date 的 batch request 另外帶 `neutral_report_job_id`、`neutral_report_hash`。每個 seed 的記憶以各自 protocol hash 隔離。三個 seed 合計 540 次流程重複，但獨立市場案例仍是 180、日期群聚仍是 20。
4. RQ2 名義決策呼叫為每案 64 次，三 seed × 180 案共 34,560 次；研究輸入庫每案約三個 LLM 研究呼叫，只有來源庫計費，不重複計入重用案例。實際重試／tokens／延遲待實機量測，不沿用舊預算。
5. RQ3 固定立場＋兩個對照，主要 Dom_C 對 C；額外對 C_budget、C_partition。含保留的 A/B/C/D，完整每案名義決策呼叫 22＋29＋29＋1＝81 次，180 案共 14,580 次，研究層與重試另計。Dom_C 缺領域證據時呼叫會略過，所以 29 是名義預算，不保證逐案實際呼叫相等，也不匹配 tokens。
6. 鎖定日期區塊長度、失敗／缺失規則、四端點 RQ2 family，以及 RQ3 三個比較的 primary／secondary family；先以 3–5 案 pilot 檢查格式、截斷、失敗率、tokens／延遲，不依績效調方案，再正式登記與執行。

離線分析範例（有三批真正完成的快照後）：

```powershell
.\.venv\Scripts\python.exe scripts\analyze_rq2_snapshot.py `
  --source-db <獨立快照.sqlite3> `
  --protocol-hashes <seed905完整hash> <seed906完整hash> <seed907完整hash> `
  --date-block-length <事前指定值> --output <新的結果.json>
```

上述尚無真實結果。尚待實驗室端點／硬體、實際權重 digest、資格輸出與 Claude 方法複核；未租 GPU 或排入付費工作。

## 協議相容性與驗證

本輪修改了影響流程的 engine／storage／protocol，source digest 會改變；**不可用本輪程式續跑舊凍結工作**。保留原 DB 與 RQ1 歷史計算程式；新研究須用新 hash、新資格與新登記。`v3-1006.1` 的舊 RQ2 結果仍可讀取原始輸出，不在新引擎中接續。

驗證結果與報告編譯結果於本輪完成後附記；只將實際跑過的驗證列為通過。


## 2026-10-15 恢復後最終驗證

- 已修正 RQ3 controls 的完成數／總輸出數，完整名義輸出為 81；瀏覽器標題區分通才階段與領域／對照階段。
- 最終全套：429 tests，428 通過、1 項 POSIX-only skip、0 failures、0 errors（116.393 秒）。包含本機 Chrome 的 RQ1 與 RQ3 controls 真實 UI 端到端測試；demo 通過不代表真實模型資格通過。
- Ruff 與所有前端 JS 語法檢查通過。證據：work/review-remediation-20261015/tests-final.txt、test-result-final.json。
- v8 已完成 XeLaTeX／BibTeX 多輪編譯，52 頁，沒有 undefined citations／references 或 overfull box；已看全頁縮圖並放大檢查第 38、45、46 頁。原 v7 SHA-256 未變；目前來源與 PDF hash 記於 work/review-remediation-20261015/report-source.json。
- 可閱讀交付：report/application-meeting-20261015_v8.pdf；來源與專用 bibliography 同在 report。先前交接所稱 47 頁未驗收 PDF 已被新編譯產物取代。
- 尚無 Claude 獨立回覆；共享資料夾的待複核項目仍有效。真實模型資格、3–5 案 pilot、統計 family／區塊長度凍結與正式登記尚未執行，RQ2／RQ3 沒有實驗結果。未啟動付費工作，未 commit／push。


## 2026-10-15 最終整體複核與推進入口

已完成 docs/review/final-review-2026-10-15.md，後續操作以 docs/rq-prep/experiment-launch-20261015.md 為準。新報告另存 v9，保留 v8；本輪修seed plan漏傳、共用報告來源seed碰撞/已見結果、探針非唯讀，補隔離pilot/report-bank runner及RQ3完整快照分析入口。445 tests全套444通過+1 POSIX skip；180/180來源資料通過目前CPU門檻。RQ1原始rows獨立重算一致。

僅放行資格檢驗與3–5案pilot的準備；真端點/digest/context/成本、正式family/區塊/缺失與恢復規則、image/source凍結仍待完成；RQ2逐seed Sharpe變異為P2待辦。沒有真模型結果、付費操作或新正式登記。Claude仍未回覆，Codex內部分工不當成Claude獨立review。
