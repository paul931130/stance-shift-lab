# 專題整體審查（2026-10-14）

## 審查範圍與結論

系統版本：`4436b47`，審查開始時工作樹乾淨。主報告採用申請共用資料中的 `application-meeting-20261007_v7.tex`／同名 PDF（50 頁），而不是 repo 中較早的 meeting 稿或 application／SSRN 稿。主報告絕對位置：`C:/Users/paul9/Desktop/115-1/研究所申請/共用資料/專題與報告/2026-10-06_專題初稿修正版/`。

本次檢查報告、研究協議、Engine、Model Router、Domain Debate、Aggregator、統計與報表、正式登記入口、前端設計與統計面板，以及現有測試。PDF 抽看實體第 24、26、40 頁，未見明顯溢出或重疊；這不是全 50 頁的排版驗收。未修改報告或系統行為、未啟動付費模型、未執行新正式實驗。

**總評：已具備可研究、可展示的流程原型；RQ1 的負面結果定位合理。但報告、登記草稿與系統之間仍有重要落差，RQ2／RQ3 尚不能直接依目前預設啟動成符合 v7 的正式研究。**

RQ1 的可辯護主張是：指定九檔股票、180 季度案例與鎖定流程下，未取得整套 D 優於整套 C 的顯著證據。不能解讀為等效、單一立場交換的因果效果，或市場通用結論。RQ2／RQ3 的程式存在，不代表真實模型資格檢驗、正式登記或實驗結果已完成。

## 已確認問題（按優先順序）

### 1. [P1] RQ2／RQ3 摘要繞過正式結果的資格篩選與案例去重

證據：`research_service/web/studies.py:226`、`:232` 僅以 `status == complete` 過濾，再交給 `model_router.rq2_summary`／`rq3_reporting.rq3_study_report`。主報表則透過 `reporting._completed_unique` 核對正式就緒、登記樣本、登記時間、qualification 身分、降級與重複案例等。

後果：RQ 專用摘要可能將未登記或 qualification 工作算入，重跑同一案例也會改變案例權重。這兩個摘要目前明確標為「描述統計」，因此不能稱作假造顯著性；但仍應區分可用正式樣本與所有探索工作。

重現：兩個唯一案例的 RQ2 interaction 為 0.5；重複放入第一案後，案例數從 2 變 3，interaction 變為 0.6666667。證據保存於 `tmp/review-20261014/reproductions.json`。

建議：共用正式 eligibility／去重邏輯，提供明確 exploratory 模式，回傳納入／排除清單與原因；同案六個主要 arm 必須完整配對後才計入 interaction。不能各 arm 各自跳過缺值而使用不同分母。

### 2. [P1] v7 的多種子 RQ2 尚無跨 seed 的完整登記與分析流程

報告 v7 第 493 行要求每條件至少三個 seed。`inference_seed` 會改變 protocol hash；現有正式研究以 hash 分組，排入與重複檢查以 dataset 判定，主報表以 `(ticker, analysis_date)` 去重。`rq_analysis` 的主要輸入則為每案一筆 correctness 或日報酬序列。

可以分別登記三個 hash 執行三批，但目前不能將它們直接當成同一研究的三個 repeat 做完整分析；跨 hash 直接拼接也會失去原有 pooling 保護。

建議：明訂 study／case／arm／assignment／seed 的識別層級，先鎖定 seed 清單與共用資料／報告身分，再定義 seed 內配對、seed 間平均與變異報告。重抽樣保留同日期的全部股票、條件與 seed；180×3 不是 540 個獨立案例。記憶亦應依條件與 seed 隔離，執行順序需固定。

### 3. [P1] RQ2 必要 B/B 對照與新版推論尚未對齊

v7 第 493、510 行將 M2/M2 定為必要，並要求分別以 M1/M1、M2/M2 計算 interaction。程式支援 BB 路由，但 `protocol.py:53` 預設只有 AA/AB/BA，前端 `design-panel.js:64` 仍將 BB 顯示為選填；`rq2_summary` 只計算相對 AA 的 interaction，`rq_analysis.RQ2_ACCURACY_ARMS` 也只有 AA 與異質配置所需的六組。

建議：為 v7 建立明確 preset，要求 AA/AB/BA/BB；兩種 homo baseline 的 accuracy／Sharpe contrast 都要有輸出。登記前決定兩個 baseline × 兩端點的 multiplicity family、主要判定規則與結果方向不一致時的解讀。B/B 可診斷能力組成，仍不能完全識別一般性的「異質性效果」。

### 4. [P1] RQ3 未實作 v7 要求的兩個必要對照

