# RQ1 升格稽核：v3-1002.3（qwen3:32b，180/180）

依 `report/revisions/2026-10-06-agent-diversity/Part-C-研究方法Review.md`「舊 RQ1 升格正式新版結果前的確認」逐項核對。

- 稽核日期：2026-10-08
- 對象：protocol v3-1002.3，plan／protocol hash `b1da80ee8dbc9c372d9eab02455734a140714a233c2d669bb0177fe9ab267cd6`
- 資料庫：Docker volume `stance-shift-lab_research-data-qwen-v2` 的 `research.sqlite3`
- 讀取方式：以本機既有映像 `stance-shift-lab-research-qwen:v3-1002.3-reviewfix-20261002` 開一次性容器（`--rm --network none`，volume 掛 `:ro`，SQLite 以 `mode=ro&immutable=1` 開啟）。沒有啟動已停止的容器 `stance-shift-lab-research-qwen-v2-1`，沒有碰 :8000、:8002 的容器，沒有以寫入模式掛載任何 volume，也沒有讀出任何金鑰。本機沒有 `python:3.12-slim`，因此改用已存在的研究映像，沒有拉取新映像。

標記：**已核對**＝有直接證據；**部分**＝有證據但缺一環；**未核對**＝本次無法核對。

## 結論

紀錄層面大致可支持升格：登記早於第一案，180 案、單一協議設定、單一模型權重、原始輸出與彙總一致，主要比較的數字可由資料庫重算。不過仍有四個缺口：

1. 事前登記文件沒有補上 `b1da80ee` 的登記時間與 hash（文件寫明「登記後補上」，但目前全 repo 找不到 `b1da80ee`，只在報告 tex 裡出現）。
2. 統計／報表程式（`reporting.py`、`web/`）不在 protocol hash 內，Sharpe 與 Ledoit–Wolf 的數字本次沒有重算。
3. Ollama 伺服器版本（0.35.0）只記在文件，資料庫裡沒有。
4. 研究者還沒有確認。

在研究者確認之前，結果維持「prior result」。即使升格，這 180 案也已在前導試跑與規則調整中看過，只能稱為「規則鎖定後對既有樣本的回溯比較」，不能稱為獨立的樣本外結果。

## 逐項核對

