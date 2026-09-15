# 版本紀錄

正式產品只有一條執行路徑：`research.ps1` → Docker Compose → `research_service` → `http://127.0.0.1:8000`。每個協議版本變更都會產生新的 protocol hash；舊版工作保留為可稽核紀錄，但不可續跑，也不能與新版本合併統計。

## v3-0913.1（後續，2026-09-16）— 清除已被取代的隱藏 GUI 子系統

不改變決策提示或可引用證據，因此不升版。

- 拿掉「設定資料來源與模型」摺疊選單的綠色標題，改用跟其他次要摺疊選單一致的灰色。
- 徹底移除兩套改版後已被新版編號導覽列取代、但被 CSS 焊死看不到（`display:none!important`）的舊系統：狀態橫幅（`.mode-banner`）與浮動狀態列（`.persistent-terminal` / `.terminal-next-action`，含「下一步該做什麼」提示與 CTA 按鈕）。兩者原本每次分頁切換、每次背景輪詢都會重新計算並寫入 DOM，使用者卻完全看不到。
- 模型連線狀態文字（`#model-state`）保留並搬到導覽列右側，改成一直看得到的樣子，不再依附在已刪除的浮動狀態列裡。
- 同時清掉更早一版就已經沒有任何 HTML 元素在用的殘留樣式（`.intro`、`.intro-actions`、`.top-status`、`.connection`、`.next-action`），以及對應的響應式版型規則。
- `app.js` 少了 `syncNextAction()`、`syncModeBanner()`、`placeTerminalWithResults()` 三個函式與其呼叫點；`renderAgentTerminal()` 不再重複寫入兩份輸出。

驗證：全新 build 後 106/106 Python 測試、10/10 JS 測試通過；瀏覽器實測確認導覽列跳轉、模型狀態文字顯示均正常，無 console 錯誤。

## v3-0913.1（後續，2026-09-15）— GUI 改為連續捲動流程，修正導覽失效

不改變決策提示或可引用證據，因此不升版。

- 網頁從「分頁切換＋巢狀子分頁」改為單頁連續捲動：頂端固定導覽列改成「1．資料準備 → 2．建立實驗 → 3．Agent 終端 → 4．統計結果」四個編號步驟，捲動時自動高亮目前所在區塊（`IntersectionObserver`），每個步驟內再細分子步驟編號（如 1.1／1.2／1.3）。
- **修正**：改版後導覽列按鈕變成純顯示用（`pointer-events:none`），點擊完全沒有反應，使用者只能自己手動捲動才找得到「建立實驗」或「統計結果」在哪裡。現在點擊會直接跳到對應區塊；捲動時的自動高亮與點擊跳轉互不干擾（不會互相打斷）。
- 資料集選擇預設列出最近 12 筆，並在第 1 步已選定股票／日期時自動帶入對應資料集，不用每次都手動搜尋。
- 資料完整度區塊直接內嵌可展開的「資料缺口清單」，逐案例列出缺少項目與可複製的補資料指令。
- 進階實驗選項（研究階段、B 組採樣）收進可折疊區塊，預設只看得到常用欄位。
- 模型連線失敗時的錯誤訊息區分 401/403/429/連線逾時，並明確標示「這不是 NoTrade」，避免被誤讀成正式的風控判斷。
- 清理 `TABS`／`syncModeBanner()` 裡殘留的舊版「即時觀察」分頁項目，避免跟已移除的 Finnhub 功能混淆。

## v3-0913.1（後續，2026-09-15）— 移除 Finnhub 即時觀察

不改變決策提示或可引用證據，因此不升版。

- 移除「即時觀察」分頁與其後端：`research_service/finnhub.py`、`research_service/live_stream.py`（WebSocket 成交串流）、`/api/live/*`、`/ws/live`、`research.ps1 live`／`watch` 指令、`FINNHUB_API_KEY` 等三個環境變數，以及對應的專屬測試。
- 理由：預設關閉（`RESEARCH_ENABLE_LIVE=false`），且功能本身與歷史回測快照刻意分開，不影響任何 A/B/C/D 實驗或統計結果；移除後介面與可維護的程式碼量更聚焦於這個專案的實際目的（歷史回測研究），不是即時交易輔助。
- 回測、資料蒐集、實驗執行、匯出、統計與 preregistration 的行為完全不變；106/106 Python 測試與 10/10 JS 測試通過。

