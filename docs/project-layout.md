# 專案結構

公開入口為 [專題網站](https://paul931130.github.io/stance-shift-lab/)。研究服務由 `research.ps1`、Docker Compose 或 CLI 啟動 `research_service`；實際資料與模型需要獨立執行環境，見 [執行方式](run-options.md)。各研究的進度見 [研究狀態](research-status.md)。

## 程式

| 位置 | 用途 | 是否提交 Git |
| --- | --- | --- |
| `research_service/` | API、資料 Agent、研究引擎、統計與正式網頁（含 `static/` 前端；實驗啟動條件由 `/api/jobs/preflight` 統一判斷） | 是 |
| `research_service/web/` | HTTP 層：`system`（介面、登入、設定）、`datasets`（快照與蒐集任務）、`jobs`（實驗驗證與佇列）、`studies`（統計）；`app.py` 只負責組裝 | 是 |
| `research_service/tests/` | Python 單元測試（unittest），含 demo 模式的瀏覽器端對端測試 `test_e2e_demo.py` | 是 |
| `scripts/` | 終端管理、資料準備、模型資格與 pilot（`lab-run.ps1`、`check_pilot.py`）、RQ2／RQ3 分析、公開網站的建置與檢查 | 是 |
| `experiments/` | 本專題各實驗（E1–E3）固定映像、資料庫與連接埠的 compose 檔，見其 README | 是 |
| `compose.research.yaml`、`compose.ollama*.yaml`、`compose.production.yaml` | 框架服務：主服務、選用的 Ollama 容器（CPU／NVIDIA）、遠端部署附加設定 | 是 |
| `Dockerfile.research`、`deploy/` | 研究服務映像、反向代理範例與資格檢查用映像 | 是 |
| `research.ps1`、`research.cmd`、`research.sh`、`start-research.cmd` | 各平台的啟動入口 | 是 |
| `.devcontainer/` | GitHub Codespaces 的雲端研究台設定，見 [雲端啟動](cloud-start.md) | 是 |
| `pyproject.toml`、`ruff.toml` | 套件相依；Python lint 規則（正確性導向：語法錯誤、未使用 import/變數） | 是 |

`research_service/` 內的主要模組：

| 功能 | 模組 |
| --- | --- |
| 資料蒐集與快照 | `data.py`、`collect.py`、`av_archive.py`、`finbert.py`、`anonymize.py` |
| 辯論引擎 | `engine.py`（A／B／C／D 四組）、`domain_debate.py` 與 `rq3_controls.py`（RQ3）、`models.py`（提示與輸出格式）、`model_router.py`（RQ2 的多模型路由） |
| 協議與凍結 | `protocol.py`、`model_identity.py`、`launch_package.py`、`run_manifest.py` |
| 回測與統計 | `backtest.py`、`statistics.py`、`rq_analysis.py`、`rq_repeats.py`、`rq3_inference.py`、`power.py` |
| 儲存與排程 | `storage.py`（SQLite）、`breaker.py`、`autostop.py` |
| 介面 | `app.py` 與 `web/`、`static/`、`cli.py`、`tui.py`、`demo.py`（展示模式） |

## 公開網站

`site/` 的內容由 `.github/workflows/pages.yml` 在 `main` 更新時部署到 GitHub Pages；部署前會執行 `scripts/check_public_site.py`。

| 位置 | 網址路徑 | 內容 |
| --- | --- | --- |
| `site/index.html` | `/` | 導覽首頁：說明各分頁的用途 |
| `site/rq1/` | `/rq1/` | 研究故事：用互動方式講 RQ1 |
| `site/demo/` | `/demo/` | 兩個已完成 RQ1 案例的逐輪回放，不執行新分析 |
| `site/app/` | `/app/` | 研究台的唯讀預覽，使用合成錄製資料，由 `scripts/static_demo.py` 產生 |
| `site/meeting/` | `/meeting/` | 研究進度的互動簡報 |
| `site/sources/*.pdf` | `/sources/` | 研究報告 PDF；LaTeX 原始檔不提交 |

公開網站是靜態頁面，沒有共用的分析後端，不呼叫模型、不抓行情。

## 文件與報告

| 位置 | 用途 | 是否提交 Git |
| --- | --- | --- |
| `README.md`、`CHANGELOG.md`、`CONTRIBUTING.md` | 專案入口、各協議版本的行為變更紀錄、貢獻方式 | 是 |
| `docs/` | 操作、研究口徑與部署文件 | 是 |
| `docs/rq-prep/` | RQ2／RQ3 的事前登記草稿、設計決策、分析計畫、實驗室操作單與 RQ1 升格稽核，見其 [索引](rq-prep/README.md) | 是 |
| `docs/archive/`、`docs/review/` | 舊版設計筆記與歷次審查紀錄，只供歷史脈絡 | 是 |
| `report/stance-shift-report.pdf` | 研究報告 | 是 |
| `report/` 其餘檔案 | LaTeX 原始檔、各版修訂與建置輸出 | 否 |

## CI

| 位置 | 用途 |
| --- | --- |
| `.github/workflows/ci.yml` | ruff、Python 測試（Linux 與 Windows）、前端語法檢查、瀏覽器端對端測試、Docker 與 Codespace 啟動、公開連結檢查 |
| `.github/workflows/pages.yml` | 部署 `site/` 到 GitHub Pages |
| `.github/dependabot.yml` | 套件與 GitHub Actions 的版本更新 |

## 只在本機、不提交的內容

| 位置 | 內容 |
| --- | --- |
| `.env.research` | 來源、模型與部署秘密 |
| `research-inputs/*.csv` | FNSPID 等授權資料；格式說明在 `research-inputs/README.md`（有提交）。正式服務的新聞來源檔為 `research-inputs/Stock_news.csv` |
| Docker volume `research-data` | SQLite、工作進度與結果；需另行備份 |
| `research-data*/` | 不用 Docker 時的本機資料目錄 |
| `work/` | 試跑輸出、離線封裝與 pilot 結果 |
| `backups/`、`deliverables/`、`release/`、`output/`、`tmp/` | 資料庫備份、打包檔與一次性輸出 |

舊版 Sites/Next 原型已移除，舊實作可查看 Git 歷史。

資料快照存進 SQLite 後，以 dataset ID 鎖定內容。相同資料集可供多個模型或 A/B/C/D 重跑；除非研究者明確要求新版資料快照，否則不重新呼叫來源 API。
