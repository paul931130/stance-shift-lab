# GitHub 正式發布檢查表

## 提交前

- 確認 `.env.research`、API key、聯絡信箱、研究資料 CSV、SQLite、模型檔與輸出 ZIP 都不在 Git 追蹤清單。
- 檢查 Git 歷史；若秘密曾經被提交，先撤銷並重發金鑰，不能只刪除目前檔案。
- 不提交 Yahoo、FNSPID 或其他受授權限制的原始資料，只提交取得與整理說明。
- 跑完 Python 測試、前端語法檢查、Docker 建置與本機 smoke test。
- 在 README 清楚區分研究系統、尚未完成的正式實驗與不能宣稱的績效。

## 部署前

- 使用獨立伺服器或 VM、持久化磁碟及定期備份；不要使用 GitHub Pages 當後端。
- 執行 `.\research.ps1 setup` 的 server 模式，設定實際網域、來源憑證與至少 32 字元的存取金鑰。
- 使用 `compose.research.yaml` 加 `compose.production.yaml`，並由 Caddy/Nginx 提供 HTTPS。
- Ollama 只暴露給同主機或私有網路；若使用雲端模型，API key 只存在伺服器環境。
- 驗證未登入 API 回傳 401、跨來源修改被拒絕、cookie 為 Secure/HttpOnly/SameSite、Host 白名單正確。
- 設定登入與反向代理速率限制、磁碟容量告警、API 額度與模型成本上限。

## 多使用者版本

目前封裝是「單一研究室擁有者」。若讓每位使用者填自己的資料來源或模型帳號，需要增加帳號系統、每人加密憑證、資料與工作隔離、刪除／匯出機制、額度限制與隱私條款。在完成這些能力前，不要在公開網頁提供儲存訪客 API key 的表單。
