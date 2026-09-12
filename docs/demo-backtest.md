# 本機回測 Demo

這份流程只啟用歷史研究與回測。Finnhub 即時面板預設關閉，系統不會連接券商或送出交易指令。

## 1. 啟動

在專案根目錄執行：

```powershell
.\research.ps1 doctor
.\research.ps1 start
```

開啟 <http://127.0.0.1:8000/>。`/health` 與頁面標籤都應顯示研究協議 `v3-0912.1`。

## 2. 建立新版資料集

`v3-0912.1` 正式資料需要 900 個日曆日的歷史行情、可比較的 SEC 財務指標，以及完整的固定版本 FinBERT 標題分數。舊資料集會保留，但通常只適合稽核或敏感性測試。

```powershell
.\research.ps1 collect NVDA 2024-12-31 -Refresh -UseFinbert
.\research.ps1 readiness
.\research.ps1 datasets
```

`datasets` 會列出完整 `dataset_id`、股票、版本、研究日、行情與證據筆數。`vN` 只是同類資料建立順序；建立工作時以完整 `dataset_id` 鎖定不可變輸入。

資料狀態分開解讀：

- `四域證據完整`：分析日當時可取得的 technical、fundamental、sentiment、macro 都存在。
- `SEC 可比較`：基本面含同比或同一期財務比率，模型不必自行混合不同期間。
- `FinBERT 完整`：資料集內每個新聞標題都有合法的正向、中性、負向機率、輸入雜湊與模型版本。
- `主要回測就緒`：分析日後至少有 60 個交易日；90 日是次要穩健性檢查。
- `正式實驗就緒`：上述條件、歷史來源與目標公司新聞品質全部通過。

資料集沒有新聞時，情緒域可依缺資料對照策略執行；如果已經有新聞，品質或 FinBERT 不完整會被阻擋，除非明確啟用敏感性測試覆寫。

## 3. Web 操作

1. 在「資料」選擇股票與季末研究日，按「重新抓取」並啟用 FinBERT。
2. 等進度完成後，確認資料集明細中的研究日、完整 ID 和五個就緒狀態。
3. 在「實驗」選同一筆資料集。正式 pilot 使用 14B 以上模型、B 組 7 次與 `allow_decision`；小模型需勾選冒煙測試覆寫，結果不得併入正式研究。
4. 按「開始研究實驗」。研究階段會顯示四域摘要，決策階段顯示 A/B/C/D 各波次與 Gatekeeper，完成後顯示 30／60／90 日回測。
5. 關閉頁面或服務重啟不會清除工作；執行中的工作會恢復為暫停，按「繼續執行」即可由最後檢查點續跑。
6. 按「下載研究產物 ZIP」，再用 `verify-export` 驗證其中每個檔案的 SHA-256。

如果選到未安裝的模型，或正式模式選到小於 14B 的模型，開始按鈕會停用並直接顯示原因。

## 4. 終端等價操作

```powershell
# 模型、來源與資料品質
.\research.ps1 models
.\research.ps1 sources NVDA 2024-12-31
.\research.ps1 readiness
.\research.ps1 datasets

# 使用上一個指令顯示的完整 ID
.\research.ps1 run NVDA 2024-12-31 `
  -DatasetId <DATASET_ID> `
  -Model ollama/qwen3:14b `
  -VotingSamples 7 `
  -MissingDataPolicy allow_decision

# 生命週期與匯出
.\research.ps1 jobs
.\research.ps1 job -JobId <JOB_ID>
.\research.ps1 pause -JobId <JOB_ID>
.\research.ps1 resume -JobId <JOB_ID>
.\research.ps1 cancel -JobId <JOB_ID>
.\research.ps1 export -JobId <JOB_ID> -File .\demo-output.zip
.\research.ps1 verify-export -File .\demo-output.zip
.\research.ps1 backup -File .\demo-backup.zip
```

Web 與終端使用同一個 FastAPI、SQLite、資料集與工作佇列；任一介面建立或控制的工作會在另一邊同步出現。網頁執行中每 3 秒更新，閒置時每 30 秒檢查一次，重新切回頁面會立即同步。

## 5. 決策結果判讀

- `model_action` 是模型輸出的 Buy／Hold／Sell。
- `derived_action` 由預期報酬與歷史中性帶推導。
- `candidate_action` 是研究主要比較層。
- `action` 是 Gatekeeper 後的實際回測層。
- `NoTrade` 只代表明確政策或風控阻擋；缺資料對照、模型解析失敗與行情不足各有獨立狀態，不會被統一改寫成 NoTrade。
- 模型逾時、網路中斷、非法引用或輸出格式錯誤會暫停為可重試錯誤。

舊協議工作只能檢視或匯出。使用「複製至新版」會保留舊 ID 與結果，並以目前協議建立新工作，避免提示詞、種子與驗證規則混用。

## 6. Demo 與正式研究界線

既有 AAPL／NVDA 工作可證明流程、續跑、匯出和非固定 Hold 行為，但只要使用舊資料規格或 8B 模型，就只能標為冒煙測試。正式論文結果需先完成 9 檔 × 20 季的 180 個正式就緒資料集，執行預註冊 pilot 停止規則，再凍結 study manifest 與程式版本。

不要執行 `docker compose down -v`，這會刪除具名資料卷。交接或升級前先執行：

```powershell
.\research.ps1 backup -File .\research-backup.zip
```

部署與交接方式見 [部署指南](deploy-v3.md)、[版本紀錄](../CHANGELOG.md) 與 [Clone 後首次啟動](getting-started.md)。
