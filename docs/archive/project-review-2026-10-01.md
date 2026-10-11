# 專案完整 Review — 2026-10-01

## 結論與範圍

系統具備實際執行研究的基本能力，但目前仍有會影響主要結果解讀的驗證與回測問題。建議先修正、增加反例測試、重新鎖定協議，再啟動新版 E2′ 季度批次；此時不宜直接擴大到月度 540 案。

本次為唯讀審查，涵蓋 protocol、模型輸入／輸出驗證、資料處理、engine、回測、統計、儲存、API、安全邊界、前端狀態及 Docker 實際資料庫。沒有修改實作、提交 Git、排入新實驗或啟停 GPU；本文件是唯一由本次 review 新增的檔案。

審查期間 HEAD 由 `3efda08cb5421b3f61276ca4c3eb7dabb6c4f5c0` 變成 `3c94326d1109626c45197257061bbc8ef7de907c`，工作區另有持續變更。以下測試結果代表執行測試時的工作區，而非最後 HEAD 加所有未提交變更的不可變快照。後續修改仍需重新測試與部署驗證。

## 優先問題

### 1. [P1] 具體數字主張的驗證仍可被錯誤敘述繞過

位置：`research_service/models.py:270-368`，尤其 `328-329`。

新驗證確實比較 structured claim 的 evidence ID、metric、period、unit、value，但沒有確保自然語言句子表達的指標與單位就是那些欄位。因此來源 `Revenue = 100 USD` 下，將 numeric_claims 正確填為 Revenue / USD / 100，以下錯誤句子仍通過：

- `Revenue was 100 billion USD.`
- `Net income was 100 USD.`

此外，某欄位根本沒有該 quote 時，`text.find(quote)` 回傳 -1，但程式未檢查 >= 0；長 quote 的位置範圍可錯誤覆蓋另一欄位的數字。反例中 rationale 的合法 quote，讓 risks 中 `Fabricated value is 100.` 也通過。

影響：目前「通過數字驗證」不能解讀成數字主張正確。既有結果更不能因移除了錯誤數字，就認定原決策未受其影響。

建議：先修負索引與逐欄位／逐次出現的引用對應；再採用可驗證的主張模板或由結構化欄位渲染主張，檢查語意中的指標、期間與單位。加入上述負向測試。四捨五入也需補一致測試：目前「至多 3 位有效數字」實作只覆蓋 3 位，123456→120000 等更粗精度不被接受。

### 2. [P1] 每日報酬使用不一致的價格時點，可能影響 Sharpe 與日期配對

位置：`research_service/backtest.py:47,64-80`。

案例總報酬採 entry open → exit open，但 daily path 從 selected[1] 開始，中間用 close，最後改用 exit open。進場日的 close 未被標記，第一筆日報酬因而混合多段時距。

已重現：1/2 open=100、close=110，後續各日 open/close=110、horizon=3，輸出為 `1/3:+10%, 1/6:0%, 1/7:0%`。實際價格上漲發生於 1/2，卻歸到 1/3。

影響：不代表案例整段 gross return 一定算錯，但會改變每日時間對齊、同期組合、波動及由日報酬衍生的 Sharpe／區塊統計。修正後需要重新計算統計；不能沿用未核對的 Sharpe 結論。

建議：統一 open-to-open 的逐日標記；若採 close-to-close，則明確處理 entry/exit 的部分交易日與日期定義。加入跨週末、進場日跳升、最後一天開盤跳空及多股票配對測試。

### 3. [P1] 報告將「證據引用新穎率」寫成「文字重疊／新論點」

位置：`research_service/engine.py:142-171`、`report/stance-shift-ssrn.tex:495`。

程式只比較 evidence_ids 集合，novelty_rate = 新引用 ID 數 / 本輪引用 ID 數；沒有比較文字，也沒有判斷論點有效性。資料庫舊 180 案的平均值為 D=0.4169907407、C=0.0120370370，正好對應報告中的 0.42 與 0.01。

影響：不能以此支持「大量新論點」或「文字重疊衡量」。而且 D 的參照是另一代理先前持有同一立場的輪次，C 的參照是自己的先前輪次，解讀需交代比較基準。

建議：改稱「引用證據新穎率」，限縮結論並寫清分母與參照輪次。若要量測新論點，另定義可重現的命題層級指標，不能直接替換名稱沿用數值。

### 4. [P2] 交換輪沒有驗證是否真的反駁自己先前的主張

位置：`research_service/models.py:622-635,837-842`；`research_service/canary.py:35-60`。

prompt 要求引用自己的 R1 主張與信心差值，但 validator 僅檢查 rebutted_claim 非空、confidence_shift 在 [-1,1]，未核對自己的歷史，也未驗算差值。

已重現：填入 `An arbitrary statement never present in any previous turn.` 及任意合法範圍的 confidence_shift，仍被接受。Canary 的交換輪沒有傳入歷史，因此也不能證明完整的自我反駁流程成立。

影響：實驗可比較不同提示流程，但不能聲稱已驗證「反駁自己原論點」這項機制被遵守。

建議：使用 own prior call/claim ID，validator 接收自己的 prior record 並核對；confidence_shift 由程式計算。Canary 補完整 R1→R2 路徑。相同模型擔任不同角色本身不是錯，但它們不等於兩個獨立模型或獨立資訊來源。

### 5. [P2] 批次內重複案例會重複排入，進度可超过 100%

位置：`research_service/web/context.py:97-98`、`research_service/web/studies.py:72-73`、`research_service/progress.py:28-33,58`。

BatchInput 沒有案例唯一性驗證；enqueue 的 existing 集合只讀一次，建立第一個工作後不更新。同一批次內重複 dataset_id 都會建立。progress 又以工作數作分子、唯一 dataset 數作分母。

