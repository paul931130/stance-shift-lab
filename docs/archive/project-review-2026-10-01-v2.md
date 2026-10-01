# 專案完整 Review：最新版本複查（2026-10-01）

## 結論

專案已經能執行真實實驗，但「能跑完」與「輸出可作為正式研究結果」仍有差距。最新版本修復了多個上輪問題，本次不沿用已修問題作為現況；仍確認數字驗證與 worker 寫入隔離兩個 P1 缺口。另有歷史回測統計未重算、月度就緒度不一致、模型身份未在執行／續跑重新核對等問題。

建議先停止擴大正式樣本，處理 P1、增加反例測試，再按新協議登記。這是建議，不是本次操作：本次沒有排入、暫停、取消實驗，沒有啟停 GPU，也沒有修改實作或提交 Git。

## 範圍與版本

- 主要專案：`C:/Users/paul9/Desktop/114-2/專題/stance-shift-lab`。外層 legacy、封存副本不是這次的現行實作，不將它們的結果混入本次評估。
- HEAD 起始 `369786ab82768a973622a97dba88d5590432993e`，末次確認 `6d298ecda2e070744522f4932f1ccc28a2df5089`。後者只更新 E2′ 登記紀錄；未提交資料與工具保留原樣。
- 現行季度 `v3-1001.1`，月度 `v3-1001.2`。
- :8003 部署映像 `stance-shift-lab-research-qwen:v3-1001.1`，實際 image ID `sha256:aa0748e5eabf7a510d933ccc20503103911d9429466f163068c6deafa25b4a46`。
- 閱讀現行程式、測試、README、方法與登記文件；正式 DB 只用 SQLite `mode=ro`。額外反例使用隔離容器／臨時 DB，不對正式 DB 寫入。
- 此文件獨立於上一份 review，保留上一份作為當時版本的歷史紀錄。

## 問題清單

### F1 [P1] 短 quote 與跨欄位位置錯誤，仍能讓錯誤數字主張通過

位置：`research_service/models.py:285-304,331-374`。

嚴格版只檢查 claim.quote，不檢查數字在原敘述中的完整上下文。來源為 Revenue / 2024-12-31 / USD / 100 時，已重現：

| 敘述／引用方式 | strict=True 結果 |
|---|---|
| `Revenue was 100 billion USD.`，quote 為完整句子 | 拒絕（此舊反例已修） |
| 同一句，quote 只填 `100` | 通過 |
| `Net income was 100 USD.`，quote 只填 `100` | 通過 |
| `Revenue was 100 EUR.`，quote 為完整句子 | 通過 |
| rationale 有合法長 quote，risks 另寫 `Fabricated value is 100.` | 通過 |

跨欄位問題來自 `text.find(quote)` 回傳 -1，卻仍參與覆蓋範圍判斷（370-371）。幣別問題來自只區分百分比／非百分比，沒有核對 USD 與 EUR。短 quote 可避開現有指標與尺度字詞檢查。

影響：新版的數字驗證尚不能保證自然語言事實正確，且最後移除數字不等於原決策沒有受到錯誤事實影響。

建議：主張要綁到指定欄位、指定出現位置與完整語句；不存在 quote 必須拒絕。對指標、期間、幣別、倍數使用可驗證的模板／結構化渲染，不能只依靠模型任選引用片段。增加上表全部負向測試。修改此規則會影響研究協議，正在跑的版本不能悄悄套新規則。

### F2 [P1] 舊 worker 可在工作被接管後覆寫新 worker 狀態

位置：`research_service/app.py:135,143`、`research_service/storage.py:257-292,321-343`。

背景 worker claim 有 owner，但 save_step 未傳 owner；失敗保存也是相同問題。Store 只有 owner 非空時才驗證租約。暫停立即把 status 改為 paused，但模型呼叫可能仍未結束；此時工作可被另一服務／CLI 接管。

臨時 DB 已重現：worker:old claim → pause → resume → worker:new claim → old worker 用 app 相同的 ownerless save_step 保存。結果新 owner 被清掉，工作變 complete，狀態內容被 old-worker-result 覆蓋。

影響：暫停／續跑、多服務或 CLI 接管時，可能覆寫較新檢查點與稽核紀錄，並把舊結果納入 case_results。這是已重現的可達路徑，不代表目前正式 DB 已發生此損壞。

