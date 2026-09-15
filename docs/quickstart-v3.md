# v3 正式研究台

入口為專案根目錄的 **start-research.cmd**。啟動後開啟 http://127.0.0.1:8000 。這是 FastAPI / Uvicorn 正式服務，不使用開發熱更新。

介面分成三個分頁：**操作台｜準備與啟動**（資料來源、資料集、實驗表單）、**監控台｜進度與結果**（Agent 終端、研究佇列、實驗詳情）、**統計報告**（同協議統計、凍結樣本）。目前分頁與檢視中的實驗都會反映在網址列（`?tab=`、`?selected=`），可重新整理或收藏。

## 本機操作

1. 開啟 Ollama，確認已有 `qwen3:14b` 或其他 14B 以上模型。14B 以下模型只能勾選明確的冒煙測試覆寫，不能作為研究比較結果。
2. 雙擊 `start-research.cmd`。啟動檔會優先以 Docker Compose 建置、啟動服務並開啟瀏覽器；沒有 Docker 時才使用 Python 3.12 以上的 `.venv` 備援。
3. 左側選股票與分析日，按「啟動資料 Agent」。技術、基本面、情緒與總經 Agent 會同時連線來源，主畫面的 Agent Shell 會顯示真實派工、筆數與保存結果。若同股票、同分析日已有四域完整快照，預設直接重用且不呼叫外部 API；勾選「強制重新呼叫」才建立新版。情緒 Agent 會自動讀取 Alpha Vantage `NEWS_SENTIMENT` 及／或本機 FNSPID CSV，兩者皆未設定時才保留為資料缺口。系統先使用 yfinance，若其 `query2` 端點失效則改用 Yahoo `query1` Chart API，並將實際下載路徑寫入資料集限制。
4. 四張 Agent 卡會分別顯示完成、未設定來源、待補資料或失敗。展開「資料來源與模型憑證」可查看設定狀態並按「實機檢查新聞來源」。行情與格式驗證通過後即可啟動實驗；缺少領域可選「實驗對照」保留模型決策，或另選保守門檻強制 NoTrade。
5. 選資料集、模型與分析日，開始四組實驗。四個研究 Agent 先以同一資料快照並行產生中立摘要，鎖定報告後，A/B/C/D 依相依關係以波次並行；C/D 同輪兩方仍看不到對方當輪輸出。
6. 在佇列點「檢視」，可直接查看四個研究 Agent、A/B/C/D 各組進度、最終決策比較與 30/60/90 日成本後回測表，並下載 ZIP。
7. 完成後點「檢視同協議統計」，下載 summary.csv 與 statistics.json。Pilot 通過、準備凍結樣本時，按「凍結目前的 preregistration」；系統會記錄當下這個協議分析過的資料集清單。凍結是一次性動作，之後若又對同協議建立了新資料集的實驗，統計頁會標示「凍結後新增」，避免看完結果後偷偷擴大樣本。

同一股票與資料類型會依建立順序標成 v1、v2……；下拉選單分開顯示「研究分析日」與「未來行情終點」。分析日依計劃書限定為 2021–2025 季末；例如研究日 2025-12-31、行情終點 2026-08-07 時，08/07 只供分析日後 30/60/90 交易日回測，不能選為分析日。選取後會展開完整 SHA-256 ID、行情範圍、建立時間、來源、證據數及曾使用的分析切點。版本序號供人辨識，完整 ID 供稽核與批次設定使用。

模型欄位會列出目前 Ollama 已安裝的模型，也可在「雲端模型」欄位直接輸入 LiteLLM 模型名稱，例如 `openrouter/openai/gpt-4.1-mini`。雲端欄位有值時會覆蓋 Ollama 下拉選擇。模型會寫入該實驗的不可變協議；已排程、執行中或已完成的實驗不可中途換模型。比較另一個模型時請建立新實驗，並依研究設計選擇 Study 2。

API 金鑰與設定檔位於專案根目錄的 `.env.research`（執行 `.\research.ps1 setup` 會自動建立）。可直接填入下列欄位，儲存後重新啟動服務。`SEC_USER_AGENT` 是 SEC 要求的研究名稱與可聯絡 email，不是金鑰；完整值不會顯示在介面。

```text
SEC_USER_AGENT=研究名稱 contact@example.com
FRED_API_KEY=你的_FRED_API_KEY
ALPHA_VANTAGE_API_KEY=你的_ALPHA_VANTAGE_API_KEY
FNSPID_NEWS_PATH=/app/research-inputs/Stock_news.csv
OPENROUTER_API_KEY=你的_OPENROUTER_API_KEY
```