v7 第 520、545 行限定主要 RQ3 使用固定立場 C，並要求約 29 呼叫的資源對齊通才對照、資訊切分但不辯論的消融。現有 `DomainDebateSettings.rule` 預設 `both`，前端亦預選固定＋交換；現有主要 arms 是 A/B/C/D、C_domain／D_domain，沒有上述兩個必要對照。

`compute_matching` 只是標籤，程式明確說不強制匹配或重新分配預算。因此設定 `nominal_calls` 並不會產生 29 呼叫通才對照。

建議：先定義並實作兩個 control 的提示詞、輸入、呼叫預算、判定規則與版本；預設改成與 v7 一致的固定立場研究 preset。Generic engine 可保留其他規則。報告中「為了讓比較只改變分工」仍應改成「固定辯論規則，避免再混入立場交換」，因為同時改變呼叫數與資訊切分。

### 5. [P1] RQ1 表格仍缺可交付的端到端重算證據

v7 的紀錄完整度表第 847–852 行仍將登記 hash／時間、180 案原始輸出、計算版本與配對日序列列為未取得。repo 的 `docs/rq-prep/rq1-promotion-audit.md` 則已有 2026-10-08 的資料庫稽核記錄，包含 `b1da80ee…`、登記時間、180 案與 C=105／D=99 的核對；但該稽核也明示 Sharpe／LW／群聚區間未重算。

本次唯讀檢查 local `research-data/research.sqlite3` 只有 5 個舊版工作、0 筆登記，沒有報告那批正式資料。Docker daemon 未運行，因此本次未重新取得 volume 內的 180 案，也未重算報告的 Sharpe 0.54／0.59、p 值與區間。

建議：不要把舊稽核當成本次重新驗證；保留凍結映像，以唯讀副本匯出 dataset／job／原始輸出／記憶／日面板，附 SHA-256、commit、image、model digest 與分析程式版本，再從匯出重建報告全部主表及敏感性結果。回溯樣本的定位仍保留，補齊紀錄不會使樣本重新成為未見樣本。

### 6. [P2] RQ3 缺值成本被平均成較低數字

`rq3_reporting.py:38` 將已知成本總和除以全部案例數 `n`。一案 100 tokens、一案 None，會回傳平均 50，而不是平均未知或「已觀測一案平均 100」。雖然另有 missing count，前端卻明示缺值不當作零，顯示的平均仍等價於把缺值零填。

成本比也使用各 arm 的部分總和，兩 arm 缺值比例不一致時會偏誤。

建議：主要均值在有缺值時回傳 None；另列 observed_mean、observed_n、missing_n。跨 arm 成本比使用共同完整案例，並顯示完整率。重現亦存於 reproductions.json。

### 7. [P2] 「Aggregator 只讀 View」與實際提示詞不同

`aggregator.py:65–85` 即使 `aggregator_input == views`，也把 View 引用的原始 evidence 與 base_rates 放進 pseudo_report；所有 View 都不引用時，退回全部合格的領域 evidence。前端卻標示「僅領域觀點」。

這不一定是錯誤設計，引用原始證據可能有利於稽核；但它和「只讀四份 View」是不同的資訊條件，全棄權時更改為全證據裁決也需要預先定義。

建議：明寫成「Views＋其引用證據＋基準率」、將 fallback 納入登記並另列案例數；或另實作嚴格 View-only 條件。不能把 fallback 案例默認成通常的 View-only 整合。

### 8. [P2] RQ2／RQ3 完整推論尚未接上研究資料輸出

`rq_analysis.py` 已有正確方向的 interaction、同案 AB/BA 合併、日期區塊與 Sharpe 組合 helper；但現有 `/rq2`、`/rq3` endpoint 只呼叫描述摘要，沒有從正式 job 建立完整配對陣列與對齊日面板的分析入口。RQ2 helper 亦未完整處理 BB、多 seed、共同 family。

建議：提供可重現的離線分析命令，輸入凍結 export＋登記分析設定，輸出各端點、CI、原始／校正 p、排除清單與表格；同一輸出再供 UI 使用。先做 deterministic fixture 的端到端資料對應驗證，不能只驗算 helper 的公式。

### 9. [P2] 文件沒有共同的版本與狀態入口

README 第 61–62 行仍把 RQ2 定為月度穩健性、RQ3 定為跨模型穩健性。RQ-prep 索引與草稿還寫 Model Router／Domain Debate／Aggregator 未實作。v7 的模組表也停在 10 月 7 日的未實作狀態，但目前 repo 已有這些程式、web 接線與測試。

建議：保留舊報告為有日期的研究快照，另外維護目前版 status matrix，分別列「設計／程式／真實模型資格／正式登記／實驗完成／統計重算」。不要把「已實作」直接改成「已完成研究」。主報告與 application／SSRN 應標明各自用途與同步範圍。

## 研究設計與報告評估