建議：所有 worker checkpoint 寫入使用 owner／generation 的 compare-and-swap，拒絕失去執行權的寫入；避免模型呼叫未返回時接管 paused 工作。須保留 web worker 每步釋放回 queued 的流程，不能直接套 CLI owner 分支而造成工作停在 running。補跨 worker、CLI 接管、模型呼叫中 pause/resume 與失敗寫入測試。

### F3 [P2] 新回測已修，但舊報告仍使用修正前的 daily path

位置：`research_service/backtest.py:64-80`、`research_service/reporting.py:130-195`、`report/stance-shift-ssrn.tex:450-486`。

現行回測中間標記已改為 open，修正上輪時點問題；然而 reporting 讀的是 state.daily，並不自動重算歷史結果。正式資料庫中的舊 180 案仍保留舊路徑。

本次以相同資料、相同已存決策，離線重算 60 日／Corwin–Schultz／固定案例權重；沒有呼叫模型、沒有寫回 DB：

| 候選層 | 已存舊路徑 Sharpe | 現行 open 路徑 Sharpe |
|---|---:|---:|
| A | 0.803605 | 0.797804 |
| B | 0.638938 | 0.635717 |
| C | 0.916151 | 0.907445 |
| D | 0.788672 | 0.782486 |

差異不大，但已證實不是完全相同。此表不是新版模型結果，也沒有重算配對檢定或宣告顯著性。

建議：保留原結果，另產生具有 postprocessing version 的修正衍生結果；重新核對收益、回撤、Sharpe、檢定及報告表格。不可因程式已修，就認為歷史報告已更新。

### F4 [P2] 月度設計與資料就緒／切分摘要不一致

位置：`research_service/readiness.py:152-200`、`research_service/splits.py:65-107`、`research_service/web/datasets.py` 的 readiness 路由。

coverage 個案判斷能依設計採 20 日，但 study_readiness 只納入 QUARTER_DATES，總數仍是 180；temporal_split_summary 的分母固定每年四季。

直接重現 2025 年九檔 × 12 個月的摘要：test target_cases=36、available_cases=108、missing_cases=-72。非季末月度案例也會被現行 readiness 總覽略過。現行批次介面明確寫死 quarterly，尚不是完整月度操作介面。

建議：讓 readiness、gaps、split summary、前端與修復命令都接收並傳遞 design；分母按 design 日期集計算。E3 的單案例 engine 支援不等於月度 540 案的整套操作已完備。

### F5 [P2] 記錄模型 digest 不等於執行時核對模型 digest

位置：`research_service/web/jobs.py:102-119,240-245`、`research_service/engine.py:step`、`research_service/storage.py:371-385`。

建工作時解析 model_identity；續跑路由只做 store.control，engine 用 protocol.model 的可變模型名稱進行呼叫，没有對當前服務／權重 digest 再檢查。正式統計會拒絕合併不同「已記錄」identity，但無法發現某工作實際用了已更換的 tag，仍攜帶原 config identity 的情況。memory 同樣只以 protocol_hash 等欄位查詢，未以模型 digest 過濾。

這是程式防護缺口，未觀察到目前 Qwen 權重真的更換，也未測試雲端供應商是否能提供不可變 revision。

建議：凍結 expected digest／runtime manifest，開始與續跑前核對；必要時定期核對或使用不可變模型名稱。memory 使用相同 identity 邊界，不能只靠最終統計拒絕混合。雲端 alias 無法鎖 revision 時，明確報告限制。

### F6 [P2] 自我反駁檢查可接受沒有任何主張的字串

位置：`research_service/models.py:919-934`。

已增加歷史比對與 confidence_shift 驗算，方向正確；但 rebutted_claim=`!!!` 時 _words 回傳空集合，跳過比對，只要信心差值合理便通過。已在 strict checker 重現。

建議：要求含可辨識內容與最低有效長度，對空 token 結果 fail closed；用 prior claim ID 或明確原句。70% 連續字詞重疊最多證明接近引用，不能證明反駁有理。Canary 仍只做最小格式／立場檢查，未用完整歷史與新嚴格驗證，不宜提升成正式資格保證。

### F7 [P2] 已開跑的新版缺完整、單一的執行 manifest

位置：`docs/e2prime-preregistration.md:3,11-19,37-46`、`docs/e2prime-run-prompt.md:19-35`、`experiments/e2prime-qwen.yaml:9`。

