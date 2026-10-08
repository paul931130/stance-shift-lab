# v3 統計實作口徑

主要持有期固定為 60 日，30/90 日只作穩健性分析。比較必須具有相同 case、資料版本、協議與模型設定；不得把不同配置混成一份統計。實驗尚未產生足量真實資料前，不呈現假造的顯著性結果。

方向準確率採配對 McNemar 精確雙尾二項式檢定；同時顯示四格表、配對數與不一致數。這項經典檢定本身不校正不同 case 之同期市場相依，輸出另提供整個分析日群聚的配對準確率差區間，以及連續日期區塊長度敏感度（季度 1／2／4 個分析日、月度 1／3／6／12 個分析日）。這些百分位區間只作依賴結構敏感性分析，不另宣稱為顯著性 p 值；季度僅 20 個日期群聚，須特別保守。多組比較另提供 Holm 校正，不以選擇最小 p 值宣稱結果有效。[statsmodels 官方定義](https://www.statsmodels.org/dev/generated/statsmodels.stats.contingency_tables.mcnemar.html)

Sharpe 檢定輸入為**對齊的每日超額投資組合報酬**，不是將季度 180 案或月度 540 案的重疊持有期報酬視為獨立每日觀測。主分析建立完整 date × case × method panel，對每個已選入 case 採固定等權；尚未進入持有期的 sleeve 視為現金 0，這是可部署投組的 `portfolio_basis=all`。`portfolio_basis=active` 只平均當天有方向部位的 sleeve，權重隨日期改變，僅作敏感性分析。零波動策略回報不可檢定，而非產生無限大 Sharpe 或虛假的 p 值。

Jobson–Korkie 採 Memmel 修正版，明示 IID 聯合常態假設。主要穩健補充使用 Ledoit–Wolf 的對稱 studentized circular block bootstrap，依論文式 (2)、(5)–(9) 實作。原樣本標準誤使用 Bartlett HAC（含 T/(T−4) 修正），不是作者偏好的 prewhitened QS；此核函數選擇在輸出中明示。bootstrap 樣本以抽出的完整區塊計算 natural block studentizer，而非套用 IID 標準誤或 percentile interval。[Ledoit 與 Wolf 原論文](https://www.econ.uzh.ch/dam/jcr:ffffffff-935a-b0d6-0000-00007214c2bc/jef_2008pdf.pdf)

所有股票與方法在同一日期共用抽樣索引；每段索引是循環連續日期區塊。預設區塊長度 20 交易日、1999 次、種子 905；正式報告應同時提供不同區塊長度的敏感性檢查。樣本不足三個區塊或超過 10% 重抽樣退化時，拒絕硬算檢定。保留有效重抽數與實際抽樣長度。少於 30 個唯一完成的歷史 case 時，系統只輸出描述統計，不產生任何 p 值。

主分析使用 `decision_layer=candidate`，以避免把 Gatekeeper 的風控覆寫誤當成 A/B/C/D 決策機制的效果；`decision_layer=gated` 另列為敏感性結果。Hold 是棄權，不當成免費正確答案：同時報告 coverage、selective accuracy、hold justified rate 與 hold opportunity cost。候選 action 由儲存的 `expected_return_pct` 與預先註冊 `hold_band_sigma=0.5` 推導；sigma 0、0.25、0.5、1.0 都必須呈現為敏感性分析。

D 組第 2 輪只讀自己的第 1 輪；C 組則讀雙方第 1 輪。因此 D−C 是「交換立場＋交換輪資訊隔離」的整套機制效果，不能寫成只識別立場互換的因果效果。兩組呼叫數均為 7，但 token 數不等化且會輸出。若要單獨估計交換效果，需另增 E 組：同 C 的雙方歷史可見性，只改變第 2 輪立場，並在新一輪實驗前事前登記。

數字驗證自季度 v3-0930.3／月度 v3-0930.4 起採結構化 `numeric_claims`：研究摘要與決策敘述每個數字都需連結引用證據 ID、來源欄位指標、期間、單位、數值與逐字敘述片段。允許來源原值或標準四捨五入至最多三位有效數字（half-up）；不允許改單位或自行計算。決策重試仍未能驗證者，只在敘述中移除未支持數字，並保留稽核；研究摘要若未通過驗證則標記為降級來源摘錄並排除正式統計。報告需另列修補案例的分層結果，不得據此推論修補對決策沒有影響。舊版 180 案維持其原協議與驗證方式，不能視為新規則下的正式重跑。

全量 FinBERT 新聞輸入需隨每案保存窗口內新聞數、來源標籤、已評分／缺分數量、缺失率及是否達至少三則指標門檻；報告按股票與年份呈現覆蓋，避免平均值掩蓋集中缺失。指標版本與舊版標題摘要不可直接合併比較。

狀態呈現分為三個門檻：工作案例是否全數完成、已完成案例是否通過正式品質條件、事前登記的完整樣本是否全部完成。達到 30 個案例只表示系統允許計算統計量，並不表示工作完成或正式樣本完整。Training、Validation、Test 需各自報告；Test 僅作凍結後最終評估，不用於提示或模型選擇。

新版統計與品質報告已接入目前工作目錄中的研究報告介面，但尚無新版正式批次產生的實證結果；任何合成資料檢查都只能驗證程式流程，不能作為研究績效或方法優越性的證據。

# RQ2／RQ3 統計實作（`research_service/rq_analysis.py`）

**RQ2 準確率交互作用。** 估計量為 Δ = (Acc_D,hetero − Acc_C,hetero) − (Acc_D,homo − Acc_C,homo)。異質條件的 AB 與 BA 兩配置共享同一案例與 outcome，不是 2n 筆獨立觀測。可事先擇一登記：`hetero="separate"` 並列報告 AB 與 BA 兩個交互差（同一組重抽索引）；或 `hetero="mean"` 先在每案平均 AB/BA 正確性（取值 0、0.5、1，非二元，因此不套普通 McNemar）。推論為聯合配對日期區塊 bootstrap：每次重抽整個分析日期（該日全部案例、全部組別與配置一起），以連續季度日期的循環區塊抽樣；區塊長度 1（日期群聚 bootstrap）、2、4 個日期作敏感性。區間為 percentile，p 值為中心化重抽分布的雙尾比例。同條件內 D 對 C 的精確 McNemar（homo、AB、BA）僅為次要描述；「一組顯著、另一組不顯著」不構成交互作用證據。單元測試確認：BA 完全複製 AB 時，平均法的區間寬度與只用單一配置相同，而錯誤地堆疊成 2n 筆會縮窄區間。

**RQ2 Sharpe 交互作用。** `sharpe_combination_test` 將 RQ1 的 Ledoit–Wolf studentized circular block bootstrap 推廣到 Σ w_j·SR_j：每次以共同交易日區塊重抽對齊的日報酬面板，並重新計算每組 Sharpe 與交互差（k=2、w=(1,−1) 時與 `ledoit_wolf_block` 完全一致）。原樣本標準誤為 Bartlett HAC，含 T/(T−2k) 修正。`hetero="separate"` 分別檢定 AB 與 BA；`hetero="pooled_half_weight"` 先以 `pooled_assignment_returns` 建立每案各半權重持有 AB 與 BA 的同 T 日報酬，再計算 Sharpe。系統不平均兩個 Sharpe，也拒絕把兩配置拼接成 2T 序列。`sharpe_block_sensitivity` 提供交易日區塊長度敏感性。

**RQ3。** `rq3_rule_matched_contrasts` 以相同機制估計 C_domain − C_generalist 與 D_domain − D_generalist（日期區塊 bootstrap、McNemar、Sharpe 差）；Holm 只套用於明確指定的 `holm_family`。`performance_cost_table` 依組別彙整呼叫數、重試、輸入／輸出 tokens、wall time 與端到端延遲（缺值另計，不當成 0）。`domain_agreement_distribution` 只在四個 Domain View 皆為有效 Buy/Sell 時計 4:0／3:1／2:2，棄權或資訊不足依有效 view 數另列；計數單位是案例，Domain View 是同一案例的中間輸出，不是獨立樣本。

**規劃用 power／MDE。** `simulate_interaction_power` 與 `interaction_mde` 依假設的不一致率、AB/BA 一致程度與日期效果，以日期群聚穩健 t（G−1 自由度）近似估計 power。這只是規劃值，不是正式資料的檢定；正式分析仍用 bootstrap。

**正式前仍須事先登記的選擇：**
1. AB/BA 處理：分開報告（並指定何者為主要，或兩者皆需成立），或每案平均；Sharpe 用分開或半權重合併。
2. 日期區塊主要長度（1、2 或 4 個日期）與 Sharpe 交易日區塊長度；重抽次數與種子。
3. 區間類型（目前準確率為 percentile，Sharpe 為 studentized 對稱區間）及單／雙尾；RQ1 的 `date_cluster_block_accuracy` 只作敏感度區間、不給 p 值，RQ2 的日期區塊 bootstrap p 值是否作為主要推論須另行登記。
4. RQ2/RQ3 的檢定 family 與多重比較方法（RQ1 的 Holm 不自動涵蓋）；主要端點與探索 diagnostics 的界線。
5. 缺失、失敗與棄權規則（目前要求完整配對資料，否則拒絕計算），以及候選層或守門後層。
6. RQ3 的公平比較基準（匹配名目呼叫、token 或只報告成本）及 Domain View 缺漏的處理。
7. Power 模擬中的不一致率、AB/BA 一致程度與日期效果假設值。
