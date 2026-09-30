# 本專題的實驗

每個實驗＝一個協議版本＝一個固定映像＝一個資料庫 volume＝一個連接埠，互不干擾。框架本身的服務用根目錄的 `compose.research.yaml`；這裡的檔案只用來重現或續跑本專題的實驗。

| 實驗 | 檔案 | 模型／協議 | 連接埠 | 資料庫 volume | 狀態 |
|---|---|---|---|---|---|
| E1 | `e1-gemini.yaml` | Gemini 3.1 Pro／v3-0927.2 | 8000 | `stance-shift-lab_research-data` | 舊情緒規則，13/180 後停止，不再續跑 |
| E2 | `e2-qwen.yaml` | qwen3:32b／v3-0929.1 | 8001 | `stance-shift-lab_research-data-qwen`（封存，唯讀） | 180/180 完成，舊規則的歷史結果 |
| E2′ | `e2prime-qwen.yaml` | qwen3:32b／v3-0930.3 | 8003 | `stance-shift-lab_research-data-qwen-v2` | **RQ1 主實驗**，已事前登記，待執行 |
| E3 | `e3-monthly.yaml` | qwen3:32b／v3-0930.4（月度） | 8002 | `stance-shift-lab_research-data-monthly` | RQ2，E2′ 完成後執行 |

一律從專案根目錄執行，並指定同一個專案名稱，容器與 volume 名稱才會一致：

```bash
docker compose -p stance-shift-lab -f experiments/e2prime-qwen.yaml up -d
```

E2′ 的執行方式見 [docs/e2prime-run-prompt.md](../docs/e2prime-run-prompt.md)，事前登記見 [docs/e2prime-preregistration.md](../docs/e2prime-preregistration.md)，整體架構見 [docs/experiment-architecture.md](../docs/experiment-architecture.md)。