新版登記時間與 hash 已記錄，但主要鎖定表仍列 v3-0930.3／舊 SHA／舊映像，補充記錄也有多個已取代 image ID；未列目前 v3-1001.1 的 aa0748e5… image ID。Compose 使用版本 tag，不是內容 digest。run-prompt 仍稱尚未登記並指向已替換的 GPU，與最新 addendum 不一致。

建議：保留舊歷史，另追加一張新版有效 manifest（source SHA、image ID／可用 repo digest、model digest、全部資料 ID hash、推理設定、GPU/Ollama runtime、登記时间）；更新操作入口讓它指向此 manifest。這是防重現錯版本，不是把已執行結果事後宣稱成另一版本。

## 上輪問題的複查結果

| 上輪項目 | 本輪現況 |
|---|---|
| 每日回測 close/open 混用 | 程式已修；歷史 state.daily 與統計仍需衍生重算（F3） |
| 新穎度誤寫成文字／新論點 | report:495 已改為引用 ID 新穎率，並寫明參照不同，已修 |
| C、D 僅差交換立場 | README、方法已明示可見性差異；report:388 仍有「四組呼叫一致」一句需修，A=1、B/C/D=7 |
| 同批重複排入、200% 進度 | enqueue 在同程序鎖內更新 existing；progress 按 dataset 去重，原反例已修；跨程序尚無 DB 唯一性保障 |
| context／並行設定不入指紋 | 新協議增加兩欄，generate 與 engine 使用凍結值，已修；不是全部 runtime 已鎖定 |
| 自我反駁只檢查非空 | 新版已有 own R1 與信心差值檢查，但有 F6，且不能代替論證品質評估 |
| 自動停機沒啟用 | 本輪部署已 enabled=true；目前正在執行，未實測實際停機 |

## 設計、資料與統計的評估

1. 同一模型模擬多個角色是合法的流程比較；不能把角色稱為獨立模型或獨立資訊來源。主要比較 D−C 現在是整套交換／可見性機制，研究問題應維持這個邊界。
2. 固定同一份報告與資料、保留原始 evidence、內容雜湊、先登記樣本、版本隔離與舊結果封存是合理基礎。資料雜湊證明保存內容未變，不證明原始資料在歷史時點絕對可得。
3. SEC 以 filed 日期與可比較同期篩選；宏觀有 vintage，新聞在分析日前窗口內篩選。Yahoo 還原 OHLC 仍需保留調整與資料版本限制。這次沒有重新下載或逐筆核對供應商資料。
4. 全窗口 FinBERT、固定 revision、CPU 本機處理、失敗不覆蓋原資料與覆蓋稽核是正向改進。至少三則是最低門檻，不是代表性保證；缺失與來源組成仍應按股票／年份呈現。
5. Hold 為棄權，coverage 與 conditional/selective accuracy 一起報告是必要的。McNemar 目前只用双方均下注的案例；不能把它當全 180 案的無條件準確率提升。
6. 已加入日期群聚／區塊敏感度；季度只有 20 個分析日期群，180 個案例不等於 180 個完全獨立樣本。30 案僅為軟體統計門檻，不是統計 power 的證明。
7. Holm 的實作按 horizon/cost/layer/basis/method 分別校正 D 對 A/B/C；不能解讀成對所有探索性檢定全域校正。需預先明定主要終點與何種檢定用來判定研究主張，不要事後選最小 p 值。這次沒有認定現有 Holm 計算公式錯誤。
8. train/validation/test 摘要有分層，但 `test_frozen=True` 是日期標籤，不是不可修改的操作保證。2025 舊結果已存在並被查看；新版本回跑 2025 不是恢復首次盲測。正式報告應區分回溯機制比較與新增樣本外驗證。
9. 舊 180 案有 75 案數字移除；42 案 memory_audit 記錄先前未完成案例。後者不能直接解讀成 42 案有前視偏誤（未必達成熟日），但應分析閘門／記憶是否受完成順序影響，保留 audit。
10. 記憶探針未發現明顯結果記憶，不等於證明沒有污染。固定樣本、單次溫度設定與可辨識公司線索的限制應繼續呈現。

## 系統與工程覆蓋

