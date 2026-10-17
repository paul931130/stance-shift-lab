# Claude／Codex 協作紀錄

## 2026-10-15 Codex

使用者要求依 `project-review-2026-10-14.md` 的順序修正，並由 Codex 與 Claude 協作。

- Codex 負責 RQ1 唯讀快照稽核、證據封存與重算，以及後續整合／驗證。
- 已找到 `work/rq1-snapshot/research.sqlite3`，其目標 hash 為 `b1da80ee8dbc9c372d9eab02455734a140714a233c2d669bb0177fe9ab267cd6`，有 180 個完成工作。已透過 SQLite backup 建立隔離副本，來源不經 Store 開啟，以免 migration／backfill 修改來源。
- 新增 `scripts/audit_rq1_snapshot.py`，使用歷史提交 `eb36a8a` 的 reporting 原始碼，先驗證 statistics／backtest／splits 與目前數值實作相同，再重算與封存。輸出放在 ignored `work/review-remediation-20261015/`。
- **更正先前審查**：10 月 14 日只查主要 local DB 與 Docker，漏查上述快照。因此「本次未重算」是當時工作範圍，不應延伸成「本機沒有 180 案來源」。
- 已嘗試呼叫本機 Claude Code 2.1.283，唯讀複核第 1、2、3、6、8 項，限制工具為 Read/Grep/Glob、plan mode、不得修改檔案。請求因 OAuth 過期在推理前失敗，沒有 Claude 的 review 結果。原始錯誤保存在 ignored `work/review-remediation-20261015/claude-review.json`。
- Claude 待辦：獨立核對正式樣本 eligibility／去重、各 arm 完整配對分母、成本缺值、多 seed、BB baseline 與多重檢定方案；指出原 review 的誤判與過度主張。請在下方追加回合，保留舊內容。協作登入恢復前，不將 Codex 的自查稱為 Claude 複核。

共同限制：不改寫 RQ1 的原始登記或既有結果；新分析與修正須另存版本／證據，不啟動付費 GPU、不啟動正式實驗、不推送公開倉庫。報告保持 RQ1 回溯比較、RQ2／RQ3 未執行的界線。

## 2026-10-15 交接

使用者已澄清協作僅透過這個資料夾，不需要 Claude CLI 登入。因用量將耗盡，要求立即先交接；目前修改已停止。**請先讀根目錄 `HANDOFF_20261015.md`**，其中列有本輪 RQ1 重算、最新程式、尚未完成的驗證、已知 RQ3 進度漏計，以及不可交付的第一遍 v8 PDF。尚無 Claude 獨立複核回覆。


## 2026-10-15 恢復後最終驗證

- 已修正 RQ3 controls 的完成數／總輸出數，完整名義輸出為 81；瀏覽器標題區分通才階段與領域／對照階段。
- 最終全套：429 tests，428 通過、1 項 POSIX-only skip、0 failures、0 errors（116.393 秒）。包含本機 Chrome 的 RQ1 與 RQ3 controls 真實 UI 端到端測試；demo 通過不代表真實模型資格通過。
- Ruff 與所有前端 JS 語法檢查通過。證據：work/review-remediation-20261015/tests-final.txt、test-result-final.json。
- v8 已完成 XeLaTeX／BibTeX 多輪編譯，52 頁，沒有 undefined citations／references 或 overfull box；已看全頁縮圖並放大檢查第 38、45、46 頁。原 v7 SHA-256 未變；目前來源與 PDF hash 記於 work/review-remediation-20261015/report-source.json。
- 可閱讀交付：report/application-meeting-20261015_v8.pdf；來源與專用 bibliography 同在 report。先前交接所稱 47 頁未驗收 PDF 已被新編譯產物取代。
- 尚無 Claude 獨立回覆；共享資料夾的待複核項目仍有效。真實模型資格、3–5 案 pilot、統計 family／區塊長度凍結與正式登記尚未執行，RQ2／RQ3 沒有實驗結果。未啟動付費工作，未 commit／push。


## 2026-10-15 流程示範播放器

使用者新增要求：模擬平台加入「播放示範」，跑流程並逐步說明。已新增 demo-player.js 與流程圖上方按鈕，以三幕九步播放 RQ1 基礎流程，提供節點標示、說明、固定示意輸出、暫停／繼續、1/2/4 倍速、重播、關閉及歷程。播放器不操作後端或實際案例狀態。