| # | 項目 | 狀態 | 證據 | 缺少什麼 |
|---|---|---|---|---|
| 1 | Data version | **部分** | `preregistrations` 的 180 個 dataset ID 互不重複，排序後 sha256 為 `402660f0…a035`，與 `docs/e2prime-preregistration.md` 相同。180 筆資料集內容以 `research_service.data.digest()` 重算後 180/180 等於其 ID（內容定址）。FinBERT 權重目錄為 `models/finbert/4556d130…`。 | 行情的調整版本（yfinance 下載時點）與 FinBERT revision 沒有和登記綁在一起；新聞來源檔的 sha256 只記在文件 |
| 2 | Snapshot／Neutral Report hash | **部分** | 每案 22 筆決策紀錄的 `report_hash` 都相同（180/180 案只有 1 個 report hash），A/B/C/D 讀的是同一份中立報告 | 報告在執行中生成，沒有事前凍結的 report hash 清單；只能證明「同案四組相同」，不能證明「與某個外部快照相同」 |
| 3 | Protocol version／hash | **已核對** | 180 個工作的 `protocol` 設定只有一種。在映像內以 `StudyProtocol(**config).fingerprint` 重算，得到 `b1da80ee…cd6`，與登記相同。`preregistration_meta`：v3-1002.3、`ollama/qwen3:32b`、quarterly | — |
| 4 | Prompt | **已核對**（透過原始碼） | fingerprint 含 `prompt_source`＝9 個模組的原始碼摘要。映像內為 `6ea81119…7aa1`，與目前 HEAD 及提交 `eb36a8a`（2026-10-02 13:20 +08）重算的結果相同；更早的提交（`d9f6ba2` 以前）不同。每次呼叫另存 `prompt_hash`。提示詞全文見 `docs/review/prompts-v3-1002.3.md` | 沒有把 3,960 個 prompt_hash 與提示詞匯出檔逐一比對 |
| 5 | Model ID／weights／version | **部分** | 登記的權重 digest 為 `030ee887…7840`，180 個工作的 `model_identity` 都相同（32.8B，context 40960）。權重身分檢查共 9,734 次：9,727 次 pass，7 次為 `unavailable`（都在 after_step，時間點與已知的 DNS／網路中斷相符），沒有任何「digest 改變」 | Ollama 伺服器版本（0.35.0）、GPU 執行個體 ID 與量化細節沒有寫入資料庫，只在文件與記憶中 |
| 6 | Sample 與 exclusions | **已核對** | 180 個工作全為 complete，error 欄位 0 筆非空，與登記的 dataset 集合完全相同（預先登記的逐案設定 0 筆不符）。主分析沒有排除案例。37 案敏感性集合（36 案只有沿用即時新聞＋MCD 2023-12-31）在執行前已寫入事前登記文件 | 同一個資料庫裡另有其他協議的工作（例如 `83d05e65`＝v3-0913.1／qwen3:14b，180 案暫停；以及已作廢的登記）。統計時必須以 hash 篩選，報告要寫明 |
| 7 | Base 與 call seeds | **已核對**（有紀錄，不保證可重現） | `inference_seed=905`，`bootstrap_seed=905`，1,999 次重抽、區塊長度 20。3,960 筆呼叫都有 `seed`（31 個不同值：依公式「基礎值＋呼叫鍵雜湊」，同一呼叫位置的種子在各案相同，符合設計）。Ollama 路徑會把 seed 寫入 `options.seed` | 固定 seed 不保證跨硬體或跨 Ollama 版本完全重現 |
| 8 | Temperature／context | **已核對** | 溫度：A/C/D 0.2、B 0.8，3,960 筆無例外；context 8192、timeout 600 秒，全部相同；`ollama_parallel=1`。最大輸出 tokens 為 1,333（上限 2048），沒有截斷 | — |
| 9 | Outcome（開盤進出、horizon） | **部分** | `case_results` 有 30/60/90 日 × zero/Corwin–Schultz × candidate/gated 共 12 種組合，每種 720 列（180 案 × 4 組）。進出場規則在 `backtest.py`，該檔包含在原始碼摘要內 | 本次沒有用行情重算任何一案的報酬與到期日 |
| 10 | Evaluation（candidate／post-gate、日面板、成本） | **部分** | 60 日、CS 成本、candidate：A 出手 141、正確 79（56.0%）；B 143／80（55.9%）；C 180／105（58.3%）；D 180／99（55.0%）。C、D 方向不同 16 案（只有 C 對 11、只有 D 對 5），雙尾精確 McNemar p≈0.21。買進／賣出數（C 145/35、D 137/43）與報告表相同。Gated 層 C、D 各有 1 案降為持有 | Sharpe、Ledoit–Wolf p、日期群聚區間沒有重算（需要日報酬面板與統計程式，而統計程式不在 hash 內） |
| 11 | Code commit／hash | **部分** | 映像 `sha256:fbd889ff…`，建立於 2026-10-02T05:20:38Z。9 個模組的原始碼摘要與提交 `eb36a8a` 至 HEAD 相同（工作樹的這 9 個檔也相同） | 映像沒有 git 標籤；摘要只涵蓋 9 個模組，`reporting.py`、`web/`、`scripts/` 的版本無法由 hash 證明 |
| 12 | 事前登記時間與變更紀錄 | **部分** | 登記 `frozen_at` 2026-10-02T05:35:33Z，早於第一個工作建立（05:35:39Z）與第一筆紀錄完成（05:36:11Z）；最後一筆完成於 2026-10-03T19:26:33Z。作廢登記（a3d65c6d、6be8da83、18bb53ca、706bc5ec）都在資料庫中，沒有混入 | `docs/e2prime-preregistration.md` 的 v3-1002.3 段落寫「登記時間與 hash 於登記後補上」，但沒有補上。執行中的網路中斷與續跑只記在記憶筆記，沒有正式的偏離說明 |
| 13 | Raw outputs 與 aggregation 一致 | **已核對** | 3,960 筆決策紀錄都有 `raw_response` 與 audit。A、C、D 的候選行動與 `case_results` 540/540 相符。B 的 180 案中有 1 案投票平手（持有 3、買進 3、賣出 1），依 `engine.py` 的規則取信心最高者為買進，與 `case_results` 相符。記憶：6,804 筆，全部屬於同一 hash、同一組，到期日都早於分析日（0 筆違規）；依程式，A/B 的提示詞不放記憶 | — |
| 14 | 研究者確認可列入新版正式 Results | **未核對** | — | 需要研究者明確同意，並決定第 1、2、9–12 項的缺口要補齊還是在報告中揭露 |

## 補充數字（可放入報告的資源附錄）

| 組 | 有效呼叫 | 邏輯呼叫（含重試） | 驗證重試 | 輸入 tokens | 輸出 tokens | 推理秒數 |
|---|---:|---:|---:|---:|---:|---:|
| A | 180 | 181 | 1 | 561,134 | 47,409 | 1,036 |
| B | 1,260 | 1,270 | 7 | 3,887,799 | 424,646 | 7,580 |
| C | 1,260 | 1,261 | 0 | 4,681,674 | 349,459 | 8,399 |
| D | 1,260 | 1,267 | 6 | 4,784,690 | 388,254 | 8,925 |

- D 每案的輸入 tokens 比 C 多約 2%、輸出多約 11%、推理時間多約 6%。「名目呼叫數相同」不等於計算量相同。
- 有無來源數字支持的敘述數字（`unsupported_numbers`）：275/3,960 次呼叫（6.9%）。
- B 有 2 次呼叫缺 usage；研究代理人的 180 筆（基本面，未呼叫模型）沒有 usage，屬預期情況。

## 升格前建議的最小補件

1. 在事前登記文件新增「偏離說明／登記補記」，寫入 `b1da80ee…`、`frozen_at`、映像 id、source digest `6ea81119…`、Ollama 0.35.0、GPU 執行個體，以及執行中斷與續跑的紀錄。只追加，不改原文。
2. 用凍結的映像，在唯讀資料庫副本上重跑 `study_report`，核對 Sharpe、LW p 與群聚區間。
3. 由研究者在 README 的決策表簽核第 14 項。
