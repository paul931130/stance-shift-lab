# 正式實驗與公開發布最終審查

更新日期：2026-09-07

本審查以 v3 計劃書為需求基準，檢查 FastAPI 正式服務、研究資料、A/B/C/D 實驗、統計、網頁、Agent CLI、Docker 與 GitHub 發布準備。結論是：**目前版本已適合本機操作與小規模 pilot；尚未達到正式 200-case 實驗、公開原始碼首發或多人公開服務的完成條件。**

## 目前可確認的狀態

| 目標 | 狀態 | 證據與界線 |
| --- | --- | --- |
| 本機研究操作 | 可用 | `http://127.0.0.1:8000` 回傳 `v3-0907.2`；Docker、SQLite、網頁及 PowerShell CLI 已可操作 |
| 正式服務測試 | 通過 | 38 項 Python 測試通過，JavaScript 語法通過，映像內 `pip check` 無破損相依 |
| 舊 Sites/Next 回歸 | 通過但不宜發布 | 生產建置、ESLint 與 18 項測試通過；但 `npm audit --omit=dev` 發現 4 個 high severity 相依問題 |
| 真實資料試跑 | 部分完成 | 12 個歷史資料快照，只涵蓋 AAPL、NVDA；目前 3 個完成 run、2 個不同完成 case、2 種協議、1 個模型 |
| 正式 200 cases | 未執行 | 尚不能報告績效或顯著性，也不能宣稱立場交換優於控制組 |
| 公開 GitHub | 未完成 | 工作樹有 20 個修改、27 個未追蹤項目，沒有 remote、LICENSE、CI、Python package metadata 或 release tag |
| 公開多人網站 | 未設計完成 | 現有驗證是單一研究室共用憑證，沒有使用者隔離、配額、憑證庫或刪除機制 |

## 排序方法

- **P0**：執行正式研究或公開發布前必須完成；未完成會使研究結論無法解釋、造成資料授權問題，或暴露已知高風險依賴。
- **P1**：進入 200-case 批次或公開 beta 前完成；主要影響可重現性、成本、失敗恢復及服務可靠性。
- **P2**：正式 GitHub release 應完成；主要影響安裝體驗、維護、審查與專業度。
- **P3**：不阻擋研究，但會改善長期使用與展示品質。
- 影響分為 **極高、高、中、低**；工作量以目前單人專題規模估計為 **小、中、大**。

## P0 正式實驗與公開發布阻斷項

