> 2026-10-17 後續修正與驗收以 [正式前整備狀態](preformal-readiness-2026-10-17.md) 為準；本頁保留原審查紀錄。

# 最終整體審查與實驗推進判定（2026-10-15）

**判定：可進入隔離資格檢驗與 3–5 案 pilot（Share with caveats）；正式 180 案批次仍為 Needs revision。審查涵蓋範圍為 Partial：本機報告、來源證據、系統、統計與流程已交叉檢查，實際模型端點、硬體與正式執行未驗證。**

最新報告另存 [v9 來源](../../report/application-meeting-20261015_v9.tex)／[PDF](../../report/application-meeting-20261015_v9.pdf)，保留 v7／v8。唯一目前操作入口是 [實驗推進手冊](../rq-prep/experiment-launch-20261015.md)。以下包含本輪已修正問題與尚待鎖定規則，不將原型通過稱為研究完成。

## 最重要的判定與處置

1. **[P1，已修正] 多 seed 批次規劃會偷偷退回 905。** `research_service/web/studies.py:135–138` 原先建 JobInput 漏傳 inference_seed；UI 即使填 906／907，plan 的 ready_cases 仍是 905，三批會成同一協議並被判重。現在完整傳遞；新增回歸驗證 905／906／907 產生三個不同 hash，登記、enqueue 後工作仍保存各自 seed。

2. **[P1，已修正] 共用研究輸入庫可能佔掉正式案例，也可能從已見決策中挑報告。** `research_service/shared_reports.py:9–27` 原來允許來源與正式同 hash，且完成來源仍可綁定。重現顯示同 seed 905 的 bank 讓正式 enqueue skipped_existing，已有 24 decision records 的來源仍通過。現在只接受獨立 seed、paused、無 owner/wants_run、最後節點 neutral_report_locked、無決策/回測/identity failure 的來源。建議 bank 904，正式 905／906／907；研究者仍須先鎖定整份 seed 清單。

3. **[P1，已修正] 記憶探針不是唯讀，可能 migration 歷史快照。** `scripts/memory_probe.py:33–54` 改成 standalone SQLite readonly/immutable Reader，完全不初始化來源 Store，拒絕 WAL，顯式關閉連線。回歸測試用舊 schema，確認查詢成功、寫入拒絕、來源 SHA 不變且未新增 sidecar。新手冊改為 PowerShell 與隔離備份路徑，舊 Bash 手冊標明歷史用途。

4. **[P1，已補入口；真實結果待驗] RQ3 原先能執行，但沒有完整凍結快照→正式推論管線。** 新增 `rq3_inference.py` 與 `scripts/analyze_rq3_snapshot.py`，要求註冊的完整 9×20 grid、相同權重/設定、四 arm 同案完整 Boolean、同案例日面板、報告與資料 hash、成熟且隔離的記憶，拒絕早期未完成案例污染。三個 C_domain−baseline 比較使用同一個 180 案分母；六端點共同 Holm 是保守提案，不是已登記決策。以完整 180 案合成 SQLite 跑通 CLI，未取得真實 RQ3 結果。RQ2 CLI 也補完整市場 grid、記憶邊界與 early-pending 檢查。

5. **[P1，啟動前須完成] 真實模型資格、分析規則與環境尚未凍結。** 需要實際兩端點、weights、Ollama、context/parallel/timeout、image/source manifest，以及完整設計 pilot。舊同質 canary 不包含 RQ2 router 或 RQ3 controls。RQ2 四端點、RQ3 六端點 family、日期與日報酬區塊長度、失敗/缺失/恢復規則需事前寫定；v9 已明確標記為提案。這些不是「測試通過就自動核准」的事項。

6. **[P2，保留待辦] 逐 seed Sharpe 變異尚未列出。** `rq_repeats.py:55–58` 已有各 seed accuracy interaction／SD，未列逐 seed Sharpe interaction／SD。合併 portfolio 的主要 Sharpe 推論可用，但正式報告承諾的 seed 變異揭露應再補描述輸出；不要把多 seed 當新增市場樣本。

