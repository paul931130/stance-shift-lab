# 網站穩定度與操作指引

## 本次修正

- 網頁 API 讀取逾時設為 15 秒；逾時會顯示可理解的錯誤，不會讓整個畫面無限等待。
- 只對 GET 讀取請求做一次短暫重試。建立實驗、下載資料、儲存設定等寫入請求不會自動重送，避免重複建立工作或快照。
- 設定、資料集、完整度、實驗佇列與模型狀態會並行載入。單一面板暫時失敗時，其餘面板仍可使用，重新整理即可補載入。
- `research.ps1 start` 會先等待 `/health` 通過，再開啟瀏覽器，避免剛啟動時看到空白或連線失敗頁面。
- Compose 啟用 `init`，讓容器正確轉送停止訊號並回收背景程序；資料仍保存在 `research-data` volume。

## 正常啟動與檢查

在專案根目錄執行：

```powershell
.\research.ps1 start
.\research.ps1 status
```

只有看到 `healthy` 且 `/health` 回傳 `status: ok` 才開始建立實驗。網站位址是 <http://127.0.0.1:8000/>。

若頁面暫時顯示部分資料未載入，等待幾秒後按「重新整理」即可；讀取請求有逾時與一次重試，寫入請求不會被瀏覽器重複送出。

## Docker Desktop 異常時

本機研究資料不在容器本身，而在具名 volume；不要使用 `docker compose down -v`。

先執行：

```powershell
.\research.ps1 status
.\research.ps1 doctor
```

若 Docker Desktop 顯示 WSL engine、`sailor-ingest.sock` 或 Linux engine 無法啟動，先完全退出 Docker Desktop，再重新開啟並等待 Linux engine 就緒。仍無法啟動時才使用：

```powershell
.\research.ps1 repair-docker
```

此指令會停止 Docker 相關程序、把 runtime 暫存目錄移到同一個 `%LOCALAPPDATA%` 下的自動復原備份目錄，再重新啟動 Docker；不會刪除 `research-data` volume 或研究輸入檔。

## 已驗證狀態（2026-09-15）

- Python 回歸測試：100/100 通過。
- 前端規則測試：10/10 通過。
- Compose 設定可解析，重建後容器 `restart=0`、健康檢查通過。
- `/health`、首頁、設定、資料集、完整度、佇列與模型端點連續三輪均回傳 HTTP 200；資料集端點首輪約 1.17 秒，後續約 0.14–0.17 秒。

目前若仍出現整個網站無法連線，優先判定為 Docker Desktop／WSL engine 沒有提供 8000 埠，而非研究資料或回測資料損壞。