## v3-0913.1（後續，2026-09-15）— 時間切分、資料缺口盤點與部署韌性

不改變決策提示或可引用證據，因此不升版；純屬操作與研究方法層的補強。

- 新增 Training（2021–2023）／Validation（2024）／Test（2025，凍結）三段時間切分（`research_service/splits.py`），依 `requested_analysis_date` 分類，即時（非季末）分析一律排除，不會混入任何切分統計。`research.ps1 splits` 查看、`create-temporal-split-plan.ps1` 產生可審查批次清單。
- 修正 `study_readiness()` 的計數錯誤：先前 `backtest_ready_cases`、`finbert_ready_cases` 等欄位會因為同一案例的「其他」領域缺資料而被連帶排除，即使該欄位本身其實已完成；現在各欄位各自獨立計數。
- 新增 `/api/readiness/gaps`（`research.ps1 gaps`）：列出每個未達正式門檻的案例、缺少的具體條件，以及可直接複製執行的補資料指令。
- 新增 `.\scripts\start-native.ps1`：Docker 不可用時的本機備援路徑，使用獨立的 `research-data-native`，不會讀寫 Docker 服務的資料庫。僅作復原／demo 用途；正式部署仍以 Docker 為準。
- `research.ps1 start` 改為等待 `/health` 通過才視為啟動完成；新增 `research.ps1 repair-docker`，在保留 `research-data` 具名 volume 的前提下自動修復 Docker Desktop 的 stale socket 問題。
- 網頁 API 讀取請求加上逾時與單次重試；寫入請求（建立實驗、下載資料、儲存設定）不自動重送，避免重複建立工作或快照。

## v3-0913.1（2026-09-13）— 本機 Alpha Vantage 新聞快取

- 情緒面新增第三個可用來源：本機 Alpha Vantage 新聞快取（`ALPHA_VANTAGE_NEWS_PATH`，或未設定時自動使用伺服器管理的 `research-data/alpha_vantage_cache/`）。`fetch_sentiment()` 依序檢查快取、FNSPID、即時 API，快取或 FNSPID 已提供的證據不會再重複打即時 API。
- 快取來源的 `alpha_vantage_cache_per_ticker_file` relevance basis 與既有的 `fnspid_per_ticker_file` 一樣視為可信的目標股票對應，計入新聞品質門檻的目標相關率。
- 因為這改變了哪些證據會進入報告（新增一個資料來源、調整了 Alpha Vantage 即時呼叫的觸發時機），依專案慣例升版；舊協議的完成結果不受影響，仍可稽核與匯出，但不與 `v3-0913.1` 合併統計。
- 網頁「設定資料來源與模型」新增「更新 Alpha Vantage 新聞快取」按鈕，可在伺服器背景執行與終端腳本相同的逐月抓取／checkpoint／當月覆寫邏輯，不需要終端機。

## v3-0912.1（2026-09-12）— 正式就緒、SEC 可比較證據與時間量測

- 資料狀態分成四域證據完整、SEC 基本面可比較、FinBERT／新聞品質、60 日主要回測與 90 日次要回測；`formal_experiment_ready` 不再等同於只有四域資料。
- 新採集的 SEC 資料建立同 concept、相近 duration 的同比數值；決策提示只接收可比較指標，舊版點時欄位需勾選敏感性覆寫才能使用。
- 新聞存在時預設要求目標公司提及率至少 50%，且所有標題完成固定版本 FinBERT 評分。
- 任一不存在的引用 ID 都會觸發模型重試，不再允許 80% 有效引用率放行。
- 自動行情下載視窗由 400 個日曆日延長為 900 日，使 60-session 非重疊基準能達到至少八窗。
- 執行時間改採服務端 monotonic clock 量測，不再把供應商回傳 duration 誤當 wall time。
- 最終審查：本機回測 demo 可交接（79/79 Python 測試通過，Docker 建置與健康檢查通過）；正式 180-case 論文實驗與公開 GitHub release 治理當時尚未完成。
- **2026-09-12（後續）**：移除舊版 Sites/Next 展示原型（`app/`、`lib/`、`db/`、`drizzle/`、`worker/`、Node/Vite/Cloudflare 設定），repo 只保留 `research_service` 這一條正式路徑；歷史 migration/review 文件併入本檔。

