window.SHOWCASE_CASES = [
 {
  "ticker": "INTC",
  "analysis_date": "2024-03-31",
  "protocol": "v3-1002.3",
  "research": {
   "technical": {
    "status": "complete",
    "summary": "The technical data as of 2024-03-28 indicates a return20 of 0.026016 (E11), with the price_vs_mean20 at 0.015776 (E12). The price_vs_mean60 is reported at -0.006328 (E13), and the mean20_vs_mean60 is -0.021760 (E14). The volatility60_annual is 0.407732 (E15).",
    "zh": "截至 2024-03-28 的技術面資料：20 日報酬 return20 為 0.026016（E11），價格相對 20 日均線 price_vs_mean20 為 0.015776（E12）；價格相對 60 日均線 price_vs_mean60 為 -0.006328（E13），20 日均線相對 60 日均線 mean20_vs_mean60 為 -0.021760（E14）；60 日年化波動率 volatility60_annual 為 0.407732（E15）。"
   },
   "fundamental": {
    "status": "complete",
    "summary": "SEC 財務欄位採同概念、相近期間配對；精確數值、單位與申報期間保留於 claim_map 及原始引用證據。"
   },
   "sentiment": {
    "status": "complete",
    "summary": "The sentiment analysis for the target asset shows a mean FinBERT score of 0.245621 over the period from 2024-01-03 to 2024-03-21 (E4). During the same period, the positive sentiment share was 0.666667 (E5), and the negative sentiment share was 0.095238 (E6). For context, the mean FinBERT score across the broader context was 0.181848 from 2024-01-02 to 2024-03-27 (E7).",
    "zh": "針對目標資產的情緒分析：2024-01-03 至 2024-03-21 期間，FinBERT 平均分數為 0.245621（E4）；同期正面情緒占比 0.666667（E5），負面情緒占比 0.095238（E6）。作為對照，較廣背景下 2024-01-02 至 2024-03-27 的 FinBERT 平均分數為 0.181848（E7）。"
   },
   "macro": {
    "status": "complete",
    "summary": "As of 2024-03-30, the unemployment rate (UNRATE) is reported at 3.9 for the observation period 2024-02-01. The federal funds rate (FEDFUNDS) is 5.33 for the same period. Additionally, the consumer price index for all urban consumers, seasonally adjusted (CPIAUCSL), is recorded at 311.054 for the observation period.",
    "zh": "截至 2024-03-30，失業率（UNRATE）在觀察期 2024-02-01 為 3.9；同期聯邦基金利率（FEDFUNDS）為 5.33；另外，都市消費者物價指數（CPIAUCSL，經季節調整）為 311.054。"
   }
  },
  "evidence": [
   {
    "id": "E1",
    "domain": "fundamental",
    "claim": "Revenue: current=54228000000 USD; current_period=2023-01-01–2023-12-30; period_days=363; prior=63054000000 USD; prior_period=2021-12-26–2022-12-31; year_over_year_change_pct=-13.997526; current_form=10-K; current_filed=2024-01-26",
    "label_zh": "營收年增率 -13.997526%"
   },
   {
    "id": "E2",
    "domain": "fundamental",
    "claim": "NetIncomeLoss: current=1689000000 USD; current_period=2023-01-01–2023-12-30; period_days=363; prior=8014000000 USD; prior_period=2021-12-26–2022-12-31; year_over_year_change_pct=-78.924382; current_form=10-K; current_filed=2024-01-26",
    "label_zh": "淨利年增率 -78.924382%"
   },
   {
    "id": "E3",
    "domain": "fundamental",
    "claim": "OperatingCashFlow: current=11471000000 USD; current_period=2023-01-01–2023-12-30; period_days=363; prior=15433000000 USD; prior_period=2021-12-26–2022-12-31; year_over_year_change_pct=-25.672261; current_form=10-K; current_filed=2024-01-26",
    "label_zh": "營業現金流年增率 -25.672261%"
   },
   {
    "id": "E4",
    "domain": "sentiment",
    "claim": "sentiment_target_mean = 0.245621",
    "label_zh": "目標資產情緒平均 0.245621"
   },
   {
    "id": "E5",
    "domain": "sentiment",
    "claim": "sentiment_target_positive_share = 0.666667",
    "label_zh": "目標資產正面情緒占比 0.666667"
   },
   {
    "id": "E6",
    "domain": "sentiment",
    "claim": "sentiment_target_negative_share = 0.095238",
    "label_zh": "目標資產負面情緒占比 0.095238"
   },
   {
    "id": "E7",
    "domain": "sentiment",
    "claim": "sentiment_context_mean = 0.181848",
    "label_zh": "背景情緒平均 0.181848"
   },
   {
    "id": "E8",
    "domain": "macro",
    "claim": "UNRATE: 3.9，觀測期間 2024-02-01，截至 2024-03-30 可知版本",
    "label_zh": "失業率 3.9"
   },
   {
    "id": "E9",
    "domain": "macro",
    "claim": "FEDFUNDS: 5.33，觀測期間 2024-02-01，截至 2024-03-30 可知版本",
    "label_zh": "聯邦基金利率 5.33"
   },
   {
    "id": "E10",
    "domain": "macro",
    "claim": "CPIAUCSL: 311.054，觀測期間 2024-02-01，截至 2024-03-30 可知版本",
    "label_zh": "消費者物價指數 311.054"
   },
   {
    "id": "E11",
    "domain": "technical",
    "claim": "return20 = 0.026016",
    "label_zh": "20 日報酬 0.026016"
   },
   {
    "id": "E12",
    "domain": "technical",
    "claim": "price_vs_mean20 = 0.015776",
    "label_zh": "價格相對 20 日均線 0.015776"
   },
   {
    "id": "E13",
    "domain": "technical",
    "claim": "price_vs_mean60 = -0.006328",
    "label_zh": "價格相對 60 日均線 -0.006328"
   },
   {
    "id": "E14",
    "domain": "technical",
    "claim": "mean20_vs_mean60 = -0.021760",
    "label_zh": "20 日均線相對 60 日均線 -0.021760"
   },
   {
    "id": "E15",
    "domain": "technical",
    "claim": "volatility60_annual = 0.407732",
    "label_zh": "60 日年化波動率 0.407732"
   }
  ],
  "records": [
   {
    "group": "A",
    "kind": "decision",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -5.0,
    "confidence": 0.65,
    "rationale": "Revenue (E1) and net income (E2) declined YoY, with net income down 78.9%. Operating cash flow (E3) also dropped 25.7%. Technical indicators show mixed signals (E14), and volatility remains high (E15).",
    "zh": "營收（E1）與淨利（E2）年減，其中淨利下滑 78.9%；營業現金流（E3）亦下降 25.7%。技術指標訊號好壞參半（E14），波動率仍高（E15）。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 1,
    "action": "Sell",
    "expected_return_pct": -15,
    "confidence": 0.68,
    "rationale": "Revenue and net income declined sharply YoY (E1,E2), with operating cash flow also dropping (E3). Sentiment is positive, but technical indicators are mixed with price below 60-day mean (E13).",
    "zh": "營收與淨利年減幅度大（E1,E2），營業現金流也下降（E3）。情緒偏正面，但技術指標好壞參半，價格低於 60 日均線（E13）。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 2,
    "action": "Sell",
    "expected_return_pct": -4.5,
    "confidence": 0.68,
    "rationale": "Revenue and net income declined sharply YoY, with operating cash flow also contracting. Sentiment is positive but not strongly aligned with fundamentals. Technical indicators show mixed short-term momentum.",
    "zh": "營收與淨利年減幅度大，營業現金流也在收縮。情緒偏正面，但與基本面並不一致。技術指標顯示短期動能好壞參半。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 3,
    "action": "Sell",
    "expected_return_pct": -4.5,
    "confidence": 0.65,
    "rationale": "Revenue and net income fell year over year (E1, E2), and operating cash flow declined (E3). Technical indicators show weak price momentum and mixed direction (E11, E14).",
    "zh": "營收與淨利較去年同期下滑（E1, E2），營業現金流也下降（E3）。技術指標顯示價格動能偏弱、方向混雜（E11, E14）。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 4,
    "action": "Sell",
    "expected_return_pct": -15.0,
    "confidence": 0.7,
    "rationale": "Revenue (E1) and net income (E2) declined YoY by -14% and -79%, respectively, indicating weak fundamentals. Operating cash flow (E3) also fell significantly by -26%.",
    "zh": "營收（E1）與淨利（E2）年減分別為 -14% 與 -79%，顯示基本面疲弱。營業現金流（E3）也大幅下降 -26%。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 5,
    "action": "Hold",
    "expected_return_pct": 0.0,
    "confidence": 0.45,
    "rationale": "Recent fundamentals show revenue (E1) and net income (E2) declined YoY, while operating cash flow also fell (E3). Sentiment is mixed, with positive FinBERT scores (E4-E6), but technicals show a recent negative trend in mean20 vs mean60 (E14). Macroeconomic conditions remain stable (E8-E10), but fundamentals suggest caution.",
    "zh": "近期基本面顯示營收（E1）與淨利（E2）年減，營業現金流也下降（E3）。情緒好壞參半，FinBERT 分數為正（E4-E6），但技術面顯示 20 日均線相對 60 日均線近期呈負向趨勢（E14）。總體經濟條件穩定（E8-E10），但基本面宜保持謹慎。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 6,
    "action": "Sell",
    "expected_return_pct": -15.0,
    "confidence": 0.75,
    "rationale": "Revenue (E1) and Net Income (E2) both declined sharply YoY, and Operating Cash Flow (E3) also fell. Technical indicators show a negative 20-day mean vs. 60-day mean (E14).",
    "zh": "營收（E1）與淨利（E2）年減幅度大，營業現金流（E3）也下降。技術指標顯示 20 日均線相對 60 日均線為負（E14）。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 7,
    "action": "Hold",
    "expected_return_pct": 4.0,
    "confidence": 0.65,
    "rationale": "Revenue and net income both declined YoY (E1, E2), and operating cash flow also decreased (E3), signaling weak fundamentals. However, recent sentiment remains slightly positive (E4), and technical indicators show moderate volatility but no clear direction (E14). The market context appears stable (E8, E9).",
    "zh": "營收與淨利皆年減（E1, E2），營業現金流也下降（E3），顯示基本面疲弱。不過近期情緒仍略偏正面（E4），技術指標顯示波動中等但方向不明（E14）。市場環境看來穩定（E8, E9）。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BULL",
    "round": 1,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 8.0,
    "confidence": 0.65,
    "rationale": "The sentiment analysis for the target asset shows a mean FinBERT score of 0.245621 (E4), with a positive sentiment share of 66.67% (E5), suggesting a favorable outlook. The 20-day return is 2.60% (E11), and the asset's price is above the 20-day mean (E12). While revenue and net income declined year-over-year (E1, E2), the positive sentiment and moderate technical strength (decision_calibration.technical.strength) support a bullish stance.",
    "zh": "目標資產的情緒分析顯示 FinBERT 平均分數為 0.245621（E4），正面情緒占比 66.67%（E5），暗示前景有利。20 日報酬為 2.60%（E11），價格高於 20 日均線（E12）。雖然營收與淨利年減（E1, E2），但正面情緒與適度的技術面強度（decision_calibration.technical.strength）支持看多立場。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BEAR",
    "round": 1,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -12.0,
    "confidence": 0.65,
    "rationale": "Revenue (E1) and net income (E2) declined sharply YoY, with net income down 78.9%. Operating cash flow (E3) also fell 25.7%. Despite positive sentiment (E4, E5), fundamentals show deterioration. Strongest counterpoint is positive sentiment and recent 20-day return (E11).",
    "zh": "營收（E1）與淨利（E2）年減幅度大，淨利下滑 78.9%。營業現金流（E3）也下降 25.7%。儘管情緒偏正面（E4, E5），基本面仍在惡化。最強的反方論點是正面情緒與近期 20 日報酬（E11）。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BULL",
    "round": 2,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 6.5,
    "confidence": 0.68,
    "rationale": "The target's positive sentiment (E4, E5) and recent 20-day return (E11) indicate short-term momentum. While fundamentals show revenue and net income declines (E1, E2), sentiment and technical strength (decision_calibration.technical.strength) support a bullish stance.",
    "zh": "目標的正面情緒（E4, E5）與近期 20 日報酬（E11）顯示短期動能。雖然基本面顯示營收與淨利下滑（E1, E2），但情緒與技術面強度（decision_calibration.technical.strength）支持看多立場。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BEAR",
    "round": 2,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -10.0,
    "confidence": 0.68,
    "rationale": "Revenue (E1) and net income (E2) declined sharply YoY, with net income down 78.9%. Operating cash flow (E3) also fell 25.7%. Despite positive sentiment (E4, E5), fundamentals show deterioration.",
    "zh": "營收（E1）與淨利（E2）年減幅度大，淨利下滑 78.9%。營業現金流（E3）也下降 25.7%。儘管情緒偏正面（E4, E5），基本面仍在惡化。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BULL",
    "round": 3,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 7.0,
    "confidence": 0.7,
    "rationale": "The target's positive sentiment (E4, E5) and recent 20-day return (E11) indicate short-term momentum. While fundamentals show revenue and net income declines (E1, E2), sentiment and technical strength (decision_calibration.technical.strength) support a bullish stance.",
    "zh": "目標的正面情緒（E4, E5）與近期 20 日報酬（E11）顯示短期動能。雖然基本面顯示營收與淨利下滑（E1, E2），但情緒與技術面強度（decision_calibration.technical.strength）支持看多立場。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BEAR",
    "round": 3,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -9.0,
    "confidence": 0.69,
    "rationale": "Revenue (E1) and net income (E2) declined sharply YoY, with net income down 78.9%. Operating cash flow (E3) also fell 25.7%. Despite positive sentiment (E4, E5), fundamentals show deterioration.",
    "zh": "營收（E1）與淨利（E2）年減幅度大，淨利下滑 78.9%。營業現金流（E3）也下降 25.7%。儘管情緒偏正面（E4, E5），基本面仍在惡化。"
   },
   {
    "group": "C",
    "kind": "adjudication",
    "agent": "adjudicator",
    "stance": "NEUTRAL",
    "round": null,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 5.0,
    "confidence": 0.69,
    "rationale": "The target's positive sentiment (E4, E5) and recent 20-day return (E11) indicate short-term momentum. While fundamentals show revenue and net income declines (E1, E2), sentiment and technical strength support a bullish stance.",
    "zh": "目標的正面情緒（E4, E5）與近期 20 日報酬（E11）顯示短期動能。雖然基本面顯示營收與淨利下滑（E1, E2），但情緒與技術面強度支持看多立場。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BULL",
    "round": 1,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 8.0,
    "confidence": 0.65,
    "rationale": "Positive sentiment (E4, E5) and recent 20-day return (E11) suggest upward momentum despite weak fundamentals (E1-E3).",
    "zh": "正面情緒（E4, E5）與近期 20 日報酬（E11）顯示上漲動能，儘管基本面疲弱（E1-E3）。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BEAR",
    "round": 1,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -10.0,
    "confidence": 0.75,
    "rationale": "Revenue and net income both declined YoY (E1, E2), signaling operational weakness. Operating cash flow also dropped significantly (E3).",
    "zh": "營收與淨利皆年減（E1, E2），顯示營運疲弱。營業現金流也明顯下降（E3）。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BEAR",
    "round": 2,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -7.0,
    "confidence": 0.72,
    "rationale": "The recent positive sentiment (E4, E5) and 20-day return (E11) are outweighed by significant declines in revenue (E1), net income (E2), and operating cash flow (E3), which signal deteriorating fundamentals.",
    "zh": "近期正面情緒（E4, E5）與 20 日報酬（E11）被營收（E1）、淨利（E2）與營業現金流（E3）的顯著下滑所壓過，顯示基本面惡化。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BULL",
    "round": 2,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 8.0,
    "confidence": 0.65,
    "rationale": "Positive sentiment scores (E4, E5) indicate strong market optimism, which may drive short-term returns despite weak fundamentals. The 20-day return is positive (E11), and the 20-day mean is above current price (E12), suggesting upward momentum. The previous bearish stance (E1, E2, E3) no longer holds as sentiment and technical indicators now dominate the decision calculus.",
    "zh": "正面的情緒分數（E4, E5）顯示市場樂觀，儘管基本面疲弱，仍可能推升短期報酬。20 日報酬為正（E11），且 20 日均線高於目前價格（E12），暗示上漲動能。先前看空的依據（E1, E2, E3）已不再成立，因為情緒與技術指標如今主導決策。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BULL",
    "round": 3,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 6.5,
    "confidence": 0.68,
    "rationale": "Positive sentiment (E4, E5) and recent upward momentum (E11, E12) support a bullish stance despite weak fundamentals (E1-E3). Market optimism may drive short-term returns.",
    "zh": "正面情緒（E4, E5）與近期上漲動能（E11, E12）支持看多立場，儘管基本面疲弱（E1-E3）。市場樂觀可能推升短期報酬。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BEAR",
    "round": 3,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -8.0,
    "confidence": 0.7,
    "rationale": "The significant year-over-year declines in revenue (E1), net income (E2), and operating cash flow (E3) signal deteriorating fundamentals. While sentiment remains positive (E4, E5) and the 20-day return is positive (E11), these factors are outweighed by the operational weaknesses.",
    "zh": "營收（E1）、淨利（E2）與營業現金流（E3）的顯著年減顯示基本面惡化。雖然情緒仍為正面（E4, E5）且 20 日報酬為正（E11），但這些因素被營運面的弱點所抵銷。"
   },
   {
    "group": "D",
    "kind": "adjudication",
    "agent": "adjudicator",
    "stance": "NEUTRAL",
    "round": null,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -7.0,
    "confidence": 0.7,
    "rationale": "Significant year-over-year declines in revenue (E1), net income (E2), and operating cash flow (E3) signal deteriorating fundamentals. While sentiment remains positive (E4, E5) and the 20-day return is positive (E11), these factors are outweighed by the operational weaknesses.",
    "zh": "營收（E1）、淨利（E2）與營業現金流（E3）的顯著年減顯示基本面惡化。雖然情緒仍為正面（E4, E5）且 20 日報酬為正（E11），但這些因素被營運面的弱點所抵銷。"
   }
  ],
  "decisions": {
   "A": {
    "action": "Sell",
    "expected_return_pct": -5.0,
    "confidence": 0.65,
    "rationale": "Revenue (E1) and net income (E2) declined YoY, with net income down 78.9%. Operating cash flow (E3) also dropped 25.7%. Technical indicators show mixed signals (E14), and volatility remains high (E15).",
    "vote_distribution": null,
    "zh": "營收（E1）與淨利（E2）年減，其中淨利下滑 78.9%；營業現金流（E3）亦下降 25.7%。技術指標訊號好壞參半（E14），波動率仍高（E15）。"
   },
   "B": {
    "action": "Sell",
    "expected_return_pct": -15.0,
    "confidence": 0.75,
    "rationale": "Revenue (E1) and Net Income (E2) both declined sharply YoY, and Operating Cash Flow (E3) also fell. Technical indicators show a negative 20-day mean vs. 60-day mean (E14).",
    "vote_distribution": {
     "Sell": 5,
     "Hold": 2
    },
    "zh": "營收（E1）與淨利（E2）年減幅度大，營業現金流（E3）也下降。技術指標顯示 20 日均線相對 60 日均線為負（E14）。"
   },
   "C": {
    "action": "Buy",
    "expected_return_pct": 5.0,
    "confidence": 0.69,
    "rationale": "The target's positive sentiment (E4, E5) and recent 20-day return (E11) indicate short-term momentum. While fundamentals show revenue and net income declines (E1, E2), sentiment and technical strength support a bullish stance.",
    "vote_distribution": null,
    "zh": "目標的正面情緒（E4, E5）與近期 20 日報酬（E11）顯示短期動能。雖然基本面顯示營收與淨利下滑（E1, E2），但情緒與技術面強度支持看多立場。"
   },
   "D": {
    "action": "Sell",
    "expected_return_pct": -7.0,
    "confidence": 0.7,
    "rationale": "Significant year-over-year declines in revenue (E1), net income (E2), and operating cash flow (E3) signal deteriorating fundamentals. While sentiment remains positive (E4, E5) and the 20-day return is positive (E11), these factors are outweighed by the operational weaknesses.",
    "vote_distribution": null,
    "zh": "營收（E1）、淨利（E2）與營業現金流（E3）的顯著年減顯示基本面惡化。雖然情緒仍為正面（E4, E5）且 20 日報酬為正（E11），但這些因素被營運面的弱點所抵銷。"
   }
  },
  "outcome": {
   "A": {
    "action": "Sell",
    "move_pct": -30.5,
    "net_return_pct": 30.3,
    "correct": true,
    "entry_date": "2024-04-01",
    "maturity_date": "2024-06-26"
   },
   "B": {
    "action": "Sell",
    "move_pct": -30.5,
    "net_return_pct": 30.3,
    "correct": true,
    "entry_date": "2024-04-01",
    "maturity_date": "2024-06-26"
   },
   "C": {
    "action": "Buy",
    "move_pct": -30.5,
    "net_return_pct": -30.8,
    "correct": false,
    "entry_date": "2024-04-01",
    "maturity_date": "2024-06-26"
   },
   "D": {
    "action": "Sell",
    "move_pct": -30.5,
    "net_return_pct": 30.3,
    "correct": true,
    "entry_date": "2024-04-01",
    "maturity_date": "2024-06-26"
   }
  }
 },
 {
  "ticker": "AAPL",
  "analysis_date": "2023-03-31",
  "protocol": "v3-1002.3",
  "research": {
   "technical": {
    "status": "complete",
    "summary": "As of 2023-03-30, the technical indicators for the asset show a return20 of 0.11274083689755776 (E11), a price_vs_mean20 of 0.04476410234525896 (E12), a price_vs_mean60 of 0.10041812888105461 (E13), a mean20_vs_mean60 of 0.05326946667756394 (E14), and an annualized volatility60_annual of 0.22935616314385554 (E15).",
    "zh": "截至 2023-03-30，技術指標顯示：20 日報酬 return20 為 0.11274083689755776（E11），價格相對 20 日均線 price_vs_mean20 為 0.04476410234525896（E12），價格相對 60 日均線 price_vs_mean60 為 0.10041812888105461（E13），20 日均線相對 60 日均線 mean20_vs_mean60 為 0.05326946667756394（E14），60 日年化波動率 volatility60_annual 為 0.22935616314385554（E15）。"
   },
   "fundamental": {
    "status": "complete",
    "summary": "SEC 財務欄位採同概念、相近期間配對；精確數值、單位與申報期間保留於 claim_map 及原始引用證據。"
   },
   "sentiment": {
    "status": "complete",
    "summary": "The sentiment analysis for the target asset from December 31, 2022, to March 30, 2023, indicates a slightly negative mean sentiment score (E5). Approximately 29.61% of the sentiment is classified as positive (E6), while 22.73% is classified as negative (E7).",
    "zh": "針對目標資產，2022-12-31 至 2023-03-30 的情緒分析顯示平均情緒分數略為負向（E5）。約 29.61% 的情緒被歸為正面（E6），22.73% 為負面（E7）。"
   },
   "macro": {
    "status": "complete",
    "summary": "As of 2023-03-30, the unemployment rate (UNRATE) is reported at 3.6 (E8), the federal funds rate (FEDFUNDS) is 4.57 (E9), and the consumer price index for all urban consumers, seasonally adjusted (CPIAUCSL) is 301.648 (E10).",
    "zh": "截至 2023-03-30，失業率（UNRATE）為 3.6（E8），聯邦基金利率（FEDFUNDS）為 4.57（E9），都市消費者物價指數（CPIAUCSL，經季節調整）為 301.648（E10）。"
   }
  },
  "evidence": [
   {
    "id": "E1",
    "domain": "fundamental",
    "claim": "LiabilitiesToAssets: Assets=346747000000 USD; Liabilities=290020000000 USD; liabilities_to_assets_pct=83.640233; period_end=2022-12-31; form=10-Q; filed=2023-02-03",
    "label_zh": "負債占資產比 83.640233%"
   },
   {
    "id": "E2",
    "domain": "fundamental",
    "claim": "Revenue: current=117154000000 USD; current_period=2022-09-25–2022-12-31; period_days=97; prior=123945000000 USD; prior_period=2021-09-26–2021-12-25; year_over_year_change_pct=-5.479043; current_form=10-Q; current_filed=2023-02-03",
    "label_zh": "營收年增率 -5.479043%"
   },
   {
    "id": "E3",
    "domain": "fundamental",
    "claim": "NetIncomeLoss: current=29998000000 USD; current_period=2022-09-25–2022-12-31; period_days=97; prior=34630000000 USD; prior_period=2021-09-26–2021-12-25; year_over_year_change_pct=-13.375686; current_form=10-Q; current_filed=2023-02-03",
    "label_zh": "淨利年增率 -13.375686%"
   },
   {
    "id": "E4",
    "domain": "fundamental",
    "claim": "OperatingCashFlow: current=34005000000 USD; current_period=2022-09-25–2022-12-31; period_days=97; prior=46966000000 USD; prior_period=2021-09-26–2021-12-25; year_over_year_change_pct=-27.596559; current_form=10-Q; current_filed=2023-02-03",
    "label_zh": "營業現金流年增率 -27.596559%"
   },
   {
    "id": "E5",
    "domain": "sentiment",
    "claim": "sentiment_target_mean = -0.005779",
    "label_zh": "目標資產情緒平均 -0.005779"
   },
   {
    "id": "E6",
    "domain": "sentiment",
    "claim": "sentiment_target_positive_share = 0.296117",
    "label_zh": "目標資產正面情緒占比 0.296117"
   },
   {
    "id": "E7",
    "domain": "sentiment",
    "claim": "sentiment_target_negative_share = 0.227346",
    "label_zh": "目標資產負面情緒占比 0.227346"
   },
   {
    "id": "E8",
    "domain": "macro",
    "claim": "UNRATE: 3.6，觀測期間 2023-02-01，截至 2023-03-30 可知版本",
    "label_zh": "失業率 3.6"
   },
   {
    "id": "E9",
    "domain": "macro",
    "claim": "FEDFUNDS: 4.57，觀測期間 2023-02-01，截至 2023-03-30 可知版本",
    "label_zh": "聯邦基金利率 4.57"
   },
   {
    "id": "E10",
    "domain": "macro",
    "claim": "CPIAUCSL: 301.648，觀測期間 2023-02-01，截至 2023-03-30 可知版本",
    "label_zh": "消費者物價指數 301.648"
   },
   {
    "id": "E11",
    "domain": "technical",
    "claim": "return20 = 0.112741",
    "label_zh": "20 日報酬 0.112741"
   },
   {
    "id": "E12",
    "domain": "technical",
    "claim": "price_vs_mean20 = 0.044764",
    "label_zh": "價格相對 20 日均線 0.044764"
   },
   {
    "id": "E13",
    "domain": "technical",
    "claim": "price_vs_mean60 = 0.100418",
    "label_zh": "價格相對 60 日均線 0.100418"
   },
   {
    "id": "E14",
    "domain": "technical",
    "claim": "mean20_vs_mean60 = 0.053269",
    "label_zh": "20 日均線相對 60 日均線 0.053269"
   },
   {
    "id": "E15",
    "domain": "technical",
    "claim": "volatility60_annual = 0.229356",
    "label_zh": "60 日年化波動率 0.229356"
   }
  ],
  "records": [
   {
    "group": "A",
    "kind": "decision",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": null,
    "action": "Hold",
    "expected_return_pct": 2.0,
    "confidence": 0.55,
    "rationale": "Recent revenue and net income have declined year over year (E2, E3), while operating cash flow has dropped significantly (E4). Technical indicators show a positive return20 (E11) and upward trend (E14), but sentiment remains neutral with no strong directional bias (E5, E6).",
    "zh": "近期營收與淨利年減（E2, E3），營業現金流大幅下降（E4）。技術指標顯示 return20 為正（E11）且趨勢向上（E14），但情緒中性，沒有明確的方向偏向（E5, E6）。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 1,
    "action": "Hold",
    "expected_return_pct": 2.5,
    "confidence": 0.65,
    "rationale": "Revenue (E2) and net income (E3) declined year over year, suggesting underlying performance challenges. Technical indicators show a recent positive return20 (E11) and upward direction (decision_calibration.technical.direction), but sentiment is neutral with a weak mean score (E5).",
    "zh": "營收（E2）與淨利（E3）年減，顯示本業表現面臨挑戰。技術指標顯示近期 return20 為正（E11）且方向向上（decision_calibration.technical.direction），但情緒中性、平均分數偏弱（E5）。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 2,
    "action": "Hold",
    "expected_return_pct": 1.5,
    "confidence": 0.55,
    "rationale": "The technical indicators (E11, E14) suggest a strong upward trend (return20 = 0.112741 and mean20_vs_mean60 = 0.053269). However, fundamental evidence (E2, E3, E4) shows revenue (-5.48%), net income (-13.38%), and operating cash flow (-27.6%) all declined year-over-year, raising concerns.",
    "zh": "技術指標（E11, E14）顯示強勁上升趨勢（return20 = 0.112741，mean20_vs_mean60 = 0.053269）。然而基本面證據（E2, E3, E4）顯示營收（-5.48%）、淨利（-13.38%）與營業現金流（-27.6%）皆年減，令人擔憂。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 3,
    "action": "Hold",
    "expected_return_pct": 1.5,
    "confidence": 0.55,
    "rationale": "Technical indicators suggest upward bias but with mixed sentiment. Revenue and net income declined year-over-year (E2, E3).",
    "zh": "技術指標偏向上行，但情緒好壞參半。營收與淨利年減（E2, E3）。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 4,
    "action": "Hold",
    "expected_return_pct": 2.25,
    "confidence": 0.6,
    "rationale": "The technical indicators suggest an upward trend with a strong 20-day return of 11.27% (E11) and the price above both 20 and 60-day moving averages (E12, E13). However, the fundamental data shows revenue and net income declined year-over-year (E2, E3), and operating cash flow dropped significantly (E4). The technical strength and median return are positive, but the fundamental weakness limits confidence in a Buy decision.",
    "zh": "技術指標顯示上升趨勢，20 日報酬強勁達 11.27%（E11），價格高於 20 日與 60 日均線（E12, E13）。然而基本面資料顯示營收與淨利年減（E2, E3），營業現金流也大幅下降（E4）。技術面強度與報酬中位數為正，但基本面疲弱限制了對買進決策的信心。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 5,
    "action": "Hold",
    "expected_return_pct": 2.25,
    "confidence": 0.55,
    "rationale": "The technical indicators suggest a slightly upward trend with strong 20-day returns (E11) but weak fundamental performance, including declining revenue (E2), net income (E3), and operating cash flow (E4). Sentiment is neutral, and volatility remains moderate.",
    "zh": "技術指標顯示略微上升的趨勢，20 日報酬強勁（E11），但基本面表現疲弱，包括營收（E2）、淨利（E3）與營業現金流（E4）下滑。情緒中性，波動率中等。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 6,
    "action": "Hold",
    "expected_return_pct": 2.25,
    "confidence": 0.6,
    "rationale": "The technical indicators show a recent upward trend and strong momentum (E11, E14). However, the fundamental data shows declining revenue (E2), net income (E3), and operating cash flow (E4) year over year, which could limit upside potential. Given mixed signals, a neutral position is prudent.",
    "zh": "技術指標顯示近期上升趨勢與強勁動能（E11, E14）。然而基本面資料顯示營收（E2）、淨利（E3）與營業現金流（E4）年減，可能限制上行空間。在訊號混雜下，採中性部位較為審慎。"
   },
   {
    "group": "B",
    "kind": "sample",
    "agent": "decision",
    "stance": "NEUTRAL",
    "round": null,
    "sample": 7,
    "action": "Hold",
    "expected_return_pct": 2.25,
    "confidence": 0.6,
    "rationale": "The technical indicators show an upward direction with strong strength. The recent 20-day return is positive. However, there are concerns regarding declining revenue, net income, and operating cash flow, which could affect future performance.",
    "zh": "技術指標顯示方向向上且強度強。近期 20 日報酬為正。然而，營收、淨利與營業現金流下滑令人擔憂，可能影響未來表現。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BULL",
    "round": 1,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 7.5,
    "confidence": 0.65,
    "rationale": "The technical indicators show a strong upward trend (E14) with a 20-day return of 11.27% (E11), suggesting positive momentum. The liabilities-to-assets ratio is 83.64% (E1), indicating manageable leverage. Despite a decline in revenue and net income year-over-year (E2, E3), the stock's recent performance and technical strength justify a bullish stance.",
    "zh": "技術指標顯示強勁上升趨勢（E14），20 日報酬為 11.27%（E11），暗示正向動能。負債占資產比為 83.64%（E1），顯示槓桿尚可控。儘管營收與淨利年減（E2, E3），股價近期表現與技術面強度仍支持看多立場。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BEAR",
    "round": 1,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -8.0,
    "confidence": 0.65,
    "rationale": "Revenue (E2) and net income (E3) both declined YoY, while operating cash flow (E4) fell sharply by 27.6%. High liabilities-to-assets ratio (E1) suggests financial leverage risk. Technicals (E11-E15) show recent strength, but fundamentals indicate weakening trends.",
    "zh": "營收（E2）與淨利（E3）皆年減，營業現金流（E4）更大幅下降 27.6%。高負債占資產比（E1）暗示財務槓桿風險。技術面（E11-E15）顯示近期走強，但基本面顯示趨勢轉弱。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BULL",
    "round": 2,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 6.0,
    "confidence": 0.68,
    "rationale": "The technical indicators (E11, E14) show strong upward momentum with a 20-day return of 11.27% and mean20 vs mean60 of 5.3%. Despite revenue and net income declines (E2, E3), the stock's recent performance and technical strength justify a bullish stance.",
    "zh": "技術指標（E11, E14）顯示強勁上升動能，20 日報酬為 11.27%，20 日均線相對 60 日均線為 5.3%。儘管營收與淨利下滑（E2, E3），股價近期表現與技術面強度仍支持看多立場。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BEAR",
    "round": 2,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -6.0,
    "confidence": 0.6,
    "rationale": "Revenue (E2) and net income (E3) declined YoY, and operating cash flow (E4) dropped sharply by 27.6%. These fundamentals signal weakening business performance, which could outweigh technical strength (E11-E15).",
    "zh": "營收（E2）與淨利（E3）年減，營業現金流（E4）大幅下降 27.6%。這些基本面顯示業務表現轉弱，可能壓過技術面強度（E11-E15）。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BULL",
    "round": 3,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 6.5,
    "confidence": 0.7,
    "rationale": "The technical indicators (E11, E14) show strong upward momentum with a 20-day return of 11.27% and mean20 vs mean60 of 5.3%. Despite revenue and net income declines (E2, E3), the stock's recent performance and technical strength justify a bullish stance.",
    "zh": "技術指標（E11, E14）顯示強勁上升動能，20 日報酬為 11.27%，20 日均線相對 60 日均線為 5.3%。儘管營收與淨利下滑（E2, E3），股價近期表現與技術面強度仍支持看多立場。"
   },
   {
    "group": "C",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BEAR",
    "round": 3,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -7.0,
    "confidence": 0.62,
    "rationale": "Revenue (E2) and net income (E3) declined YoY, and operating cash flow (E4) dropped sharply by 27.6%. These fundamentals signal weakening business performance, which could outweigh technical strength (E11-E15).",
    "zh": "營收（E2）與淨利（E3）年減，營業現金流（E4）大幅下降 27.6%。這些基本面顯示業務表現轉弱，可能壓過技術面強度（E11-E15）。"
   },
   {
    "group": "C",
    "kind": "adjudication",
    "agent": "adjudicator",
    "stance": "NEUTRAL",
    "round": null,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 6.0,
    "confidence": 0.68,
    "rationale": "Technical indicators (E11, E14) show strong upward momentum with a 20-day return of 11.27% and mean20 vs mean60 of 5.3%. Despite revenue and net income declines (E2, E3), the stock's recent performance and technical strength justify a bullish stance.",
    "zh": "技術指標（E11, E14）顯示強勁上升動能，20 日報酬為 11.27%，20 日均線相對 60 日均線為 5.3%。儘管營收與淨利下滑（E2, E3），股價近期表現與技術面強度仍支持看多立場。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BULL",
    "round": 1,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 7.5,
    "confidence": 0.65,
    "rationale": "Recent 20-day return is positive (E11), and price is above both 20-day and 60-day moving averages (E12, E13). The 20-day mean is rising relative to the 60-day mean (E14), suggesting upward momentum. While revenue and net income declined year-over-year (E2, E3), the technical strength and volatility suggest potential for recovery.",
    "zh": "近期 20 日報酬為正（E11），價格高於 20 日與 60 日均線（E12, E13）。20 日均線相對 60 日均線上升（E14），暗示上漲動能。雖然營收與淨利年減（E2, E3），但技術面強度與波動顯示有復甦潛力。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BEAR",
    "round": 1,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -8.0,
    "confidence": 0.75,
    "rationale": "Revenue (E2) and net income (E3) both declined YoY, while operating cash flow (E4) dropped sharply. High liabilities-to-assets ratio (E1) signals financial risk. Technicals (E11-E15) suggest recent strength, but fundamentals are deteriorating.",
    "zh": "營收（E2）與淨利（E3）皆年減，營業現金流（E4）大幅下降。高負債占資產比（E1）暗示財務風險。技術面（E11-E15）顯示近期走強，但基本面正在惡化。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BEAR",
    "round": 2,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -5.0,
    "confidence": 0.7,
    "rationale": "The recent 20-day return is positive (E11), but revenue, net income, and operating cash flow all declined year-over-year (E2, E3, E4), signaling deteriorating fundamentals. The liabilities-to-assets ratio is high at 83.64% (E1), raising concerns about financial leverage. While technical indicators suggest upward momentum, the bearish stance is supported by weak fundamental performance and high volatility (E15). The claim in round 1 that 'technical strength and volatility suggest potential for recovery' (rebutted_claim) no longer holds under the bearish stance, as the fundamental declines outweigh the technical positives.",
    "zh": "近期 20 日報酬為正（E11），但營收、淨利與營業現金流皆年減（E2, E3, E4），顯示基本面惡化。負債占資產比高達 83.64%（E1），引發對財務槓桿的疑慮。雖然技術指標暗示上行動能，但疲弱的基本面表現與高波動（E15）支持看空立場。第一輪提出的「技術面強度與波動顯示有復甦潛力」（rebutted_claim）在看空立場下已不成立，因為基本面的下滑壓過了技術面的正面因素。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BULL",
    "round": 2,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 6.0,
    "confidence": 0.65,
    "rationale": "Recent technical indicators (E11, E14) show strong upward momentum, with return20 at 11.27% and mean20 above mean60 by 5.33%. While fundamentals (E2, E3, E4) show declines, technical strength may drive short-term gains. Round-1 claim 'fundamentals are deteriorating' no longer holds as technicals now dominate the near-term outlook.",
    "zh": "近期技術指標（E11, E14）顯示強勁上升動能，return20 為 11.27%，20 日均線高於 60 日均線 5.33%。雖然基本面（E2, E3, E4）下滑，但技術面強度可能推動短期獲利。第一輪的主張「基本面正在惡化」已不再成立，因為技術面如今主導近期展望。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-a",
    "stance": "BULL",
    "round": 3,
    "sample": null,
    "action": "Buy",
    "expected_return_pct": 6.5,
    "confidence": 0.68,
    "rationale": "Technical indicators show strong upward momentum with a 20-day return of 11.27% (E11) and the price above both 20-day and 60-day moving averages (E12, E13). The 20-day mean is rising relative to the 60-day mean (E14), reinforcing bullish technicals. While fundamentals (E2, E3, E4) show declines, technical strength may drive short-term gains.",
    "zh": "技術指標顯示強勁上升動能，20 日報酬為 11.27%（E11），價格高於 20 日與 60 日均線（E12, E13）。20 日均線相對 60 日均線上升（E14），強化了偏多的技術面。雖然基本面（E2, E3, E4）下滑，技術面強度可能推動短期獲利。"
   },
   {
    "group": "D",
    "kind": "debate",
    "agent": "agent-b",
    "stance": "BEAR",
    "round": 3,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -6.0,
    "confidence": 0.72,
    "rationale": "Fundamental indicators (E2, E3, E4) show year-over-year declines in revenue, net income, and operating cash flow, signaling deteriorating business performance. The liabilities-to-assets ratio is high at 83.64% (E1), raising concerns about financial leverage. While technical indicators (E11, E14) suggest upward momentum, the bearish stance is supported by weak fundamentals and high volatility (E15).",
    "zh": "基本面指標（E2, E3, E4）顯示營收、淨利與營業現金流皆年減，顯示業務表現惡化。負債占資產比高達 83.64%（E1），引發對財務槓桿的疑慮。雖然技術指標（E11, E14）暗示上行動能，但疲弱的基本面與高波動（E15）支持看空立場。"
   },
   {
    "group": "D",
    "kind": "adjudication",
    "agent": "adjudicator",
    "stance": "NEUTRAL",
    "round": null,
    "sample": null,
    "action": "Sell",
    "expected_return_pct": -6.0,
    "confidence": 0.72,
    "rationale": "Fundamental indicators (E2, E3, E4) show year-over-year declines in revenue, net income, and operating cash flow, signaling deteriorating business performance. The liabilities-to-assets ratio is high at 83.64% (E1), raising concerns about financial leverage. While technical indicators (E11, E14) suggest upward momentum, the bearish stance is supported by weak fundamentals and high volatility (E15).",
    "zh": "基本面指標（E2, E3, E4）顯示營收、淨利與營業現金流皆年減，顯示業務表現惡化。負債占資產比高達 83.64%（E1），引發對財務槓桿的疑慮。雖然技術指標（E11, E14）暗示上行動能，但疲弱的基本面與高波動（E15）支持看空立場。"
   }
  ],
  "decisions": {
   "A": {
    "action": "Hold",
    "expected_return_pct": 2.0,
    "confidence": 0.55,
    "rationale": "Recent revenue and net income have declined year over year (E2, E3), while operating cash flow has dropped significantly (E4). Technical indicators show a positive return20 (E11) and upward trend (E14), but sentiment remains neutral with no strong directional bias (E5, E6).",
    "vote_distribution": null,
    "zh": "近期營收與淨利年減（E2, E3），營業現金流大幅下降（E4）。技術指標顯示 return20 為正（E11）且趨勢向上（E14），但情緒中性，沒有明確的方向偏向（E5, E6）。"
   },
   "B": {
    "action": "Hold",
    "expected_return_pct": 2.5,
    "confidence": 0.65,
    "rationale": "Revenue (E2) and net income (E3) declined year over year, suggesting underlying performance challenges. Technical indicators show a recent positive return20 (E11) and upward direction (decision_calibration.technical.direction), but sentiment is neutral with a weak mean score (E5).",
    "vote_distribution": {
     "Hold": 7
    },
    "zh": "營收（E2）與淨利（E3）年減，顯示本業表現面臨挑戰。技術指標顯示近期 return20 為正（E11）且方向向上（decision_calibration.technical.direction），但情緒中性、平均分數偏弱（E5）。"
   },
   "C": {
    "action": "Buy",
    "expected_return_pct": 6.0,
    "confidence": 0.68,
    "rationale": "Technical indicators (E11, E14) show strong upward momentum with a 20-day return of 11.27% and mean20 vs mean60 of 5.3%. Despite revenue and net income declines (E2, E3), the stock's recent performance and technical strength justify a bullish stance.",
    "vote_distribution": null,
    "zh": "技術指標（E11, E14）顯示強勁上升動能，20 日報酬為 11.27%，20 日均線相對 60 日均線為 5.3%。儘管營收與淨利下滑（E2, E3），股價近期表現與技術面強度仍支持看多立場。"
   },
   "D": {
    "action": "Sell",
    "expected_return_pct": -6.0,
    "confidence": 0.72,
    "rationale": "Fundamental indicators (E2, E3, E4) show year-over-year declines in revenue, net income, and operating cash flow, signaling deteriorating business performance. The liabilities-to-assets ratio is high at 83.64% (E1), raising concerns about financial leverage. While technical indicators (E11, E14) suggest upward momentum, the bearish stance is supported by weak fundamentals and high volatility (E15).",
    "vote_distribution": null,
    "zh": "基本面指標（E2, E3, E4）顯示營收、淨利與營業現金流皆年減，顯示業務表現惡化。負債占資產比高達 83.64%（E1），引發對財務槓桿的疑慮。雖然技術指標（E11, E14）暗示上行動能，但疲弱的基本面與高波動（E15）支持看空立場。"
   }
  },
  "outcome": {
   "A": {
    "action": "Hold",
    "move_pct": 15.3,
    "net_return_pct": 0.0,
    "correct": null,
    "entry_date": "2023-04-03",
    "maturity_date": "2023-06-29"
   },
   "B": {
    "action": "Hold",
    "move_pct": 15.3,
    "net_return_pct": 0.0,
    "correct": null,
    "entry_date": "2023-04-03",
    "maturity_date": "2023-06-29"
   },
   "C": {
    "action": "Buy",
    "move_pct": 15.3,
    "net_return_pct": 14.8,
    "correct": true,
    "entry_date": "2023-04-03",
    "maturity_date": "2023-06-29"
   },
   "D": {
    "action": "Sell",
    "move_pct": 15.3,
    "net_return_pct": -15.7,
    "correct": false,
    "entry_date": "2023-04-03",
    "maturity_date": "2023-06-29"
   }
  }
 }
];