| 排名 | 改善項目 | 影響 | 現況與風險 | 完成標準 | 工作量 |
| ---: | --- | --- | --- | --- | --- |
| 1 | 凍結主要研究問題與 estimand | 極高 | 計劃書同時出現 B=5、約 6 次與程式 B=7；尚未正式指定 D 對 C 或 D 對所有控制組、候選決策或 Gatekeeper 後決策、零成本或成本後結果何者是主分析 | 一份不可修改的 preregistration 明列主要假設、主要比較、B=7、主要 60 日成本模型、效果量、排除與停止規則；其他設定只作敏感性分析 | 小至中 |
| 2 | 分開「研究股票池」與「上線可查股票池」 | 極高 | 程式固定 10 檔且包含 ASTS，但目前 FNSPID 只有 9 檔；使用者又決定本階段先不跑 ASTS。現在 `TICKERS` 同時限制回測與產品查詢，既無法形成宣稱的 200 cases，也無法讓上線版查一般 ticker | 明確選擇 9×20=180、補足第 10 檔，或取得 ASTS 完整資料；另建 `STUDY_UNIVERSE` 與可擴充的 ticker/CIK resolver | 中 |
| 3 | 建立不可變的 study manifest | 極高 | 現行統計對同 ticker/date 自動採「最新完成重跑」，看過結果後重跑可能造成選擇偏誤；也沒有固定 200 個 dataset ID 與 run ID 的清單 | manifest 鎖定 case、dataset hash、run ordinal、模型、協議、程式 commit；主分析採第一個有效 run，重跑需原因碼並另列敏感性結果 | 中 |
| 4 | 鎖定模型實體與每次抽樣種子 | 極高 | 只保存模型名稱；Ollama tag 和雲端 alias 可變，B 組沒有 per-call seed，因此可能得到重複樣本，也不能精確重播 | 保存 Ollama digest/量化/context、雲端 provider response metadata、模型版本、runtime 版本、run seed 與每個 call seed；seed 不寫進 prompt | 中 |
| 5 | 修正新聞公司相關性、時間與取樣 | 極高 | Alpha feed 即使沒有目標 ticker 的 relevance record 仍會收入；跨來源同篇文章可能重複；最新 12 筆會偏向單一來源；FNSPID 只有日期且缺 ASTS | 預註冊 relevance 門檻、ticker 必須匹配、canonical URL/標題去重、來源平衡與半開時間窗；保存原始時區、抓取時間、規則版本及人工抽查結果 | 中 |
| 6 | 標準化 SEC 財報事實語意 | 極高 | 每個 tag 只以最新 `end/filed` 選值，未限制 10-Q/10-K、FY/Q1/Q2/YTD、duration、frame、unit 與 amendment，可能把不同期間值放在同一摘要中比較 | 建立財報 fact selector；保存 form、fy、fp、start/end、filed、accepted、accn、unit、frame、duration 與選擇理由；為 10 檔人工核對至少兩個切點 | 中 |
| 7 | 建立資料 provenance 與可重建快照 | 極高 | dataset hash 可鎖目前內容，但沒有 request 參數、原始回應 hash、parser 版本、供應商版本與授權欄位；Yahoo 調整後行情可能隨公司行動回算 | 每個來源輸出 manifest、raw hash、request window、retrieved_at UTC、parser/schema version、license/terms；正式研究保存允許留存的原始回應或經驗證衍生檔 | 大 |
| 8 | 凍結回測與投資組合定義 | 極高 | 現況是下一交易日 open 進場、固定一單位多空、90 日 case 可重疊；基準是同一股票 active-window buy-and-hold，並非市場指數；未含借券、融資、稅與滑價 | 預先指定持倉規模、重疊部位、資金占用、再平衡、short 約束、風險無利率、交易成本與 SPY/產業 benchmark；輸出 alpha 與 turnover | 中至大 |
| 9 | 正式定義 Hold／NoTrade 的評分 | 極高 | 方向準確率排除 Hold 與 NoTrade，只在報表附 coverage；不同方法若棄權比例不同，條件式準確率會失真 | 同時報 coverage、selective accuracy/risk、NoTrade、Hold、錯失機會成本與預先指定效用；主檢定不能只條件化在雙方都交易的子樣本 | 中 |
| 10 | 補足同期相依與統計獨立驗證 | 極高 | Sharpe 已有日期區塊 bootstrap，但方向 McNemar 仍把同期股票視為獨立；固定 block=20 未做敏感性；現行 Ledoit-Wolf 實作尚未與獨立套件或論文數值例交叉驗證 | 對方向結果加入日期 cluster/permutation 或 block sensitivity；驗證統計公式、有效樣本、Holm family、block 長度 10/20/40；先做 power 或 simulation | 中 |
| 11 | 分層報告機制輸出與 Gatekeeper 輸出 | 高 | Gatekeeper 可把 Buy/Sell 降為 Hold；歷史準確率目前只警告、不改決策。若只看 gate 後績效，無法辨認差異來自辯論或風控 | 主機制分析用 `candidate_action`，安全部署分析用 final action；分開報 gate 原因、校準曲線、歷史警示與恢復規則 | 中 |
| 12 | 先通過 pilot gate 再排 200 cases | 高 | 現在只有 2 個不同完成 case、1 個模型，無法估算逾時、降級、token、成本或資料缺口分布 | 先完成 2 檔×4 日期×A/B/C/D，零未解釋錯誤；人工抽查所有來源，產生 coverage、失敗率、token、時間與統計資料形狀報告 | 中 |
| 13 | 將正式 FastAPI 與舊 Next/Sites 原型分離 | 極高 | 根目錄同時有兩個產品、兩套設定與兩條部署路徑；`.openai/hosting.json`、Node app 與 Python 正式服務容易讓使用者啟動錯誤。舊 Node 依賴目前有 4 個 high severity 問題 | 正式 repo 只留 FastAPI 產品；舊版移至 `legacy-sites` branch 或獨立 repo。若仍發布舊版，先升級並重新通過 audit | 中 |
| 14 | 完成資料與程式授權決策 | 極高 | 專案沒有 LICENSE；FNSPID 的 README 與 LICENSE 對商業權利說法不一致；Yahoo/yfinance 與 Alpha Vantage 對使用範圍有限制；FRED 有指定顯示文字 | 選定程式碼 license，加入 LICENSE/NOTICE/DATA_SOURCES；不發布原始新聞與行情；顯示 FRED 必要聲明；公開服務前逐一確認供應商權利 | 小至中 |
| 15 | 建立乾淨、可驗證的首個 release | 極高 | 目前 47 個工作樹變更、沒有 remote、CI、tag 或 release artifact，不能證明 GitHub 上的版本與本機已測版本相同 | 整理提交、secret/history scan、GitHub Actions、乾淨 clone smoke、簽名 tag、release notes、Docker image digest；公開後再從 remote 重裝驗證 | 中 |