隔離反例用真實 BatchInput/router endpoint、mock prepare 与記憶體 Store：一個登記案例，批次傳入兩次，created=2；兩個工作完成後 done_fraction=2.0。沒有對正式 DB 寫入。

建議：拒絕批次重複案例，並以交易／唯一性約束保護並發排程；完成率按正式案例去重，另列取消與重試工作。不能只把百分比 clamp 到 100%。

### 6. [P2] 推理 context 設定改變不會改變協議指紋

位置：`research_service/models.py:69-71,714-723`、`research_service/protocol.py:171`。

已重現 RESEARCH_MODEL_CONTEXT_LENGTH=4096 与 8192 的 protocol fingerprint 完全相同，但傳給 Ollama 的 num_ctx 不同。audit 有記錄 context，卻不等於防止同一正式批次混用推理設定。

建議：context 長度及必要的推理／執行參數納入凍結的 execution manifest，建立、續跑時核對。修正不可悄悄回填成舊結果原本就有的設定。

### 7. [P2] C、D 比較與呼叫預算的文字仍有互相矛盾

位置：`research_service/protocol.py:96,239-244`、`report/stance-shift-ssrn.tex:388`，以及 README 四組說明。

目前 switch_isolation=True：D 交換輪只看自己的歷史，C 可以看双方歷史。因此 D−C 衡量「交換立場＋資訊可見性調整」整套機制，不是純交換立場。新版 E2′ 事前登記與部分報告已有正確說明，但 report:388 仍寫「只是第二輪不換邊」，且稱四組呼叫次數一致；A 與多呼叫組的預算並不一致。

建議：統一 README、方法、摘要與圖表說明。若要識別純交換效應，需新增同資訊可見性的對照並重新登記，不要在已凍結 E2′ 上直接切換 isolation。

## 實際執行狀態（本次查詢時）

| 批次 | 工作狀態 | 解讀 |
|---|---:|---|
| 舊 Qwen32B / v3-0929.1 / 39f71a9c… | complete 180/180 | 工作已完成；75 案曾移除敘述數字，需品質分層；不是新版 E2′ 結果 |
| 新 E2′ / a3d65c6d… | 已登記 180，未建立工作 180 | 尚未開始，不可描述成已完成實驗 |
| 舊 Qwen14B / de3e9138… | complete 53，paused 127 | 舊版未完整；不應和新版合併 |
| 舊 Gemini Pro / 5435113a… | complete 13，paused 167 | 舊版未完整；不應當成新版跨模型對照 |

Qwen8003、monthly8002、Gemini8000 現在使用各自 Docker volume；歷史上共享 DB 的風險在這次部署中已隔離。8000/8002 的舊映像沒有新 /api/studies 路由，404 不能直接解讀成實驗引擎故障。

GPUtw instance `61159cf5-ae75-4995-b917-de46564a7722` 查詢結果為 STOPPED。8003 autostop.enabled=false；目前沒有運算中 GPU 可由本次 review 停止。下次啟動前需核對部署映像、管理權限與自動停機是否真正啟用，不能只看本機已有新程式。

新版新聞輸入覆蓋：180 案中 133 案有 4 個情緒指標、44 案有 3 個、2 案有 1 個、1 案沒有指標（MCD 2023-12-31）。至少 3 則是產生指標的最低門檻，不代表覆蓋充分。新版計畫已保留低密度敏感度設計，報告仍需提供股票／年份缺失與來源組成。

## 已驗證、做得合理的部分

- 協議版本、資料雜湊、模型身份、登記樣本与完成狀態有明確分層；舊結果保留而非覆蓋。
- 統計已加入日期群聚／區塊敏感度與 train/validation/test 分層；季度只有 20 個日期群，仍需保守解讀。
- 全窗口新聞情緒與樣本數／來源資訊，比只選少量標題更可稽核；需保持固定資料版本。
- 報告 API/統計頁已區分工作完成、品質條件、正式樣本完整与最低推論門檻。
- 權限、同源／跨來源防護及服務的 localhost 邊界有測試覆蓋；本次未進行公開部署滲透測試。

## 驗證紀錄與限制

- 使用既有 CPU Docker 映像 `stance-shift-lab-research-qwen:v3-0930.3`，將工作區 read-only 掛載，network none，PYTHONDONTWRITEBYTECODE=1。没有调用云端模型或消耗 GPU 推理額度。
- `python -m unittest discover -s research_service/tests -p 'test_*.py'`：OK，273 個測試，略過 1 個（容器缺 Playwright）。不代表瀏覽器全流程已驗證。
- `ruff check research_service scripts`：通過。
- JavaScript ES module 語法檢查：通過；不等於互動 UI 測試。
- 數字主張、交換輪欄位、context fingerprint、日報酬与重複排程反例均在隔離環境執行。正式 SQLite 僅以 mode=ro 查詢。
- 沒有重新執行完整真实案例、重新計算所有統計或啟動 E2′；不能由單元測試推出研究效果成立。
- 既有結果已看過的年份，即使重新跑同年新版，也不是首次未見的盲測資料。應明確區分新協議的回溯驗證與真正新增的樣本外驗證。

## 建議順序

1. 先補數字與回測反例測試並修正 P1，重新計算既有統計；修正報告的新穎率解釋。
2. 補交換輪歷史約束、排程去重与執行設定凍結，統一 C/D 和預算文字。
3. 固定 source SHA、image digest、資料、模型与 manifest；確認自動停機；先跑一個完整真實案例檢查所有 audit。
4. 以新協議重新登記／執行季度對照，保留舊 180 案作为舊版與品質敏感度資料。
5. 同版本季度基準完整後，再考慮月度 540 案與跨模型實驗。