驗證：新增手機寬度 Chrome 測試已通過，涵蓋全流程、暫停、重播、關閉、URL 保持及零寫入請求；既有 RQ1／RQ3 Chrome 流程也各自通過。JS 語法、Ruff、diff whitespace 通過；桌面與 390px 手機畫面已看圖，未見橫向溢出。證據位於 ignored work/demo-player-20261015（player-final.txt、e2e-final.txt、desktop.png、mobile.png）。e2e-final.txt 的播放器失敗是測試誤將初始化的唯讀 preflight POST 算成播放寫入；已等待預檢就緒後重驗，最終以 player-final.txt 為準。尚無 Claude 回覆。


## 2026-10-15 最終整體複核與推進入口

已完成 docs/review/final-review-2026-10-15.md，後續操作以 docs/rq-prep/experiment-launch-20261015.md 為準。新報告另存 v9，保留 v8；本輪修seed plan漏傳、共用報告來源seed碰撞/已見結果、探針非唯讀，補隔離pilot/report-bank runner及RQ3完整快照分析入口。445 tests全套444通過+1 POSIX skip；180/180來源資料通過目前CPU門檻。RQ1原始rows獨立重算一致。

僅放行資格檢驗與3–5案pilot的準備；真端點/digest/context/成本、正式family/區塊/缺失與恢復規則、image/source凍結仍待完成；RQ2逐seed Sharpe變異為P2待辦。沒有真模型結果、付費操作或新正式登記。Claude仍未回覆，Codex內部分工不當成Claude獨立review。


## 2026-10-17 正式前本機整備

目前入口 docs/rq-prep/preformal-runbook-20261017.md；狀態 docs/review/preformal-readiness-2026-10-17.md。本次補 launch_package、RQ2 report-bank binder、明確RQ2三seed/RQ3單seed、RQ3 runtime、環境版本檢查；逐seed Sharpe描述與正式協議停止保護已驗收。465 tests：464 pass、1 POSIX skip、0 failure/error，包含三個 Chrome E2E；Ruff/JS語法通過。實際180案封裝及兩種三案離線pilot準備成功，合成180案bank綁定540筆成功但不得當正式輸入。證據 work/preformal-20261017/release-manifest.json。GPUtw上次Qwen HTTP524、資格未通過；使用者確認已關機，既有憑證401，本輪未租機/未呼叫模型/未建立新正式登記或job。剩真實runtime/canary/probe/pilot、真實報告庫及封存登記。Codex子代理不是Claude獨立複核，尚無Claude回覆。


## 2026-10-17 Claude 獨立複核（第一回合）

範圍：`rq_study.py`、`rq_repeats.py`、`shared_reports.py`、`rq3_controls.py`、`rq3_inference.py`，以及 `web/studies.py` 的正式登記 guard。以 commit `d8700d9` 的程式為準；全套 465 tests 在本機重跑通過（1 skip）。只讀程式與兩項小型執行檢查，未改任何程式。

**確認正確（未發現問題）**
- RQ2 完整配對：`rq2_study_report` 要求每案 C/D × AA/AB/BA 都有 Boolean 結果才納入；BB 只在協議要求時加進同一個共同子集；同案同 arm 重複列會報錯。分母一致。
- 多 seed：`rq_repeats` 先在案例內平均 seed 與 AB/BA，再以日期區塊重抽；AA、BB 兩個基準、四個端點共用同一組日期抽樣；seed 與 AB/BA 不增加獨立案例數。Sharpe 交互作用權重 (1,−1,−1,1) 方向正確。
- 四端點 Holm 在端點相依（AA、BB 共用 hetero 項）下仍有效，只是偏保守。
- `shared_reports.bind_report`：要求來源停在 `neutral_report_locked`、尚無任何決策或回測、除 seed 外設定相同、同 dataset/date、fingerprint 為目前程式、研究與路由權重一致、四域未降級，並以內容 hash 核對。結果依賴選擇（看過決策才挑報告）的路徑已封住。
- `rq3_inference`：共同完整案例面板、案例內日報酬缺漏即拒絕、記憶的組別／協議／成熟日邊界檢查、日報酬權重 1/180 與 RQ1 一致。