## P1 批次研究與公開 beta 前完成

| 排名 | 改善項目 | 影響 | 具體作法 | 工作量 |
| ---: | --- | --- | --- | --- |
| 16 | 強制資料集日期一致 | 高 | 自動下載的資料集只能用於其 `requested_analysis_date`；通用匯入資料另設明確模式。目前後端允許同 ticker 搭配另一季末日期，新聞 90 日窗會錯位 | 小 |
| 17 | Provider registry 與 model preflight | 高 | 以單一 catalog 管理 provider、模型 ID、context、structured output、reasoning、key 名稱與 endpoint；建立工作前做最小 schema call | 中 |
| 18 | 重試、退避、流量與成本控制 | 高 | 對 429/5xx/timeout 做有上限的 exponential backoff；記錄每次 attempt、延遲、token、費用；每 run/batch 設 token、金額與時間上限 | 中 |
| 19 | 真正取消與冪等 | 高 | 現有取消只在波次後生效；應向可取消 provider 傳遞 cancel，停止後續波次，並以 request/call ID 避免恢復時重複計費 | 中 |
| 20 | 200-case 排程器與 dry run | 高 | 現有單一工作執行緒會逐案處理；加入資源感知佇列、provider rate bucket、預估完成時間、dry run、失敗重排與批次摘要 | 中至大 |
| 21 | 用 token、時間與金額做 compute matching | 高 | B=7 只對齊呼叫數；D 的上下文較長。每組報 prompt/completion tokens、wall time、費用，主分析採 token budget 對齊或做敏感性分析 | 中 |
| 22 | 建立 Study 2 跨模型彙總 | 高 | 先在每個模型內做 D vs A/B/C，再以模型分層或階層模型彙總；保留模型別效果與異質性，不直接混在同一 protocol hash | 中 |
| 23 | 把失敗與 degraded 視為 attrition | 高 | 依模型、領域、股票與組別報 timeout、重試、fallback、排除比例；預先指定排除規則並做 best/worst-case sensitivity | 小至中 |
| 24 | 分開「固定回測實驗」與「一般查詢」 | 高 | 回測模式維持固定股票、季末與無外部知識；上線查詢模式才能接受其他 ticker/日期與即時資料，且不得混入正式實驗統計 | 中至大 |
| 25 | 把情緒分類變成可重現管線 | 高 | 自動下載資料也要能選擇 frozen FinBERT；保存 revision/digest、tokenizer、輸入 hash與分數。遠端 HF 呼叫需批次、快取及部分失敗處理 | 中 |
| 26 | 為 FNSPID 建索引 | 中高 | 現在每個 case 都掃描整份 CSV；先轉 SQLite/Parquet 並以 ticker/date 建索引，200-case 取樣才不會重複掃檔 | 中 |
| 27 | 正式 artifact manifest 與 schema | 高 | ZIP 加入 `manifest.json`、每檔 SHA-256、JSON Schema 版本、程式 commit、模型與資料 provenance；提供 deterministic export 測試 | 中 |
| 28 | 資料庫 migration、備份與還原 | 高 | SQLite 現在只有啟動時 `CREATE TABLE IF NOT EXISTS`；加入 schema version、migration、WAL-safe 備份、排程備份、還原演練與保留政策 | 中 |
| 29 | 公開服務登入與濫用防護 | 高 | 現有簽章 cookie 已不保存主金鑰，但仍需登入限流、session 撤銷/rotation、審計、工作配額、CSRF 測試、Caddy 限流與成本上限 | 中 |
| 30 | 多使用者 BYOK 設計 | 高 | 只有確定做多人服務時才加入網頁填 key；需帳號、每人加密憑證、tenant 隔離、秘密刪除、資料匯出、稽核與隱私政策 | 大 |
| 31 | 可觀測性與營運告警 | 中高 | 加入結構化 log、queue depth、provider latency/error、token/cost、DB/磁碟、備份年齡與健康告警；不得記錄 API key 或完整敏感提示 | 中 |
| 32 | 技術面與總經面特徵規格 | 中高 | 技術面目前只有 return20、SMA20/60、vol60 且沒有 volume；總經只有 FEDFUNDS/CPI/UNRATE。預先指定指標、發布延遲、單位與正規化方法 | 中 |

