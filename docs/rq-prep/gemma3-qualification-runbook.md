# gemma3:27b 資格檢驗操作手冊（RQ2 模型 B）

適用版本：未標註（下次修訂時補上） · 最後更新：2026-10-19

> 2026-10-15：請先讀 [新版實驗推進手冊](experiment-launch-20261015.md)。下方保留舊 Bash／模型資格脈絡；使用者的 PowerShell 指令、獨立唯讀探針副本、新版 RQ2／RQ3 pilot 及 report-bank seed 規則以新手冊為準。不要直接對原 RQ1 快照初始化 Store；舊 canary 不能代表新設計已合格。

正式登記 RQ2 之前，模型 B 要先通過與 qwen3:32b、gemini-2.5-flash 相同的三項檢驗。本手冊只列操作步驟；為何需要這些檢驗見 `model-b-candidates.md`。

| 檢驗 | 目的 | 呼叫量 | 比較對象 |
|---|---|---|---|
| 1 無資料回想（recall） | 不給證據，只問代號與日期，看模型是否「記得」60 日後的漲跌 | 63 次 | qwen3:32b、gemini-2.5-flash 各年皆未高於多數方向基準 |
| 2 匿名辨識（identify） | 給匿名化證據，看能否猜出公司 | 18 次 | 兩者皆 6/18 |
| 3 合成資料能力試跑（canary） | 確認能完成 22 次決策呼叫的格式、引用與裁決規則 | 約 22 次 | qwen3:32b 已通過 |

三項都通過後，再記下 Ollama 權重雜湊，供事前登記鎖定。

## 0. 事前準備

1. 向實驗室確認：顯卡型號與顯示記憶體（gemma3:27b 量化版需約 17 GB，建議 24 GB 以上）、Ollama 版本、能否自行 `ollama pull`、遠端連線方式。
2. 在實驗室主機下載模型：`ollama pull gemma3:27b`，再用 `ollama show gemma3:27b` 確認。
3. 從本機建立 SSH 通道，不要把 11434 埠開放到網路上（Ollama 沒有密碼保護）：

```bash
ssh -N -L 11435:localhost:11434 你的帳號@實驗室主機
```

4. 確認連得到，並記下權重雜湊（`digest` 欄位）：

```bash
curl -s http://localhost:11435/api/tags
```

## 1–2. 記憶探針

RQ1 資料庫已複製成本機快照 `work/rq1-snapshot/research.sqlite3`（sha256 `46c567ec…b665`，git 忽略），探針只讀它的案例與行情；預設 7 個分析日共 63 案，與先前兩個模型相同。

`GPUTW_OLLAMA_BASE_URL` 的優先順序高於 `OLLAMA_BASE_URL`，執行前必須在這個 shell 清掉，否則會打到 GPUtw 的 qwen 主機。

```bash
env -u GPUTW_OLLAMA_BASE_URL OLLAMA_BASE_URL=http://localhost:11435 .venv/Scripts/python.exe scripts/memory_probe.py --model ollama/gemma3:27b --mode recall --protocol-hash b1da80ee --data-dir work/rq1-snapshot --out docs/gemma3-27b-memory-probe.json
```

```bash
env -u GPUTW_OLLAMA_BASE_URL OLLAMA_BASE_URL=http://localhost:11435 .venv/Scripts/python.exe scripts/memory_probe.py --model ollama/gemma3:27b --mode identify --protocol-hash b1da80ee --data-dir work/rq1-snapshot --out docs/gemma3-27b-anonymized-identification.json
```

判讀方式與 `docs/knowledge-cutoff.md` 相同：各年正確率是否明顯高於多數方向基準；辨識率與 qwen 的 6/18 比較。結果只說明這種問法下有無可見的回想，不證明沒有記憶。

## 3. 合成資料能力試跑

```bash
env -u GPUTW_OLLAMA_BASE_URL OLLAMA_BASE_URL=http://localhost:11435 .venv/Scripts/python.exe scripts/run_model_canary.py --model ollama/gemma3:27b
```

結束代碼 0 為通過。注意：canary 是同質設定（四組都用 gemma）；RQ2 的異質辯論（A/B 分屬兩台主機）路由已合併，但仍需用新版完整設計另做資格／pilot。

## 4. 登記前要留下的紀錄

- `ollama/gemma3:27b` 的權重 digest、量化格式、Ollama 版本、實驗室主機代稱（不記密碼）
- 三項檢驗的 JSON 輸出與執行日期
- 兩台主機（qwen 在 GPUtw、gemma 在實驗室）各自的平行設定（RQ1 為一次一個呼叫）

## 若實驗室顯卡不足

改用備案 `gemini/gemini-2.5-flash`：兩項記憶探針已有結果（`docs/gemini-2.5-flash-*.json`，舊協議），但 API 模型無法鎖定權重，報告須揭露。