**需要處理或在報告中揭露**
1. （中）C_budget 的 28 份提案用 C 組溫度 0.2（實測 `temperature_for` 回傳 0.2；B 組投票為 0.8），seed 雖各不相同，提案可能高度相同，使「呼叫量對照」實際上接近單次判斷加裁決。這是設計選擇：維持 0.2（與辯論者同溫度）或改用投票溫度 0.8（提高多樣性）。正式登記前須決定並寫入登記文件；pilot 時應報告 28 份提案的方向一致率。
2. （中）共用報告庫使多 seed 只重抽決策層，研究代理人層固定，因此 `seed_accuracy_sd`／`seed_sharpe_sd` 會低估整體生成變異。報告中須寫明 seed 變異是「條件於鎖定報告」的決策層變異。
3. （低～中）`select_cases` 與正式 guard 不要求路由到 API 模型（如 Gemini 備案）有權重 digest：`select_cases` 只比對 (model, digest, id) 是否一致，digest 為 None 也會通過。現行決定模型 B 為 gemma3:27b（Ollama），故目前不觸發；若改用 Gemini 備案，正式 guard 應明確拒絕或標示「API 模型版本未鎖定」。
4. （低）C_partition 的提示仍包含四個研究代理人的 72 字摘要（`_compact_report` 的 `research` 欄位），並非只有四組證據。這些摘要與 Generalist、領域辯論者看到的相同，不是 Domain View，所以不影響公平性，但「partition-only」的描述應寫成「證據分組＋相同研究摘要、無辯論」。
5. （低）`rq_repeats` 逐 seed Sharpe 描述值用 `var(ddof=0)`，其餘 Sharpe 用 ddof=1；僅影響描述值，建議統一。

**Gemini 真實模型冒煙測試（10/14，HEAD 4436b47，非研究資料）帶出的待修項**
- Gemini 不遵守 JSON schema 的 `maxLength`，`models.generate` 重試時送出相同提示、未回饋錯誤，三次都失敗會暫停整個案例（RQ3 `uncertainty` 300 字、RQ2 `rebutted_claim` 240 字各一次）。
- 被拒絕的嘗試沒有 usage 紀錄時，`rq3_diagnostics.resources` 整組 token 與關鍵路徑變成 null。
- `failed_model_calls` 不帶 `model_route`，無法歸因到模型 A 或 B。
- 「未匹配來源數字」大量誤報期間長度（20、60）。
Claude 接著修前三項，修改會另外 commit 並記錄於此。

## 2026-10-17 Claude 修正與 Gemini 再測

- commit `08f7d67`：`models.generate` 在 JSON schema 失敗後，下一次嘗試附上「哪個欄位違反哪個限制」的修正提示；失敗的路由呼叫帶 `model_route`；路由的 validation_retries 與 compute_usage 規則一致；RQ3 view 在 generate 內放棄時保留 usage。469 tests 通過（1 skip）。這些檔案屬於雜湊來源，協議／RQ3 指紋已改變；`work/preformal-20261017/` 的封裝若記錄來源指紋，須重新產生。
- Gemini 再測（HEAD `08f7d67`，AAPL 2024-12-31，探索性、非研究資料，`work/gemini-smoke-2/`）：RQ3（rule both）88 次 HTTP／名義 80，2 次 schema 失敗由修正提示救回；RQ2（v3-1015.1，AA/AB/BA/BB）71 次／名義 64，4 次 schema 失敗全部救回。兩案皆不需手動續跑，`rq3_diagnostics.resources` 各組 token 皆非空，`failed_model_calls` 為空。決策全為 Buy。未驗證到「失敗呼叫帶 model_route」的真實案例（無失敗呼叫），由單元測試覆蓋。

## 2026-10-17 使用者決定

- C_budget 的 28 份提案維持溫度 0.2（與辯論者相同），先跑看看；pilot 須報告 28 份提案的方向一致率，若幾乎全同再重新討論。
- 使用者要求用 GPUtw RTX 3090 測試 Ollama 是否可用（實驗室環境類似）；這是連線與模型可用性測試，不是資格檢驗或正式研究。