## RQ1 的獨立核算與結論界線

本輪直接讀取封存 ZIP 中的原始 job rows，另用 plain Python 樣本矩與 SciPy exact binomial 計算，不呼叫 reporting／statistics 的顯示 helper：180 案、20 個分析日，C 正確 105、D 正確 99，C-only 11、D-only 5；McNemar exact p＝0.210113525390625。逐案例日報酬按 1/180 加總，T＝1219，C Sharpe＝0.5912556041051471、D＝0.5383993328628929，與報告一致。ZIP SHA-256 仍為 9c606070a491f244a27c6bbbddad980c9c4e9f6c16dc8b1c34e2ff87bb2e8f9a。

本輪未獨立重寫 Ledoit–Wolf 演算法；沿用前輪保存的歷史 reporting 重算結果與原始碼稽核。亦未重跑真實模型或原 Docker image。可支持的是指定樣本與鎖定流程下未取得 D 優於 C 的顯著證據，不支持等效、單一交換機制的因果效果或通用投資優勢。沿用已見 180 案的 RQ2／RQ3 仍是回溯延伸；獨立新日期/新標的驗證要另行設計。

## 新增的實際推進工具

- `scripts/run_design_pilot.py`：預設離線，明確 --execute 才連模型；最多 5 案 pilot、最多 180 案 report bank；新 Store、來源唯讀、失敗即停止、逐案 ZIP、source/runner 指紋、formal_launch_ready=false。pilot 標 qualification，不能算正式結果；空記憶小樣本也不能代表完整 180 案時序記憶已資格化。
- 已從原始登記資料選固定最早日期三案，產生 rq2／rq3／bank 的 example JSON。兩種三案離線規劃均已在實際歷史資料副本成功，未探測端點、未建 job。端點值只是本機 SSH 通道範例，需本人確認。
- bank source ID 只能在含來源工作的同一 Store 內使用；新 runner 的 data/ 是獨立資料庫。正式服務須沿用該 Store 或另做經驗證的完整匯入，不能只複製 dataset 或跨 DB 引用 ID。
- 正式服務會在某案暫停後繼續其他 queued 工作；若早期案例失敗，先 pause-all、處理早案再繼續，避免後案先凍結缺漏記憶。本輪分析 CLI 會拒絕已記錄 pending_earlier_cases 的結果；不能把事後重跑當成補回既有 frozen memory。

## 最短推進順序

1. 確認模型 A/B 的實際端點與完整 digest，使用新手冊的 PowerShell 指令，在獨立來源副本執行兩模型 recall／identify／基礎 canary。
2. 以 example BatchInput 跑 RQ2 與 RQ3 完整設計的 3–5 案 pilot，核對原始回應、引用、失敗、截斷、28提案整合長度、tokens、延遲與權重；不依績效調方案。
3. 明訂 seed／family／區塊／缺失／記憶與恢復規則，建立新 source/image/config manifest。正式批次前任何程式改動都要重驗相關資格，不續用舊 hash。
4. 用正式 seed 清單以外的 904 建立逐案鎖定報告庫，保留 paused/noowner；在同一 Store 逐案帶來源 job ID／hash，分別登記 905／906／907。
5. 先 RQ2 再 RQ3，按分析日一次排齊、保留失敗及成本，完成後 SQLite backup→對應 CLI→封存輸入與輸出。沒有硬體實測前不採用舊 GPU 小時／費用。

RQ2 名義決策呼叫 34,560、RQ3 14,580，研究層、重試另計；實際 token、成本與時間須由 pilot 估計。不要把呼叫數相近稱作 token 或計算量嚴格匹配。

## 審查覆蓋與限度