## v3-0909.7（2026-09-09）— 基本面點時欄位不再作為決策特徵

SEC XBRL 的單一營收、資產、負債、現金流與 `NetIncomeLoss` 欄位仍完整保留在四域研究報告、資料快照與匯出檔，但不再進入 A/B/C/D 的決策提示與可引用 ID 清單——這些點時數值沒有同口徑比較期、成長率或估值證據，不能支持「強營收」或價格方向的決策論述。決策改為只使用技術指標、目標公司新聞情緒與總經資料。

## v3-0909.6（2026-09-09）— 財務語意驗證的誤判修復

v3-0909.5 的規則會把新聞標題中的「AI infrastructure growth」誤判為財務趨勢用語並拒絕輸出。修正後檢查縮限為明確指向營收、現金流、資產、負債、淨利或基本面的品質與趨勢敘述；市場、產業與新聞所述的需求或基礎設施成長仍可使用。

## v3-0909.5（2026-09-09）— 數字格式化

源鎖定的 SEC 基本面 claim map 保持數值不變，只在報告顯示的整數前加上千分位逗號（例如 `Revenues = 91,166,000,000 USD`）；`claim_map` 與不可變資料集仍保留未格式化原值。

## v3-0909.4（2026-09-09）— 基本面改為 source-locked SEC 摘要器

基本面研究域改為只列出凍結輸入中每一筆點時 XBRL 欄位並註明缺少比較期，不再讓語言模型推論強弱、虧損、成長或價格影響。其餘三個研究域與 A/B/C/D 決策仍使用選定模型；報告記錄 `mode: source_locked` 與輸入雜湊。

## v3-0909.3（2026-09-09）— 拒絕未經比較的財務判斷

`NetIncomeLoss` 等 SEC XBRL 欄位是 taxonomy 欄位，不是虧損或獲利的陳述；原始數值在沒有比較基準時不能支持強弱、成長或財務壓力的判斷。違規輸出獲得一次審核重試，仍失敗則改用標示清楚的來源摘錄。

## v3-0909.2（2026-09-09）— 本機模型輸入精簡

針對本機 Ollama 的有限 context，模型提示改為緊湊摘要（校準數值、硬性基本面／技術／總經事實、四則代表性新聞標題），輸出預算限縮為 512 tokens。原始快照、報告、引用與匯出內容不變。

## v3-0909.1（2026-09-09）— 新協議欄位與 pilot gate

新增 `switch_isolation`、`target_context_priority`、`citation_pass_floor`、`news_relevance_floor` 等協議欄位；`model_action`/`derived_action`/`candidate_action`/`action` 決策欄位分層。新增 `case_results` 索引表與 `/api/studies/{protocol_hash}/pilot`、`/hold-band` 檢查端點。

## v3-0908.2（2026-09-08）— 本機回測修正版

基本面摘要只允許引用證據中存在的數值，禁止換算或自行四捨五入；引用不存在的 ID 會使該步失敗並可重試。情緒研究保留跨公司新聞作為脈絡，但須清楚標示被提及公司非目標公司。交付包不含金鑰、資料庫、原始新聞、模型與舊 Node 原型。

## v3-0907.2（2026-09-07）— 最終審查基準

本機研究操作可用，38 項 Python 測試通過；正式 200-case 實驗、公開 GitHub 發布與多人公開服務尚未開始。舊版 Sites/Next 原型當時因 `npm audit` 有 4 個 high severity 相依問題，被列為不宜發布（該原型已於 v3-0912.1 後移除）。

## v3-0905（2026-09-05）— 正式版需求基準

依「多代理人立場交換辯論機制」計劃書訂定正式版驗收規格：不可變 protocol、四域研究 Agent、A/B/C/D（1/7/7/7）、分輪立場交換與資訊隔離、真實資料來源、Gatekeeper、完整回測、配對統計檢定（McNemar、Jobson–Korkie、block bootstrap）等。此規格為後續所有版本的需求依據。