## P2 GitHub 專案品質與操作體驗

| 排名 | 改善項目 | 影響 | 具體作法 | 工作量 |
| ---: | --- | --- | --- | --- |
| 33 | Python package 與跨平台 CLI | 中高 | 新增 `pyproject.toml` 與 console script，例如 `stance-shift setup/doctor/collect/run/status`；PowerShell 保留為 Windows wrapper，Linux/macOS 使用相同 CLI | 中 |
| 34 | 單一設定入口 | 中高 | 正式 repo 只留一份 `.env.example` 與一份 Compose；用 typed settings 驗證布林、URL、模型、workers 與 secret；正確處理空白和特殊字元 | 中 |
| 35 | GitHub CI gate | 中高 | 參考 TradingAgents：Python 支援矩陣、pytest、ruff、clean-install import；再加 Docker build、Compose config、JavaScript syntax、secret scan 與最小 E2E | 中 |
| 36 | SemVer、CHANGELOG 與 protocol/schema 分版 | 中 | 區分 app version、study protocol version、dataset schema、parser version；建立 CHANGELOG、migration notes、signed tag 與 release notes | 小至中 |
| 37 | 社群與研究檔案 | 中 | 加入 CONTRIBUTING、SECURITY、CODE_OF_CONDUCT、CITATION.cff、issue/PR templates、authors/acknowledgments；說明如何引用計劃書或論文 | 小 |
| 38 | 供應鏈安全 | 中高 | Dependabot/Renovate、pip-audit、npm audit（若仍保留 Node）、CodeQL、container scan、SBOM、GHCR image、base image digest 與 release provenance | 中 |
| 39 | Docker production hardening | 中 | 加 `read_only`、`no-new-privileges`、cap drop、tmpfs、resource limits、health start period；資料 volume 與輸入目錄維持最小權限 | 小至中 |
| 40 | README 發布頁重整 | 中 | 增加架構圖、短 GIF/截圖、三分鐘 quickstart、CLI/網頁兩種路徑、研究與一般模式、輸出範例、限制、可重現性、引用與 roadmap | 中 |
| 41 | 移除個人絕對路徑與過期狀態 | 中 | `docs/quickstart-v3.md` 與 `research-inputs/README.md` 仍含 `C:\Users\paul9\...`；文件測試數與「正在接入」文字也有版本漂移 | 小 |
| 42 | 改善前端更新機制 | 中 | 現在每 5 秒持續打 `/api/dashboard`，即使沒有執行中工作；改用 SSE/WebSocket，或只在 active job 自適應輪詢並於背景分頁暫停 | 中 |
| 43 | 讓資料 Agent 顯示真實串流 | 中 | 目前資料下載 API 完成後才一次回傳四域結果；改成背景 collection job，逐域保存進度、錯誤、retry 與 cache hit | 中 |
| 44 | 模型與批次預算畫面 | 中 | 模型選擇改為 provider→model；顯示可用 key、context、估計 calls/tokens/時間/費用；200-case 匯入先預覽再確認 | 中 |
| 45 | 資料集與工作管理 | 中 | 加別名、完整 ID 複製、來源/日期/模型/狀態篩選、封存、刪除與空間使用量；不要只列最近 5 個資料集 | 中 |
| 46 | 統計結果的可讀圖表 | 中 | 加 coverage-vs-accuracy、各組 paired difference、信賴區間、NoTrade/Hold、成本敏感性、失敗率與資料缺口圖；保留原始 JSON/CSV | 中 |
| 47 | API 版本與開發者介面 | 中 | 提供 `/api/v1`、OpenAPI 下載、JSON Schema、錯誤碼、pagination、ETag 與 batch idempotency key；正式環境可關互動 docs | 中 |
| 48 | 瀏覽器與無障礙 E2E | 中 | 用 Playwright 驗證登入、建立資料、日期鎖定、run、暫停/恢復、匯出與手機版；加入鍵盤、焦點、表格 caption、對比與 screen-reader 測試 | 中 |

