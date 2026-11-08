# v11 互動研究故事

正式原始碼是 `site/index.html`、`site/story.css`、`site/story.js`；沿用原研究小屋的奶油／薄荷／粉紅色與貓咪。既有 `site/demo` 保留作逐輪輸出展示，並回連同一首頁與 v11 PDF。未建立新的 Sites 專案。

- 報告來源：`report/application-meeting-20261020_v11.tex`、同名 PDF。網站 `site/sources` 保存完全相同的來源副本，避免誤連公開舊版。
- 逐案來源：`site/story-cases.json`，16 個 C/D 分歧案例，取自 180 案凍結證據包。JSON 內含封存、manifest、逐案 SHA-256 與候選決策口徑；C 正確 11、D 正確 5。
- 價格變動是標的開盤至開盤、60 交易日、未扣成本，不是策略淨報酬。其餘案例論點沒有自動推演；只展示報告兩例摘要。
- 頁面只讀取同站 JSON；不呼叫模型、行情、交易或新實驗。
- `site/story/` 是原私人 Sites 的獨立來源 checkout，`dist` 是上述正式來源及 demo/app/sources 的發布副本，請勿分開編輯兩套敘事。Sites ID 保留原 `appgprj_6ad646b63ea88191b7f5c93924fa9962`。

驗收：JavaScript 語法、git diff 空白檢查；封存／manifest／16 個 job 的 SHA-256、PDF 逐位元一致；瀏覽器猜選、Enter 揭曉、D 第二輪、準確率／Sharpe、AAPL／INTC、股票與正確組篩選；390px 無橫向溢出，焦點可見、無前端錯誤。減少動態由 prefers-reduced-motion CSS 支援。