Alpha Vantage 使用官方 `NEWS_SENTIMENT` 端點，查詢分析日前 90 天且排除分析日當天的新聞。FNSPID 原始 `Stock_news.csv` 很大，先將它放成 `research-inputs\Stock_news_full.csv`，再執行下列命令串流篩出研究股票與期間；整理器只保留日期、股票、標題、網址與出版社，因正式情緒證據使用標題而不需要全文。處理完成後設定上述容器路徑。Docker 服務會以唯讀方式掛載結果。可參考 [Alpha Vantage 官方文件](https://www.alphavantage.co/documentation/)、[FNSPID 官方儲存庫](https://github.com/Zdong104/FNSPID_Financial_News_Dataset) 與 [FNSPID 資料頁](https://huggingface.co/datasets/Zihan1004/FNSPID)。

**FNSPID 只到 2023-12-31**：上游專案已於 2025 年停止維護，資料集本身就不含 2024／2025 年的新聞，重新下載也無法補齊。2024-03-31 以後的分析日只能靠 Alpha Vantage 補情緒域證據。免費版 Alpha Vantage 有每日額度限制，180 組合通常無法在同一天完成；可用 `scripts/collect-quarters.ps1` 批次收集完整 9 檔 × 20 季。腳本預設執行本機 FinBERT、按季度交錯股票，會在額度用完前自動停止並把進度存進 `work/collect-quarters-checkpoint.json`，之後重跑同一指令即可從中斷處繼續：

```powershell
.\scripts\collect-quarters.ps1
.\scripts\collect-quarters.ps1 -DailyBudget 5   # 額度較保守時
```

不想用終端機的話，網頁「設定資料來源與模型」展開後有「更新 Alpha Vantage 新聞快取」按鈕，會在伺服器背景執行同一套邏輯（9 檔 × 逐月，當月自動覆寫更新），額度用完會自動停止，進度存在伺服器的 `research-data/alpha_vantage_cache/`（Docker 具名資料卷內，重啟不會消失），按鈕下方會即時顯示目前處理到哪個股票／月份。這個快取只要存在就會被 `fetch_sentiment()` 自動優先讀取，不需要另外設定 `ALPHA_VANTAGE_NEWS_PATH`。

Windows 使用者也可用統一終端入口：`.\research.ps1 setup` 設定憑證、`.\research.ps1 doctor` 檢查服務、`.\research.ps1 collect NVDA 2024-12-31` 取得資料、`.\research.ps1 run NVDA 2024-12-31` 以預設 14B 模型啟動實驗。小模型只用於流程檢查，例如 `.\research.ps1 run NVDA 2024-12-31 -Model ollama/qwen3:8b -AllowSmallModel`。

在專案根目錄執行（PowerShell 用 `${PWD}`，Bash 用 `$(pwd)`）：

```powershell
docker run --rm -v "${PWD}/research-inputs:/inputs" stance-shift-lab-research python scripts/prepare_fnspid_news.py /inputs/Stock_news_full.csv /inputs/Stock_news.csv
```

勾選 FinBERT 時，系統在本機以固定版本的 `ProsusAI/finbert` 離線分析 sentiment 證據的新聞標題，產生 positive/neutral/negative 機率與正負差分並寫回資料集；首次使用會下載並快取模型，之後不需要 `HF_TOKEN` 或網路。評分結果會保存模型版本、輸入雜湊與處理參數，只有全部指定標題成功才建立新的資料集版本。雲端模型依 LiteLLM 的模型名稱使用對應金鑰，例如 OpenRouter 使用 `OPENROUTER_API_KEY`。Ollama 推論不會載入 LiteLLM 或聯絡雲端模型。

## 研究協議

- 主設定 A/B/C/D = 1/7/7/7 次決策模型呼叫，四域研究呼叫另計。B 可切換為 5 次，但分開統計。
- B 採樣與 A 使用完全相同提示，不加入 sample 編號、不讀取先前投票。平票按候選信心最高者處理；信心再相同時採固定輸出順序。
- C/D 同輪兩方只見前輪歷史；D 第二輪交換，第三輪恢復。三輪後各有一次裁決。
- 中立報告在分流前鎖定。每步保存報告雜湊、提示雜湊、原始 JSON、token 使用量及時間。呼叫數相同不代表 token 完全相同。
- Study 1/2 均在各次比較內使用同一模型；Study 2 更換模型重跑，以不同 protocol hash 隔離。
- `allow_decision` 將缺少資料的案例標記為實驗對照並保留模型輸出；`force_no_trade` 保留原本的保守閘門。策略寫入不可變協議與 protocol hash，統計時不混合。
- 決策固定預測分析日後 60 個交易日：候選 Agent 必須在 Buy/Hold/Sell 中選擇；Buy/Sell 分別建立一單位多／空部位，有效證據互相衝突或接近零報酬時使用 Hold。NoTrade 只由 Gatekeeper 在「保守門檻」且資料缺失時強制產生；「實驗對照」會保留候選決策。Bull/Bear 辯論回合的 action 固定代表其被指派的 Buy/Sell 論證，最終選擇仍由 Adjudicator 決定。
- Gatekeeper 的歷史準確率低於 50% 時只留下警示，不再把後續 Buy/Sell 永久改成 Hold；低信心與極高波動仍會套用風險閘門，因此新成熟案例可以讓歷史準確率恢復。
- 股票代號匿名化不會完全移除公司名稱、產品與數值特徵，因此不能證明不存在訓練記憶污染。
- 長期記憶只使用同股票、同協議、同組別，且 60 日回測成熟日期早於本次分析日的完成案例；重跑不重複計數。

## 資料與回測口徑

所有研究證據與技術指標只使用 `available_at < analysis_date` 的資料；同日公告時間不明時保守排除。財報依 filing date 篩選；ALFRED 依切點前的 realtime vintage 取得。Yahoo 還原價格可能包含事後公司行動調整，不是不可變 vintage 行情，此限制會隨資料集保存。

在分析日之後第一個交易日的還原開盤價進場，第 30/60/90 個交易日收盤出場。Buy 為固定股數多頭，Sell 為固定股數空頭，Hold/NoTrade 不建立部位。回測期間不足時標為 pending。空頭權益不正時標為無效，不納入統計。

Corwin–Schultz 使用連續兩日 high/low 的非負價差估計；每側扣半價差，進場估計只用分析日前價格，出場依出場日價格估計。另保留零成本結果。此實作未作隔夜跳空調整與多日平滑，不包含稅費、借券費、融資、流動性衝擊或強制平倉。不能將這些結果稱為實盤可交易績效。

統計採每日等權「當天有效案例部位」組合；重疊案例視為不同部位，只計算有部位視窗的交易日。基準也是相同視窗的 Buy-and-Hold，並非跨 2021–2025 的連續指數持有。無風險利率明定為零。方向準確率只計 Buy/Sell；McNemar 只配對雙方皆有方向的案例，另顯示覆蓋數與 NoTrade 比例。30/90 日是穩健性分析，主要 60 日比較另提供 Holm 校正。

## 暫停、重啟與備份

暫停會等目前並行波次結束再停止。研究摘要 Agent 格式錯誤或逾時時，系統改用具證據編號的來源摘錄並標示為降級；該案例仍可完成個別檢視，但會從正式彙總統計排除，應以可正常完成摘要的模型重跑。決策 Agent 錯誤時，同波次已成功的輸出仍會保存；修正模型或連線後按「繼續」只重跑未完成項目。取消會保留紀錄但不允許續跑。意外中止中的外部呼叫可能需要重試，不能保證外部模型計費恰好一次。

Compose 將資料庫保存在 Docker 具名資料卷 `research-data`。請用 `.\research.ps1 backup -File .\demo-backup.zip` 建立 WAL-safe 一致性快照，不要在服務執行時直接複製 SQLite 主檔。備份只包含資料集與工作紀錄，不包含 `.env.research`、API key、本機模型或原始 CSV；需要時請在安全位置另外保存 `.env.research`。更改 `.env.research` 後需重新啟動。Uvicorn 使用單一程序，不可啟動多個服務共用資料目錄。程式支援 `RESEARCH_PARALLEL_WORKERS=1..8`；來源蒐集與雲端模型的獨立工作可並行，但本機 Ollama 的研究摘要與決策會依序排程，避免多個完整 CPU context 同時耗盡 Docker Desktop。GPU 或雲端環境可在實測資源後提高。工作流仍以相依波次安排四域與 A/B/C/D，C/D 僅在前一輪完成後前進。前端有執行中工作時每 3 秒以單一 dashboard 請求更新；閒置時改為每 30 秒，背景分頁暫停並在回到頁面後立即同步。

若頁面顯示無法連線 Yahoo，請確認是從檔案總管雙擊 `start-research.cmd` 啟動，且 Windows 防火牆或執行環境允許該 Python 程序連出 HTTPS。受限的 IDE／沙箱程序可能只能連 localhost，這種情況即使瀏覽器本身可上網，後端仍無法下載行情。

## 批次 180 案例

目前回測研究名單為 9 股票 × 2021–2025 每季末 20 日期，共 180 個案例。ASTS 保留給後續即時查詢，不納入目前歷史研究；每個 case 需先準備符合切點的資料集。

批次匯入格式：

```json
{"cases":[{"dataset_id":"已保存的資料集 ID","analysis_date":"2024-12-31","model":"ollama/qwen3:14b","voting_samples":7,"study":"study1","anonymize_ticker":false}]}
```

每批最多 200 筆，先全部驗證再排程。不同案例在佇列中序列執行，避免同時載入過多模型；每個案例內的 Agent 與 A/B/C/D 仍依上述規則並行。正式樣本尚未全部跑完前，介面不會產生預設的優越性結論。

## 驗證命令

```powershell
.venv\Scripts\python.exe -m unittest discover -s research_service/tests -v
node --check research_service/static/app.js
```

測試向量刻意使用 synthetic 標記，與實際行情案例分開。完整實跑紀錄與限制見後續驗收文件。
