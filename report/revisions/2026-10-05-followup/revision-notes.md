# 2026-10-05 第二輪修訂

依使用者採納項目更新主報告與申請版。`before/` 保存本輪修改前的 TEX、BIB、PDF；未更動實驗程式、未重跑模型或提交 Git。

## 已完成

- 明分案例數 `n_case=180`、分析日群聚數 20、Sharpe 日報酬面板長度 T；另交代 Ledoit–Wolf 每次重抽樣長度 `20 floor(T/20)`。不把案例數當成日資料筆數。
- 將 D/C 比較明定為 composite-protocol estimand，涵蓋交換立場、交換輪隔離對手、強制引用與相應驗證／重試。未消融，不歸因於單一設計要素。
- RQ2 的一致判準明定為兩模型 D−C 準確率差同號，零差另列；不要求最佳組相同，也不推論效果相等或模型與機制無交互作用。RQ3 保留月度設計，明列未執行／後續研究。
- 限縮研究缺口：截至 2026-10-05，在本文列舉文獻及本次核對的 arXiv、OpenReview、ACL Anthology 範圍內未見相同條件的直接投資績效比較。不是系統性回顧或首次研究宣稱。
- 補等效／非劣性界值的必要性，保留既有準確率差 CI [-7.2,+0.6] 百分點與 Sharpe 差 CI [-0.47,+0.36]；沒有事前實務界值，未事後宣稱等效或非劣。
- 增加條件式 MDE 敏感度診斷。固定觀察到的 K=16 不一致案例、假設案例獨立，單一準確率端點雙尾 alpha=.05 的拒絕集合為 X<=3 或 X>=13。解二項分配精確檢定力為 .8 的 q 得 .8529181215，期望差 6.2740999373 百分點，正文四捨五入為 6.3。它不是事前規劃或整體研究 MDE；未納入日期依賴、Holm 或 Sharpe 聯合門檻。`conditional-mde.json` 保存計算假設與結果。
- 修正兩版圖 1 caption，列出可見歷史、C/D 記憶權限、D 交換輪隔離，以及 qwen B=.8、其餘=.2 的溫度設定。
- 13 筆 arXiv 預印本從 `@article` 改為 `@misc`，補官方 arXiv DOI、URL、可見 DOI；不填不存在的期刊卷期頁碼。保留原引用年份。Liang、PROClaim 與 Kong 明記 v1，避免本輪 metadata 整理混用後續版本的作者順序或定量內容。
- 摘要維持「兩端點差異皆正且 Holm 後顯著」為判定規則，結果仍明列未達判準；未把措辭問題說成數值矛盾。

## 使用者指定跳過

使用者對新版 v3-1002.3/b1da80ee 完整逐案資料來源問題回覆「跳過這個」。本輪停止查找，不從舊協議反推新版 T 或補造完整 16 案附錄。正文明列 T 實際筆數未核對，以及兩個事後選例不能代表全部分歧案例。原主要結果與 CI 沿用報告，沒有聲稱重新核實新版原始資料。

## Metadata 來源

逐筆核對 arXiv 官方頁面之 DOI；原文內容的版本核对承接第一輪修訂。

- https://arxiv.org/abs/2412.20138
- https://arxiv.org/abs/2305.14325
- https://arxiv.org/abs/2305.19118v1
- https://arxiv.org/abs/1908.10063
- https://arxiv.org/abs/2402.06698
- https://arxiv.org/abs/2309.17322
- https://arxiv.org/abs/2311.17371
- https://arxiv.org/abs/2502.08788
- https://arxiv.org/abs/2603.28488v1
- https://arxiv.org/abs/2304.07619
- https://arxiv.org/abs/2307.10485
- https://arxiv.org/abs/2407.18957
- https://arxiv.org/abs/2602.14233v1

## 驗證

- Codex 原生編輯器已送出開啟兩份 TEX 的請求；原生編譯器仍回傳環境錯誤 `Unable to find standard directories for platform`，不據此宣稱成功。
- 使用既有 MiKTeX、禁止自動安裝，完成 BibTeX 與 pdfLaTeX 交叉引用更新。兩版均無 undefined citations/references、missing characters、overfull boxes 或 BibTeX warnings；metadata warnings 從 26 降為 0。
- 主報告 28 頁；申請版參考文獻局部行距調整為 1.3，避免單筆文獻獨占尾頁。頁數與 SHA-256 以 `qa/verification.json` 為準。
- 全頁縮圖與新增統計公式／MDE、圖 caption、參考文獻重點頁目視檢查；`qa/` 保存檢查產物。
