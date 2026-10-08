# 2026-10-05 報告修訂紀錄

依使用者貼上的完整 review 修訂 `stance-shift-ssrn.tex`，並同步 `application.tex` 的共用方法與結論。修改前的兩份 TEX、PDF 與 references.bib 保存於 `before/`。原始實驗程式、協議、資料庫與登記未修改，未提交 Git，未啟動 GPU 或付費模型實驗。

## 已完成

- 中英文摘要及結論統一為規則鎖定後對既有樣本的回溯比較；移除完全排除前視偏差、因果機制、模型能力與資訊瓶頸的過強推論。
- 保留 RQ2 跨模型、RQ3 月度的順序；標示前者探索性、後者未執行，補上 RQ2 回答與一致性的有限定義。
- 補機制動機與工作假設 H1。H1 是本次論述形式化，未將原有雙尾檢定改為 review 建議的單尾檢定，未事後改動 Holm 規則。
- 補日序列、252 年化、零無風險基準、累積報酬、回撤、學生化區塊自助法與種子定義；修正方向正確採未扣成本價格變動、淨報酬另計的區別。
- 「總報酬」依程式改為「累積報酬」，不是 review 所提「平均 60 日報酬」。程式 `backtest.metrics` 實際使用日序列的複利乘積，`reporting` 以 1/180 固定案例權重對齊每日序列。
- 持有機會成本補百分點單位及公式，不將其當成可實現獲利。主表增加一律看多方向參照，但明示只與 C／D 同基底。
- 補目的性選樣與 ASTS／LLY／INTC 的資料覆蓋理由，不杜撰初始候選池或事前市值排名；刪除未使用的訓練／驗證／測試切分敘述。
- 明列 D 的原文引用驗證、重試負擔，以及名目呼叫對齊不代表实际呼叫／token 成本對齊。
- 修正 16 案中的 12 案賣出與 5／11 正確數的混淆；增加第二案例表，使兩個案例均有表格；標示事後選例，不推因果。
- 從文中既有總數代數重建 C／D 混淆分布，標示不是獨立逐案稽核。下跌精確率 C=14/35、D=15/43；不概括稱完全無辨識力。
- 檢定力段補條件於 16 個不一致案例的精確拒絕門檻：13 對 3，雙尾 p=0.02127075、差異 5.56 百分點。此為診斷，未冒稱 80% power 的事前 MDE，也未將未顯著解讀為等效。
- 補既有前導探針的實際結果及適用範圍。qwen 無資料回想 63 題；匿名辨識 6/18，但使用舊協議 39f71a9c，不作新版 180 案已排除汙染之證据。開放式回答不直接採九選一的 11.1% 作虛無基準。
- 壓縮守門員敘述，明列記憶模組未消融；UI 與工具表保留作系統貢獻的說明。
- 主報告封面改為 115 年十月；申請版原封面已是十月。

## 仍需新版原始匯出或新實驗

1. A／B 出手子集的一律看多準確率，以及 Gemini A／B 覆蓋率。不能從四捨五入準確率猜分母。
2. Gemini 3 Flash 完整 API model ID、存取日期、實際溫度、種子是否套用，以及兩模型的逐案報告雜湊。本文不將相同資料集等同於相同生成報告。
3. 排除 37 案的完整名單與規則，及其與 36 個僅有 API 標題案例、MCD 兩則新聞案例的重疊關係。未推定 36+1 就是可驗證的分組。
4. 新版報告匿名辨識／結果記憶探針；不同種子的 C 對 C′ 重跑；D 要素消融；新樣本的事前檢定力規劃；月度實驗。
5. FinBERT revision 與行情調整版本的完整可重現性紀錄。

本次未取得與 b1da80ee 同身分的完整 180 案逐案資料，因此既有主要結果數值保持不變。可讀的 localhost:8000 是舊 v3-0927.2 服務，列出的 qwen 完整批次為 v3-0929.1／39f71a9c；它不作新版結果的重新驗證。已存在的 ZIP 亦是舊協議，不混用。混淆表僅依本文既有彙總數重建。

## 文獻核對

- [Lord, Lepper & Preston (1984) 原文](https://www.researchgate.net/profile/Mark-Lepper-2/publication/16669522_Considering_the_Opposite_A_Corrective_Strategy_for_Social_Judgment/links/56107d7508ae48337519fedb/Considering-the-Opposite-A-Corrective-Strategy-for-Social-Judgment.pdf)：兩項人類社會判斷實驗；本文將其作機制動機，不當成 LLM 預測績效證據。
- [Huang et al.，ICLR 2024](https://arxiv.org/abs/2310.01798)：無外部回饋的內生自我修正在其推理設定中可能失效；新增 bibliography 條目。
- [PROClaim 原文 Table 5 與 Appendix P](https://arxiv.org/html/2603.28488v1)：120 claims 的完整系統 81.67%、無交換 77.50%，約 4.2 百分點；210.9K／18.9K tokens 約 11.16 倍，是整套系統相對 Standard MAD 的成本，不是交換本身的單獨成本。原數值保留。
- [Kong et al. 原文 Figure 2 與 Table 1](https://arxiv.org/html/2602.14233v1)：164 篇與五類偏誤均有原文支持，保留。

## 驗證

- Codex 內建 LaTeX 編譯器回傳環境錯誤 `Unable to find standard directories for platform`，未以它宣稱成功；編輯器保持開啟。
- 使用既有 MiKTeX pdfLaTeX／BibTeX 編譯，禁止自動安裝，未安裝任何 TeX 套件。
- 主報告 27 頁、申請版 16 頁；已完成引用、標籤與編譯日誌檢查，無 undefined citations、undefined references、missing characters 或 overfull boxes。
- 目視檢查全頁縮圖，以及新增公式、主結果表、跨模型表、混淆表與前導探針頁；修正申請版末頁只剩免責句的排版。
- `qa/verification.json` 保存最終 PDF SHA-256 與檢查結果。編譯成功不等於新版原始實驗已重新驗證。
