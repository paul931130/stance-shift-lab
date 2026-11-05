# 在瀏覽器分析自己的股票

不用在自己的電腦安裝 Python、Docker 或開本機網址。研究台會在你自己的 GitHub Codespace 執行，透過私人 HTTPS 網址操作。

如果只想看系統如何運作，直接 [播放真實案例](https://paul931130.github.io/stance-shift-lab/demo/)，不用建立 Codespace。案例展示是既有結果的回放，不能新增分析。

## 1. 建立自己的研究台

[建立雲端研究台 →](https://codespaces.new/paul931130/stance-shift-lab)

1. 登入自己的 GitHub 帳號，確認帳號可使用 Codespaces，再按 **Create codespace**。運算與儲存使用你自己的 Codespaces 額度；模型服務另外依供應商計費。
2. 等待環境建置與研究台啟動。第一次需要下載套件與建立容器，所需時間依網路與主機而異。
3. 瀏覽器版 VS Code 開好後，研究台會嘗試自動開啟。若沒有開啟，進下方 **Ports／連接埠**，找到 **8000／研究台**，按 **Open in Browser／在瀏覽器開啟**。

網址會是 `https://<你的 codespace 名稱>-8000.app.github.dev`，不是 `localhost`。保持連接埠為 **Private／私人**；這是你自己的研究台，不是所有訪客共用的公開服務。

## 2. 設定資料與模型

Agent 可以使用你自己的 API：不用租 GPU，也不需要在 Codespace 下載 Ollama 模型。研究 Agent 與 A／B／C／D 決策流程會透過你設定的模型服務呼叫；費用計入該 API 帳號。

在研究台進入「資料準備」，展開「設定資料來源與模型」（也可按「設定模型與金鑰」快捷按鈕）：

- **資料來源**：填入 `SEC_USER_AGENT`（自己的姓名與 email）、`FRED_API_KEY`、`ALPHA_VANTAGE_API_KEY`。申請連結見 [金鑰準備](run-options.md#事前準備金鑰)。
- **模型**：選自己的雲端模型 API 或已啟動的 GPUtw 遠端 Ollama，填入模型名稱與對應金鑰／連線資訊。Codespaces 沒有 GPU，不會自動提供 qwen3:32b；詳見 [選擇模型來源](model-sources.md)。
- 按「儲存設定」，重新整理頁面，讓模型選單讀取新設定；到「建立實驗」確認選用自己的模型。使用真實分析時，`RESEARCH_DEMO_MODE` 保持 `false`；缺少資料或模型時應先補齊，不能把合成回應當成真實分析。

金鑰只填在自己的研究台或 Codespaces Secrets，勿放進公開 repo。也可以在建立 Codespace 前先 [設定 Secrets](run-options.md#第一次建立-codespace只做一次)，啟動時會自動讀取。

| 使用自己的哪個 API | 要填的金鑰欄位 | 模型名稱 |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | 使用帳號可存取的模型 ID，格式 `openai/<模型 ID>` |
| Gemini | `GEMINI_API_KEY` | 使用帳號可存取的模型 ID，格式 `gemini/<模型 ID>` |
| OpenRouter | `OPENROUTER_API_KEY` | 使用服務上的模型 ID，格式 `openrouter/<供應商>/<模型 ID>` |

只填你選用的供應商即可，不必三把 key 都申請。模型是否可用取決於帳號權限與服務供應；儲存成功只代表設定已保存，實際呼叫成功才代表連線可用。換模型的探索結果不能直接當成本專題 qwen3:32b 正式實驗的重現。

金鑰保存在該私人研究台的伺服器設定中，設定查詢只回傳是否已設定，不回傳 key 原文。目前是單一擁有者架構；不要把同一台研究台開放給多人各自填 key，以免互相覆蓋設定。

## 3. 跑第一個案例

1. **資料準備**：選股票與歷史分析日，按「啟動資料 Agent」，確認資料就緒與缺口。此流程主要針對美股歷史案例；未來 60 個交易日尚未發生的分析，不能立即得到該期間的真實回測結果。
2. **建立實驗**：選剛建立的資料集，確認模型與設定，按「開始研究實驗」。
3. **Agent 執行**：查看研究摘要、A／B／C／D 決策與辯論進度；若缺資料或模型出錯，先處理畫面上的原因。
4. **看結果**：完成後下載研究產物 ZIP，查看回測與統計。單一案例只用於理解與探索，不等於正式研究結論；正式研究另有 [登記與執行流程](running-experiments.md)。

## 4. 下次回來與停止使用

- 下次到 [你的 Codespaces](https://github.com/codespaces) 開啟**原本那台**，再從 Ports 開研究台。不要每次建立新的一台，資料不會自動搬過去。
- 使用完到 Codespaces 清單將該台 **Stop codespace**。若另有租用 GPU，須另外停止 GPU 執行個體。
- 刪除或重建環境前先備份；保留與重建限制見 [Codespaces 資料說明](run-options.md#之後每次打開原本那台)。

公開網站上的「研究台介面預覽」仍是合成錄製資料。要執行新分析，請使用這裡建立的私人研究台。