## P3 長期維護與展示

| 排名 | 改善項目 | 影響 | 具體作法 | 工作量 |
| ---: | --- | --- | --- | --- |
| 49 | 中英文介面與文件 | 低至中 | 內部 prompt 語言、輸出語言與 UI 語言分開設定；正式研究須鎖定輸出語言並納入 protocol | 中 |
| 50 | 結果比較工作區 | 中 | 允許選兩個 run 並排比較 report hash、模型、token、決策、gate 與回測差異 | 中 |
| 51 | 可分享的去識別研究報告 | 中 | 產生不含 key、本機路徑與受限制全文的 HTML/PDF；附 manifest、限制與引用 | 中 |
| 52 | 儲存空間生命週期 | 低至中 | 顯示 volume 用量，設定 raw cache、dataset、run、export 的保留與清理規則；刪除前提供備份 | 中 |
| 53 | 故障注入與長跑測試 | 中 | 模擬斷網、429、模型格式錯誤、程序重啟、磁碟滿、DB lock 與 200-case 長時間執行 | 中 |
| 54 | `.gitattributes` 與編碼規範 | 低至中 | 固定 LF/CRLF 與 UTF-8；PowerShell 5 所需 BOM 例外化，消除目前 Git 行尾警告 | 小 |

## TradingAgents 發布方式對照

