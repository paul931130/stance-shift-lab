# 專案結構

正式產品只有一條執行路徑：`research.ps1` → Docker Compose → `research_service` → `http://127.0.0.1:8000`。

| 位置 | 用途 | 是否提交 Git |
| --- | --- | --- |
| `research_service/` | API、資料 Agent、研究引擎、統計與正式網頁（含 `static/` 前端與 `readiness-rules.js` 純函式規則） | 是 |
| `research_service/tests/` | Python 單元測試（unittest） | 是 |
| `research_service/tests_js/` | 前端純函式規則的 Node 內建測試（`node --test`，無需 npm） | 是 |
| `research-inputs/README.md` | 本機資料格式說明 | 是 |
| `research-inputs/*.csv` | FNSPID 等授權資料 | 否 |
| `.env.research` | 來源、模型與部署秘密 | 否 |
| `scripts/` | 終端管理、資料準備與驗證 | 是 |
| `docs/` | 操作、研究口徑與部署文件 | 是 |
| Docker volume `research-data` | SQLite、工作進度與結果 | 否；需另行備份 |
| `CHANGELOG.md` | 各協議版本的行為變更紀錄 | 是 |
| `.github/workflows/ci.yml` | ruff、Python 測試、前端語法與測試、Docker build | 是 |
| `ruff.toml` | Python lint 規則（正確性導向：語法錯誤、未使用 import/變數） | 是 |

舊版 Sites/Next 展示原型（`app/`、`lib/`、`db/`、`drizzle/`、`worker/`、Node/Vite/Cloudflare 設定）已於 2026-09-12 移除；其設計背景保留在 [design-notes-v3-0908.md](design-notes-v3-0908.md)，需要參考原始碼可從 git 歷史還原。正式服務只讀專案根目錄的 `research-inputs/Stock_news.csv`。

資料快照存進 SQLite 後，以 dataset ID 鎖定內容。相同資料集可供多個模型或 A/B/C/D 重跑；除非研究者明確要求新版資料快照，否則不重新呼叫來源 API。
