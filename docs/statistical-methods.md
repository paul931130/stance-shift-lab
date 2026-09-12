# v3 統計實作口徑

主要持有期固定為 60 日，30/90 日只作穩健性分析。比較必須具有相同 case、資料版本、協議與模型設定；不得把不同配置混成一份統計。實驗尚未產生足量真實資料前，不呈現假造的顯著性結果。

方向準確率採配對 McNemar 精確雙尾二項式檢定；同時顯示四格表、配對數與不一致數。這項經典檢定本身不校正不同 case 之同期市場相依，輸出必須保留警語並搭配日期區塊敏感性分析。多組比較另提供 Holm 校正，不以選擇最小 p 值宣稱結果有效。[statsmodels 官方定義](https://www.statsmodels.org/dev/generated/statsmodels.stats.contingency_tables.mcnemar.html)

Sharpe 檢定輸入為**對齊的每日超額投資組合報酬**，不是將 200 個重疊 case 的 60 日累積報酬當成 200 個獨立每日報酬。主分析建立完整 date × case × method panel，對每個已選入 case 採固定等權；尚未進入持有期的 sleeve 視為現金 0，這是可部署投組的 `portfolio_basis=all`。`portfolio_basis=active` 只平均當天有方向部位的 sleeve，權重隨日期改變，僅作敏感性分析。零波動策略回報不可檢定，而非產生無限大 Sharpe 或虛假的 p 值。

Jobson–Korkie 採 Memmel 修正版，明示 IID 聯合常態假設。主要穩健補充使用 Ledoit–Wolf 的對稱 studentized circular block bootstrap，依論文式 (2)、(5)–(9) 實作。原樣本標準誤使用 Bartlett HAC（含 T/(T−4) 修正），不是作者偏好的 prewhitened QS；此核函數選擇在輸出中明示。bootstrap 樣本以抽出的完整區塊計算 natural block studentizer，而非套用 IID 標準誤或 percentile interval。[Ledoit 與 Wolf 原論文](https://www.econ.uzh.ch/dam/jcr:ffffffff-935a-b0d6-0000-00007214c2bc/jef_2008pdf.pdf)

所有股票與方法在同一日期共用抽樣索引；每段索引是循環連續日期區塊。預設區塊長度 20 交易日、1999 次、種子 905；正式報告應同時提供不同區塊長度的敏感性檢查。樣本不足三個區塊或超過 10% 重抽樣退化時，拒絕硬算檢定。保留有效重抽數與實際抽樣長度。少於 30 個唯一完成的歷史 case 時，系統只輸出描述統計，不產生任何 p 值。

主分析使用 `decision_layer=candidate`，以避免把 Gatekeeper 的風控覆寫誤當成 A/B/C/D 決策機制的效果；`decision_layer=gated` 另列為敏感性結果。Hold 是棄權，不當成免費正確答案：同時報告 coverage、selective accuracy、hold justified rate 與 hold opportunity cost。候選 action 由儲存的 `expected_return_pct` 與預先註冊 `hold_band_sigma=0.5` 推導；sigma 0、0.25、0.5、1.0 都必須呈現為敏感性分析。

D 組第 2 輪刻意不讀取前一輪辯論，以測量模型在中立報告下是否能重新找出相反立場的證據。這會讓 D 的 prompt token 數通常低於 C；呼叫數雖保持 A=1、B=7、C=7、D=7，token 數並不等化且會輸出。若 D 表現不同，不能排除較短脈絡本身的影響；應以 `switch_isolation=false` 做敏感性重跑。

這些模組目前正在接入正式資料與實驗介面；單元測試使用人工生成的測試向量，不能作為研究績效或方法優越性的證據。
