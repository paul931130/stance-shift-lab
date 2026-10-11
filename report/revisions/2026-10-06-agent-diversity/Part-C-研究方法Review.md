# Part C 研究方法 Review

結論：方向能延續原核心，但 RQ2 的能力差距與 RQ3 的計算量混淆尚未解決。目前適合完成研究設計稿，尚不足以直接啟動三組正式實驗。以下建議不自動成為 protocol。

| 檢查 | 判斷 | 必須處理的條件 |
|---|---|---|
| 1 RQ1 完整保留 | 通過 | 原句逐字保留，C/D 比較，不改為 Prompt Diversity |
| 2 RQ2 只操弄 heterogeneity | 部分成立 | Freeze 同一 Neutral Report、Research Agents、Judge、Gatekeeper、資料與 outcome；A/A→A/B 同時改變模型能力組成，不能宣稱純異質性因果效果 |
| 3 Model×stance 平衡 | 設計已要求，執行待鎖定 | AB、BA 都需規劃；建議每案同時跑兩指派，不能把同案兩指派當360獨立案例；若只分派一次，採股票×日期平衡且記錄隨機化 |
| 4 Judge 固定 | 通過但待選型 | RQ1、RQ2 同一 Judge model/version/prompt/temperature/context/memory；AB、BA 皆不換 Judge |
| 5 Gatekeeper 固定 | 通過但待凍結 | 相同實作 hash、風險閾值、覆蓋與證據規則；Gatekeeper 是既有驗證模組，不假定另有 LLM model |
| 6 RQ3 真正 domain debate | 通過方向、未完成規則 | 四領域各有 Bull/Bear 論證與交互批評，形成 Domain View；只做四份摘要不算此處的領域辯論 |
| 7 RQ3 公平比較 | 未解決 | 同資料、模型、horizon、輸出、候選／守門後層；Generalist 的 C 或 D 必須對應 domain 的規則，不能 C_generalist 對 D_domain 後稱純分工效果 |
| 8 compute/call confound | 存在 | calls、retries、tokens、cost、latency 均報告；未鎖定成本比較前，不能歸因 domain specialization |
| 9 其他重要變因 | 存在 | 記憶污染、資料覆盖、context truncation、Judge順序、模型能力/訓練記憶、執行失敗、依賴性、多重檢定 |

## RQ1 保留原問題與可辨識範圍

「在相同案例資料與相同名目決策呼叫次數下，自我反駁式立場交換辯論（D）的 60 日方向準確率與年化 Sharpe 是否高於固定立場辯論（C）？」

C/D 皆三輪雙方＋Judge，共七次名目決策呼叫。D 第二輪保留只讀自己第一輪並引用反駁的限制。此操作包含 stance switching、對手資訊隔離、引用驗證及重試，是複合流程的比較，不是只操弄 stance。原主要候選決策層、雙尾 McNemar、Ledoit–Wolf／區塊 bootstrap、兩端點 Holm 與日期群聚敏感性設計可作沿用基礎，正式新版須重新登記。舊樣本已見過的事實不可撤回。

## RQ2 能力與異質性不能完全分離

最低設計為 C_homo(A/A)、D_homo(A/A)、C_hetero(AB/BA)、D_hetero(AB/BA)。它回答「引入指定 B 後，D−C 是否改變」，不能涵蓋所有 heterogeneous models。

建議增加 B/B 的 C/D 對照，以知道改善是否只是 B 較強；這是待決策的補充控制，不直接擴充正式實驗。即使有 B/B，仍不能把互補、能力、訓練資料與模型家族分離成普遍異質性因果效果。另須固定 Judge 對模型身分的可見性，盲化模型標籤並控制輸入順序，防止 Judge 偏好某家族文風。

AB/BA 要記錄 model identity、原 stance、round stance 與 own first-round argument ID。D 的 round 2 只換 stance，原 agent/model 不換。若兩指派都跑，輸出不能在觀察結果後擇優。Accuracy 可先形成同案平均正確率或分指派報告；平均後不再是二元結果，不能直接用普通 McNemar。Sharpe 也不能簡單平均兩個 Sharpe 或把兩組策略拼接成雙倍 T。正式前須選擇以兩指派各自報告、合併日報酬或其他事先指定方式處理，並同案配對。

可建議 accuracy 的 interaction contrast：

Δ_interaction = (Acc_D,hetero − Acc_C,hetero) − (Acc_D,homo − Acc_C,homo)。

