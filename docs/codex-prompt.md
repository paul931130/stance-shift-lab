# Codex 任務：讓 stance-shift-lab 以「本機原生安裝 + API」快速上線

## 背景
- Repo：stance-shift-lab（FastAPI + SQLite + 原生 JS 前端，`research_service/`）。
- 定位：研究/教育用的 multi-agent「立場交換」回測工具，**不下單、不提供投資建議**。
- 目標：使用者從 GitHub 安裝後在自己電腦跑（Ollama 在主機上），同時提供穩定的 HTTP API。
- **Docker 不是必要條件**：改成原生安裝為主，Docker 為選配（伺服器/隔離用）。Windows 上 Docker Desktop/WSL2 最不穩。

## 硬性限制（不可違反）
1. 不改 `StudyProtocol` 欄位與 `protocol_hash` 語意；純工具/UI/API 改動不升協議版本。
2. 不改 `QUARTER_DATES`、`splits.py` 時間切分（Test 2025 凍結）、快照不可變規則。
3. 不把 API key、`.env.research`、`research-data*/`、`research-inputs/` 的 CSV 提交進 repo。
4. 不接券商、不下單、不產生個人化投資建議。
5. 不修改 git config；commit 訊息結尾加 `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`（若由 Claude 提交）。
6. 每個階段都要 `python -m unittest` 與 `ruff check` 通過，CHANGELOG 補條目。

## P0-A　可安裝套件
1. 新增 `pyproject.toml`（PEP 621）。核心相依放 dependencies；`torch`+`transformers` 放 extra `[finbert]`；測試/ruff 放 `[dev]`。保留 numpy/scipy/pandas/transformers 的既有 pin（可重現性）。
2. 新增 console entry point `stance-shift`，子命令：`setup`、`doctor`、`serve`、`demo`、`collect`、`run`、`jobs`、`export`、`verify-export`、`backup`、`gaps`、`splits`。純 Python（argparse 或 typer），Windows/macOS/Linux 皆可。`scripts/researchctl.ps1` 保留為薄包裝。
3. 預設資料目錄用 platformdirs（例如 `~/.stance-shift`），可由 `RESEARCH_DATA_DIR` 覆蓋；移除程式中寫死的 Windows 路徑。
4. README 第一屏只留三行：`pipx install git+https://github.com/paul931130/stance-shift-lab` → `stance-shift doctor` → `stance-shift serve`。其餘搬 docs。

## P0-B　doctor 與 demo
5. `stance-shift doctor`：檢查 Python 版本、資料目錄可寫、SQLite、Ollama 連線、指定模型是否已安裝、FinBERT 是否可用、API key 是否設定，輸出「實際使用的模型端點」。
6. **端點遮蔽警告**：若已設定遠端 `GPUTW_OLLAMA_BASE_URL` 但連不上，明確警告，不可靜默覆蓋本機 Ollama（先前造成「本機尚未安裝 qwen3:14b」誤導）。UI 也要顯示目前解析出的端點。順便修 `/api/models` 401/403 訊息中寫死的「GPUtw」字樣（端點是本機時不應出現）。
7. `stance-shift demo`：內建小型合成資料集 + mock 模型，不需任何 API key，端到端跑完並在 UI 看到結果。

## P0-C　API 正式化
8. `app.py` 目前 `docs_url=None, redoc_url=None`：本機預設開啟 `/docs`、`/openapi.json`；對外綁定時需 token 才可看。
9. 路徑加 `/api/v1` 前綴，舊路徑保留一版轉導。
10. 預設只綁 `127.0.0.1`；對外時強制 Bearer token（沿用 `RESEARCH_ACCESS_KEY`），CORS 預設關閉，加 Host 白名單。
11. 統一錯誤格式 `{code, message, retryable}`（`/api/models` 已有雛形，推廣到全部端點）。
12. 拆輕量端點：`GET /api/v1/jobs/{id}/summary`（狀態、進度、決策）、`/records?cursor=`、`/events`（SSE 推進度，取代 3 秒輪詢）。目前 `GET /api/jobs/{id}` 回傳整包 state（>40 KB），負載高時逾時；前端改用新端點。
13. `/api/v1/jobs` 加分頁與篩選。commit 產生的 `openapi.json`；提供薄封裝 httpx 的 Python client 與 `docs/api.md`（含 curl 範例）。
14. CI 加 API 契約測試（例如 schemathesis）。

## P1　穩定性與正確性
15. `Store.recover()` 把 running 工作改 paused 並寫入「服務重啟」錯誤；resume 時要清空 `error` 欄位。
16. `models.py` 硬編碼 240 秒逾時改為可設定（環境變數 + settings），並保留重試次數設定。
17. 呼叫 Ollama 時明確傳 `options.num_ctx`（如 8192）與 `keep_alive`；prompt 逼近上限時預警（目前 context 4096、prompt 約 3000 tokens）。
18. 模型資格 canary：開跑正式工作（22 次呼叫）前，先用 1–2 個短 prompt 驗證「引用 evidence_id 是否合規」。實測 gemma3:4b 幾乎全部引用失敗，qwen3:8b 過 A/B/C 但 D 組立場交換失敗；不合格要先告知，不要跑半小時才發現。
19. worker 拆成獨立行程 `stance-shift worker`（同一個 SQLite WAL），API 行程在 14B 推論期間仍可回應。暫停/取消需能中斷進行中的呼叫。
20. 不要每步重寫整包 state JSON，改增量 records 表（保持匯出格式與 hash 語意不變）。
21. 新增 `/health/deep`：worker 狀態、DB 可寫、目前模型端點。

## P1　CI 與測試
22. CI 加 OS matrix：ubuntu / windows / macos 原生跑單元測試。修 Windows 上 2 個 SQLite 暫存檔清理失敗（明確關閉連線或 `TemporaryDirectory(ignore_cleanup_errors=True)`）。
23. Smoke test：乾淨 venv 安裝 wheel → `stance-shift serve` → 打 `/health` 與數個端點。
24. Playwright 冒煙：分頁導覽、設定面板非 secret 欄位顯示值。

## P2　發佈與散布
25. tag 時 GitHub Actions 自動建 wheel/sdist 並附到 Release；Docker image 推 GHCR（slim 不含 torch、`-finbert` 含 torch）；`compose.research.yaml` 改為 `image:` 為主、`build:` 為備援。
26. 新增 `.devcontainer/devcontainer.json`（Codespaces，使用雲端模型 key，不含本機 Ollama）。
27. `docs/` 內日期型驗證文件歸到 `docs/archive/`；補 SECURITY.md、issue templates、「該選哪種安裝方式」對照表與 Docker Desktop 不穩時改走原生的 troubleshooting。
28. 協議版本單一來源：由 `protocol.py` 讀取，README/CHANGELOG 不重複手寫。

## 驗收標準
全新 Windows/macOS/Linux 機器只裝 Python 3.12 與 Ollama，執行
`pipx install ...` → `stance-shift doctor` → `stance-shift serve`（或 `demo`），5 分鐘內在 `http://127.0.0.1:8000/` 看到 demo 案例跑完，`/docs` 可用；CI 在 ubuntu 與 windows 皆綠。

## 建議施工順序
P0-A → P0-B → P0-C → P1（15–18 先，19–20 為較大重構獨立 PR）→ CI → P2。每個階段一個 PR，附測試與 CHANGELOG。