[TradingAgents](https://github.com/TauricResearch/TradingAgents) 目前把核心套件、CLI、測試、Docker、範例環境變數、版本紀錄與授權放在單一 Python 專案。它的 `pyproject.toml` 宣告可安裝套件及 `tradingagents` console command；CI 會測 Python 3.10–3.13、乾淨安裝與 Ruff；README 另列 Docker、持久化、checkpoint resume、可重現性、研究用途限制與引用；CHANGELOG 和 GitHub Releases 使用 SemVer 記錄修正。

本專案應採用相同的發布骨架，但保留自己的研究差異：不可變 dataset、決策前中立報告、A/B/C/D 公平比較、角色交換、Gatekeeper 分層輸出與配對統計。不要複製 TradingAgents 的產品敘事來宣稱交易績效；它的後續版本也曾專門修正 FRED、新聞、記憶與價格的 look-ahead 問題，這些問題應在本專案正式跑實驗前先封鎖。

建議正式 repo 結構：

```text
stance-shift-research/
├─ pyproject.toml
├─ src/stance_shift/          # API、engine、data、models、statistics
├─ src/stance_shift/web/      # 正式網頁靜態檔
├─ tests/
├─ docs/
├─ scripts/
├─ research-inputs/README.md  # 只留下載與整理說明
├─ deploy/
├─ .github/workflows/ci.yml
├─ Dockerfile
├─ compose.yaml
├─ .env.example
├─ LICENSE
├─ NOTICE
├─ CITATION.cff
├─ CHANGELOG.md
└─ README.md
```

舊 `app/`、`lib/`、`db/`、`worker/`、`.openai/hosting.json`、Node package 與 Cloudflare 設定移入獨立 `legacy-sites` branch 或另一個 archive repo，不和正式 Python 產品一起發布。

## 資料授權與發布注意

- [yfinance 文件](https://ranaroussi.github.io/yfinance/index.html) 明示工具供研究教育使用，Yahoo 資料權利仍受 Yahoo 條款限制，且提到 API 是個人使用；公開 repo 只發布 downloader，不發布下載後行情。
- [Alpha Vantage 條款](https://www.alphavantage.co/terms_of_service/) 把個人、非商業研究與提供他人存取的服務分開；多人公開服務前需確認方案與授權。
- [FRED API 條款](https://fred.stlouisfed.org/docs/api/terms_of_use.html) 要求公開應用顯示指定的非背書聲明，並提醒部分 series 有第三方權利。
- [SEC API 文件](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) 要求遵守自動存取政策；應保留可聯絡 User-Agent、全域速率限制與快取。
- FNSPID 官方 repo 的 [LICENSE](https://github.com/Zdong104/FNSPID_Financial_News_Dataset/blob/main/LICENSE) 仍是 CC BY-NC 4.0，但其 README 又寫出較寬鬆的權利聲明。兩者未正式釐清前，最安全作法仍是讓使用者自行下載，repo 不散布 CSV，並在 DATA_SOURCES 記錄版本、引用與限制。

## 建議執行順序

1. **先鎖研究規格**：完成排名 1–4、8–11，產生 preregistration 與 study manifest schema。
2. **修資料選擇**：完成排名 5–7、16、25、26，重建並人工抽查兩個資料集。
3. **跑 pilot**：2 檔×4 日期，驗證 coverage、失敗、token、費用、候選與 gate 後輸出。
4. **整理單一正式 repo**：完成排名 13–15、33–41，從乾淨 clone 再跑所有測試。
5. **才跑正式批次**：凍結 manifest 後執行 Study 1；完成、封存與分析後，再跑 Study 2。
6. **最後公開服務**：先處理供應商權利、安全、配額、備份與監控，再以 HTTPS 網域驗收。

## 發布判定

- **現在可以做**：本機展示、資料流程驗證、單 case 測試、pilot、程式碼整理。
- **完成 P0 實驗項後可以做**：凍結並執行正式 Study 1。
- **完成 P0 發布項後可以做**：建立公開 GitHub repository 與第一個 pre-release。
- **完成 P1 安全與授權項後可以做**：部署單一研究室 beta。
- **完成多使用者隔離後才可以做**：讓訪客在網頁輸入自己的模型或資料來源金鑰。

本審查不把通過測試、兩個完成案例或合成 fixture 當成研究績效證據。正式結論只能來自事先凍結、資料完整且未經結果導向挑選的正式樣本。
