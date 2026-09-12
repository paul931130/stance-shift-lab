# 專案結構

正式產品只有一條執行路徑：`research.ps1` → Docker Compose → `research_service` → `http://127.0.0.1:8000`。

| 位置 | 用途 | 是否提交 Git |
| --- | --- | --- |
| `research_service/` | API、資料 Agent、研究引擎、統計與正式網頁 | 是 |
| `research-inputs/README.md` | 本機資料格式說明 | 是 |
| `research-inputs/*.csv` | FNSPID 等授權資料 | 否 |
| `.env.research` | 來源、模型與部署秘密 | 否 |
| `scripts/` | 終端管理、資料準備與驗證 | 是 |
| `docs/` | 操作、研究口徑與部署文件 | 是 |
| Docker volume `research-data` | SQLite、工作進度與結果 | 否；需另行備份 |
| `app/`、`lib/`、Node/Vinext 檔案 | 舊版 Sites/Next 展示原型 | 暫時保留，不是正式入口 |

`app/research-inputs/` 是先前手動下載留下的本機目錄，已由 Git 與 Docker 排除。正式服務只讀專案根目錄的 `research-inputs/Stock_news.csv`。未來整理公開儲存庫時，可將舊版 Sites/Next 原型移到獨立 branch；在完成遷移前不要直接刪除，以免遺失仍需參考的介面或部署設定。

資料快照存進 SQLite 後，以 dataset ID 鎖定內容。相同資料集可供多個模型或 A/B/C/D 重跑；除非研究者明確要求新版資料快照，否則不重新呼叫來源 API。
