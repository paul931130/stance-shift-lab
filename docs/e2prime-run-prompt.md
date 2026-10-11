# E2′ 正式批次執行規格（修正版待放行）

## 狀態：目前不得啟動正式批次

本文件取代舊版執行提示。舊版引用的 `v3-1001.1`、hash `6be8da83…`、舊映像及舊登記指令都已失效，不可照舊 POST 或續跑。舊研究記錄保留供追溯，不能與新批次合併。

本機修正候選為季度協議 `v3-1002.3`。source digest 與協議 hash 在最終程式 commit、映像建置後，以正式服務 `/health` 的 `source_digest` 與批次預覽為準；任何實驗模組（anonymize、backtest、data、engine、finbert、model_identity、models、protocol、storage）變更都會讓 hash 改變，必須重算。Engine、單案續跑與整批續跑都會重新比對已凍結 hash；不相符就拒絕續跑。

`docs/e2prime-batch-payload.json` 目前有 180 個唯一資料集，已按分析日期排序並逐案明列設定。正式案例均須使用相同的新來源、映像、模型 digest 與協議 hash。執行者不得自行略過下列放行檢查；本規格本身不授權啟動 GPU、事前登記或建立正式工作。

## 凍結設定

| 項目 | 固定值 |
|---|---|
| 協議／設計 | `v3-1002.3`／季度 |
| 樣本 | 9 檔 × 2021–2025 年 20 個季末，共 180 個唯一 dataset ID；依 analysis_date 排序 |
| 模型 | `ollama/qwen3:32b`；事前登記時鎖定 180 案相同的實際權重 digest |
| 輸入匿名化 | `anonymize_ticker=true`；資料內財報數值和日期仍可能讓模型辨認標的 |
| 行動 | `action_source=model`；A/B 可 Hold；C/D 裁決者必須 Buy 或 Sell，且方向須與預期報酬正負號一致 |
| 投票與辯論 | B 組 7 次投票；三輪辯論，D 交換輪只提供同一代理人自己的第 1 輪 |
| 生成 | temperature 0.2；投票 temperature 0.8；輸出上限 2048 tokens；context 8192；同時呼叫 1；每個驗證失敗最多 3 次模型請求 |
| 缺值與例外 | `missing_data_policy=allow_decision`；`allow_point_fundamental=false`、`allow_small_model=false`、`allow_low_quality_sentiment=false` |
| 主要終點 | D−C、60 個交易日、Corwin–Schultz 成本、candidate layer、all-portfolio；方向準確率與年化風險調整報酬為固定兩端點 Holm family；兩者都正向且校正 p<.05 才支持主要假說 |
| 敏感性／成本 | 30、60、90 日；零成本與 Corwin–Schultz；價差窗口 20；不含借券費、滑價、衝擊、稅費或實際 RF 序列 |
| 統計 | bootstrap seed 905、1999 次、日報酬 circular block 20；日期 cluster 與分組比較均屬敏感性分析，不取代主要 family |
| 資料品質指標 | `unsupported_call_rate` 的分母為有 audit 的模型輸出呼叫；至少一個未匹配來源數字即計一次。它不是所有數字的 token 比例，也不等同事實正確率 |

## 正式放行前的檢查

1. **凍結原始碼與映像。** 完成本輪 review 後不得再改研究程式。用目前工作樹建置 `experiments/e2prime-qwen.yaml` 指定的 image tag；不要使用 `git archive HEAD`，它不會包含未提交修正。記錄 Git HEAD、source digest、建置後 image ID。容器 `GET /health` 必須回 `version=v3-1002.3` 且 `source_digest` 與本機相同。
2. **核對有效執行設定。** 只查看 `/api/settings` 的非秘密欄位；不要列印或複製任何 key。確認模型逾時 600 秒、context 8192、Ollama parallel 1、自動關機閒置 15 分鐘。確認 `/api/gputw/status` 顯示 autostop enabled；這需要 `instances:manage` 權限，但不要輸出憑證。私有設定可能覆寫 compose 環境值，不能只看 YAML。
3. **核對端點與模型身分。** `/api/models` 必須為 ready、只使用 `ollama/qwen3:32b`，並記錄實際 digest。先前預期值 `030ee887880fc378860c2dd35101da424377520441ae4bfe7be6deff8ade7840` 只能作為比對參考；以當次查得且事前登記鎖定的 digest 為準。任何不同都停止，不要改登記內容配合它。
4. **完成隔離資格檢查。** 使用獨立資料庫／輸出，不掛正式 volume、不計入 180 案。最新版 qualification 必須涵蓋完整研究報告與 22 個決策呼叫、C/D 三輪及裁決、匿名化、引用／數字記錄、重試成本、推理前後身分、回測、統計匯出與斷線恢復。canary 或合成 demo 不能代替正式模型 qualification。
5. **預覽與比對。** 對 180 案做完整預覽；確認唯一 ID、季度日期、全部 readiness、每案明列參數、匿名化為 true、相同 source digest、protocol hash 與模型 digest。hash 不符、數量不是 180 或任何 readiness blocker 存在時停止。
6. **事前登記及正式排入需要另行明確授權。** 在使用者批准以前，不呼叫 `/api/studies/preregister`、`/enqueue` 或 resume。獲授權後，登記回傳的 hash 必須逐字等於預覽 hash；只使用新 hash，不修改或續跑舊登記。正式工作建立後才開始監控。
7. **故障與停機。** 端點錯誤應暫停並可續跑；權重 digest 真正不一致才永久封鎖。breaker 持續開啟 15 分鐘後，佇列視為 idle，再經一般 15 分鐘 idle timer 嘗試自動關機，約 30 分鐘；正式 GPU 管理權限尚未實機驗收，操作期間仍須監控 GPU 狀態。
8. **收尾與報告。** 只在 180 個登記案例都到終態後彙整；列出失敗案例、恢復次數、實際 provider attempts／tokens、有效 digest、source/image manifest 與費用。保留所有失敗歷史，不把較舊協議、資格案例或其他資料庫輸出混進正式結果。