值得保留的部分：v7 明確區分已完成 RQ1 與未執行 RQ2／RQ3，沒有把不顯著寫成等效；D 被定義為交換、隔離、自我引用與重試的流程套組；RQ2 比較 interaction，而不是比較「一邊顯著、另一邊不顯著」；AB／BA 共用案例，不誤算成 360 個獨立樣本；RQ3 把 Domain Views 當中間產物而非獨立樣本；候選層與 gated 層、案例 n 與日序列 T、目的性選股、生成噪音、成熟記憶與訓練記憶風險均有揭露。

仍需定案：

- **檢定力與有效樣本量**：180 案只有 20 個日期，RQ1 僅 16 個 C/D 分歧。增加 seed 可減少生成噪音，不會增加市場日期數。RQ2 應以日期依賴、AB/BA 相關、多 seed 與多端點聯合門檻做事前規劃；不能使用觀察到的 16 分歧推導的條件式 MDE 充當事前規劃。
- **長期記憶與重跑順序**：各 arm 自己的歷史記憶讓估計量成為動態流程效果；同一 seed 內必須按時間推進、可用記憶快照必須記錄。若關閉記憶作消融，應列成另一個有版本的研究條件。
- **機制證據**：70% 原文相符只能證明引用來源。反駁品質、證據使用變化、Judge 採用哪一方等可做盲評診斷；少量選取案例不能識別原因。只讀自己但不交換等消融與 C/C′ 多 seed 應放入新的方案，不能事後改寫 RQ1。
- **金融可用性**：一律看多、同配置買進持有、低曝險 1/180 權重、RF=0、未計完整放空成本都應保留說明。v7 結論第 865 行「沒有勝過最簡單的做法」宜明確限定為「本樣本點估計未超過基準；尚無證據支持統計劣勢」，避免從不顯著比較再做方向性推論。
- **新樣本**：RQ2／RQ3 若繼續用已看過的 180 案，仍是回溯延伸。新日期或新標的才是獨立驗證；也要考慮模型訓練截止日與資料來源的 point-in-time 可得性。
- **成本預算**：舊草稿 RQ2 的單 seed、optional BB 與 RQ3 V=0／7呼叫比較預算，不能直接套用 v7 的必要 BB、至少三 seed、29 呼叫 control 與消融。先依最終 call plan 重算，再以實機 canary 量測。
- **呈現**：v7 用白話解釋重要概念有助於口試，但 50 頁中「候選假說、未執行、不能因果歸因」多次重複。可集中為一張研究問題／估計量／比較／狀態表，以及一張限制表；表格與正文避免重複完整流程。

## 文獻核對

抽查三項直接相關文獻：Zhang et al. 的模型異質性論文、Liu et al. 的角色交換論文與 Chen et al. 的 MPT 均有對應的官方來源。PROClaim 的 v1 HTML 亦支持「拿掉 role-switching 少約 4.2 百分點、總 token 約為 Standard MAD 的 11 倍」的報告敘述。上述結果來自其他任務，不證明本專題金融預測有效；報告目前對此已有合理限縮。

- https://arxiv.org/abs/2502.08788
- https://openreview.net/pdf/ed2a9b5040b6924b521777457881364224a50b85.pdf
- https://aclanthology.org/2026.findings-acl.1389/
- https://arxiv.org/html/2603.28488v1

只抽查上述主張，未完成所有參考文獻逐篇全文稽核。

## 驗證與工作順序

本次 `ruff check research_service scripts` 全部通過，前端所有 JS 的 `node --check` 通過。完整測試執行 411 項：409 通過、2 跳過（缺 Chromium 的瀏覽器 E2E、Windows 不適用的 POSIX 權限檢查）、0 失敗／錯誤，耗時 35.449 秒；紀錄位於 `tmp/review-20261014/tests-verified.txt`。首次測試遭沙盒暫存目錄 SQLite 存取限制，改為 repo 內 tempfile 後，Windows asyncio 的本機 socketpair 初始化仍被沙盒卡住；traceback 已定位，改在沙盒外執行後完整通過。這些環境問題不列為系統功能缺陷，也不使用首次的 227 個錯誤作為專題品質評估。

程式問題的小型重現結果位於 `tmp/review-20261014/reproductions.json`。現有測試通過不代表上述研究設定、正式樣本 pooling 與缺值均值問題已被涵蓋；本次沒有另外修改測試或修正系統。

最優先工作：先保存並重算 RQ1 的證據鏈；接著同步目前研究狀態與 v7 方案；修正正式摘要資格／去重、缺值成本與多 seed 分析；補 RQ2 BB 與 RQ3 必要 control；最後完成模型資格、實機 canary、預算與新版登記。新實驗完成后才能更新結果章。