下列分母是本輪具名組件/主張的範圍清單，不是所有檔案或所有測試組合；0/N 只表示沒有觀察到尚存缺陷，不表示 N 項真實執行都已驗證。類別相互重疊，不可加總成「準確率」。本輪仍缺實際模型環境與正式分析鎖定，故整體覆蓋為 Partial。

**平台與報告品質**

| Category | Observed defects | Assessment |
|---|---|---|
| Usefulness and completeness | 1 / 6 | 可進隔離pilot；真模型資格與正式分析設定仍未鎖定。 Partial review: 2 scoped items have incomplete or stale evidence (Actual model qualification and deployment; Locked families, dates, failures and seeds). |
| Analytical clarity | 0 / 2 | v9區分回溯RQ1、待執行RQ2/RQ3與待登記family。 |
| Visual and interaction consistency | 0 / 2 | 沿用未變動播放器桌面/手機畫面與本輪v9第26–29頁；不是逐頁全文排版稽核。 |

**分析正確性與穩健性**

| Category | Observed defects | Assessment |
|---|---|---|
| Source authority and confidence | 0 / 2 | RQ1原始匯出有封存及獨立核算；實際端點/digest仍待取得。 Partial review: 1 scoped item has incomplete or stale evidence (Actual model qualification and deployment). |
| SQL/value accuracy | 0 / 3 | RQ1主結果獨立核算；新RQ3推論用180案合成快照驗證，無真實RQ2/3結果。 |
| Within-chart agreement | 0 / 2 | 本輪主要數表與文本對應；不評未產生的研究圖。 |
| Complete source details | 0 / 6 | 本機來源/腳本/manifest可追溯；真模型環境與映像仍未知。 Partial review: 1 scoped item has incomplete or stale evidence (Actual model qualification and deployment). |
| Cross-artifact consistency | 0 / 3 | 新手冊與v9對齊程式；舊草稿已標示歷史用途。 Partial review: 1 scoped item has incomplete or stale evidence (Locked families, dates, failures and seeds). |
| Data-quality controls | 0 / 6 | 已查正式資格、seed、共用報告、readonly與配對；無實機資料完整度認證。 Partial review: 1 scoped item has incomplete or stale evidence (Actual model qualification and deployment). |
| Conclusion support | 0 / 5 | 不把不顯著當等效，不把原型/合成通過當研究結論。 Partial review: 1 scoped item has incomplete or stale evidence (Locked families, dates, failures and seeds). |

## 驗證紀錄

最終整合測試、Ruff、JS 語法、v9編譯與視覺抽查結果完成後記於下方。前輪播放器的 desktop/mobile 截圖與端到端測試僅在前端輸入和程式未改動的範圍沿用；本輪未逐頁重看所有52頁，也未逐篇重新核對所有文獻。三份審查分工是 Codex 內部交叉複核，沒有把它稱作 Claude 回覆；共享資料夾目前仍未收到 Claude 的獨立審查。


本輪最終驗證：445 tests（444通過、1項POSIX-only skip、0 failures/errors，199.495秒），包含Chrome一般流程／RQ3 controls／播放器、兩design pilot與180案合成RQ3 CLI。Ruff、所有前端JS語法、git diff whitespace通過。最初探針測試因Windows測試fixture未關閉SQLite導致cleanup失敗，已修正並納入上述全套通過；不把環境或fixture問題當成產品通過。

本輪另以目前 readiness.coverage 逐一重查原登記180份資料，180/180通過目前CPU資料門檻、0 blockers，內容hash全數相符（work/final-review-20261015/data-readiness.json）。這表示可供新版pilot，並不證明真實模型或正式環境合格。

v9 52頁，引用／交叉參照與overfull檢查無警告；已放大檢查26–30頁變更處。交付hash見 work/final-review-20261015/deliverables.json；原v7/v8不覆寫。尚未租GPU、聯網實驗、建立正式登記、commit或push。