| 層級 | 本次檢查 | 評估／限制 |
|---|---|---|
| protocol／engine | 四組排程、輪次依賴、固定推理參數、驗證重試、降級與記憶 | 結構清楚；F1/F2/F5/F6 未解 |
| data／collect／FinBERT | 時間篩選、SEC 同期、新聞窗口、評分快取、原子更新 | 有稽核基礎；未重抓供應商資料或完整測 FinBERT 真推理 |
| backtest／statistics／reporting | 開盤路徑、棄權、成本、組合權重、配對、群聚、完整狀態 | 新回測正確方向；歷史重算與樣本外解釋仍需處理 |
| storage／API／CLI | 檢查點、owner、取消、續跑、登記、資料包、備份 | WAL-safe backup 與隔離 volume 合理；worker fencing 缺口 |
| security | localhost 綁定、Host、Origin、session、secret redaction、靜態路徑與大小限制 | 有測試；現行 :8003 無登入只適合受控本機，未做公開滲透測試 |
| frontend | ES module、批次預覽、資料／工作／正式完整度、研究卡片 | 語法通過；本次未實跑瀏覽器；月度支援不完整 |
| packaging／CI／Docker | pyproject、入口、非 root 容器、Linux/Windows/browser/arch 工作流程 | 本次用既有映像，未乾淨重裝／重建 ARM64，也未查遠端 CI 最新狀態 |
| docs／report | README、協議、登記、統計方法與結果表 | 已解多個文字問題；F3/F7 與預算說明仍需一致 |

本機存在未提交的資料包測試／工具；本次 287 個測試包含工作區可見的測試，因此不代表 GitHub clean clone 必然有相同 287 個測試。沒有讀取或印出 .env.research 的秘密值。

## 最新執行快照（易隨其他操作改變）

審查期間另有操作更新登記、啟動 GPU 並排入工作；以下是本次末次查詢，不是本次 review 執行的動作：

| 研究 | 狀態 |
|---|---|
| E2′ v3-1001.1 / 6be8da83… | 登記 180；complete 0、running 1、queued 89、未建立 90 |
| 作廢 v3-0930.3 / a3d65c6d… | 無工作，current=false |
| 舊 Qwen32B / 39f71a9c… | complete 180；75 案數字移除 |
| 舊 Qwen14B / de3e9138… | complete 53、paused 127 |
| 舊 Gemini Pro / 5435113a… | complete 13、paused 167 |

新版登記時間：2026-10-01 12:55:56 +08:00（UTC 04:55:56）。GPU 狀態從本次初查 DEPLOYING 變成 RUNNING；autostop.enabled=true，空佇列閒置門檻 15 分鐘，未有成功停機紀錄。依最新 addendum，GPU 為 b8904b25…，不要沿用舊操作文件的 instance ID。

Qwen :8003、monthly :8002、Gemini :8000 使用各自 volume。:8002 仍是 :dev 舊部署，不是「程式支援 v3-1001.2，所以正在跑 v3-1001.2」。新版尚無完成真實案例，不能報告新版實驗績效。

## 本次驗證

- 在 `stance-shift-lab-research-qwen:v3-1001.1` 使用唯讀工作區掛載、network none、PYTHONDONTWRITEBYTECODE=1 跑 unittest：**287 tests，OK，skipped=1；即 286 通過、1 略過**。瀏覽器測試因缺 Playwright 略過。測試中的 provider down／security error 日誌是刻意負向案例，不是正式服務故障。
- `ruff check research_service scripts`：通過。
- 所有 static/js ES module 語法檢查：通過。
- F1、F2、F4、F6 的反例在隔離容器／臨時 Store 重現；F5/F7 為來源／部署防護與紀錄缺口，不聲稱已發生模型漂移。
- F3 在正式 SQLite 唯讀快照以相同決策離線重新計算，未寫回、未呼叫模型；尚未重新計算全套 p 值。
- 未安裝套件、未啟動額外研究服務、未操作 GPU、未執行正式模型推理、未修改原始資料與論文。

## 建議處理順序

1. 由使用者決定是否暫停当前批次；先修 F1/F2 並加入負向與交錯執行測試。保留目前已產生的所有稽核與結果。
2. 若改變驗證政策，升級協議並新增事前登記；不可覆寫或混入 6be8da83 的結果。
3. 補完整執行 manifest、模型身份核對與一個真正完整的真實案例；再安排新版季度主批次。
4. 對舊 180 案產出版本化的修正回測衍生統計與品質分層，更新論文表格，不改原始失敗／修補紀錄。
5. 完成 design-aware 月度 readiness 與介面，再做 540 案與同版本跨模型比較。

「沒有可靠提升」也可以是研究結果；前提是測量與比較邊界可靠。不能把規則錯誤、尚未完成、或不完整控制造成的差異，當成模型太弱或交換機制有效／無效的證明。