可考慮在相同案例與日期區塊共同重抽樣，或對二元正確性建立配對/群聚交互作用模型。這是建議，不直接採用；20個日期群聚數有限，模型推論需審慎。Sharpe 屬非線性策略量，須於同日期日報酬序列重抽樣後每次重新計算各 Sharpe 與交互差。這是實驗因素交互作用比較，沒有平行趨勢假設，不宜直接稱傳統觀察資料 DID。不能以「hetero顯著、homo不顯著」證明效果改變。

## RQ3 最優先的五項待鎖定事項

1. 各 Domain 採 Fixed only、Switch only、或 Fixed與Switch都跑。
2. 各 Domain 的 nominal decision calls、Domain View 生成是否另用 LLM、Final Aggregator calls、驗證與重試上限。
3. Generalist 公平比較：decision calls、token usage、compute cost、latency，何者匹配、何者只報告。
4. Final Judge input schema：只讀四 Views或另讀原證據、可否讀 transcripts、記憶、輸入順序與長度。
5. 四 Domain Views 的標準化 schema，以及缺資料／無方向輸出如何處理。

以上全部標示「正式實驗前待鎖定」。固定資源比較、同三輪但不同資源的架構比较、或performance/cost frontier可作選項，不自動決定。若維持相同輪數且四個 domain 各雙方三輪，僅辯論呼叫量便為4×2×3；這是展示混淆的算例，不是決定實驗預算。研究代理人呼叫、Domain View 生成與Final Judge須另外計算。只匹配名目calls也不能證明compute匹配。

領域局部結論一律針對同一60交易日方向，可將短期指標當證據但不可把20日預測與60日預測直接投票。相同 evidence 集的領域切片應從鎖定 Research outputs 分流，不重新抓新聞或改摘要模型。Generic與Domain需控制模型組成；首版RQ3若與heterogeneity同時改變，須明說是整體架構效果。建議將模型條件固定，但模型選擇待確認。

4:0／3:1／2:2只適用四個有效binary stances；某domain資訊不足或無方向時需另列 missing/abstain，不能硬塞進2:2。Domain votes並非四筆獨立樣本。Aggregator是上層整合器，後接相同Gatekeeper；不能拿Gatekeeper代替整合器。

## 共同控制與統計風險

- 鎖定記憶來源與可見時間：僅分析日前已到期，隔離試跑與正式batch；若各組讀自己過去結果，歷史輸入會隨處理改變，估计量成为動態整套流程效果。若要固定共用記憶，須另登記，不能默默改RQ1。
- 股票與日期反覆出現、60日持有期可重疊；180案例不是180独立日期，Sharpe的T另核對。依賴性與有限群聚須納入敏感性，而非只用獨立McNemar宣稱充分控制。
- 凍結資料時間可降低pipeline直接洩漏，不能排除LLM訓練記憶；晚近模型對2021–2025內容可能有不同汙染程度。
- FinBERT revision、新聞來源與37案排除集合、行情事後調整仍待核對；失敗／缺失規則應在看結果前訂定，不因模型失敗率不同而另選有利配對集合。
- 三個RQ正式檢定 family、共同主要端點與探索diagnostics需事先指定；保留RQ1的Holm規則不代表全三題自動完成多重性控制。
- temperature相同不保證跨模型同程度隨機性；seed可能不支援，須記錄實際是否套用，不能假稱deterministic。
- 原A/B允許Hold、無長期記憶，C/D候選層須Buy/Sell；補充對照不能只歸因辯論。守門後Hold另報coverage与条件accuracy。

## 舊 RQ1 升格正式新版結果前的確認

核對 data version、snapshot/Neutral Report hash、protocol version/hash、prompt、model ID/weights/version、sample与exclusions、base与call seeds、temperature/context、outcome（開盤進出与horizon）、evaluation（candidate或post-gate、日面板、成本）、code commit/hash、preregistration時間與變更紀錄、raw outputs與aggregation的一致性。由使用者確認是否允許列入新版正式Results。在確認前全部維持prior result；若有規則変更，不直接合併。單純重登記或重跑，仍不能把已見180案稱獨立樣本外。

## 文獻核對

2026-10-06核對原有的[Zhang et al. 2025](https://arxiv.org/abs/2502.08788)、[TradingAgents](https://arxiv.org/abs/2412.20138)與[Huang et al.](https://arxiv.org/abs/2310.01798)原始頁面。前者可支持異質模型的研究動機，TradingAgents可支持金融功能分工；不能直接證明本研究四領域各自C/D與上層整合的因果效益。【需補文獻】heterogeneous debate能力控制、domain debate与task decomposition的直接對照、跨領域整合与資訊負荷。其餘原引用沿用既有書目，本次不宣稱全部重新完成文獻查證或系統性回顧。
