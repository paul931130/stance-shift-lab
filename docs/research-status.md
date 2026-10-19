# 研究狀態與證據界線

此頁整理目前版本內的研究紀錄，不代表重新執行實驗、即時查核資料庫或完成模型資格。公開入口為 [專題網站](https://paul931130.github.io/stance-shift-lab/)；[唯讀合成展示](https://paul931130.github.io/stance-shift-lab/app/) 僅說明流程，[研究報告 PDF](../report/stance-shift-report.pdf) 提供完整內容。

| 研究 | 已有證據 | 尚未完成／可支持的結論 |
|---|---|---|
| RQ1 | v3-1002.3、qwen3:32b，180 案回溯比較；版本內稽核記錄 C 正確 105/180、D 正確 99/180，雙尾精確 McNemar p 約 0.21 | 未取得 D 優於 C 的顯著證據。樣本曾用於前導試跑與調整，不能視為獨立樣本外結果；正式升格缺口及研究者確認仍依稽核紀錄處理 |
| RQ2 | 異質模型路由與 AA／AB／BA／BB 設定已實作；候選設計採至少三個 seed | 真實 A/B 模型資格、完整設計 pilot、鎖定報告庫、正式登記與執行尚未完成，沒有新版正式結果 |
| RQ3 | 領域辯論、View judge、Final Aggregator、資源對齊通才與資訊切分不辯論對照已實作，並有合成測試 | 真實模型資格、完整設計 pilot、正式登記與執行尚未完成；程式／合成測試通過不代表研究假說成立 |

RQ1 數字及限制來自 [RQ1 升格稽核](rq-prep/rq1-promotion-audit.md)，此頁未重新計算。月度實驗、整套系統換模型與合成展示，不等於新版 RQ2／RQ3 結果。

## 正式研究的下一步

以 [2026-10-17 正式實驗前操作單](rq-prep/preformal-runbook-20261017.md) 與 [候選分析計畫](rq-prep/analysis-plan-20261015.json) 為準。先確認環境、模型權重與 runtime，再完成基礎 canary、記憶探針及三案完整設計 pilot；驗收並凍結程式與分析設定後，才建立並鎖定報告庫，最後事前登記並排入正式案例。離線封裝的 `formal_launch_ready=false` 不表示模型不合格，也不表示已允許正式啟動。

RQ2 跨 seed 在案例內合併，不能把三 seed 當成三倍市場樣本；RQ3 使用單 seed／protocol 候選分析。舊草稿的預算、可選控制組及待開發敘述只供歷史脈絡，不可直接作正式登記。

## 文件入口

- [RQ 準備索引](rq-prep/README.md)：設計草稿、資格與操作文件。
- [實驗架構](experiment-architecture.md)與 [E2′ 登記文件](e2prime-preregistration.md)：既有配置與紀錄。
- [模型資格](model-qualification.md)：資格檢查與證據要求。
- [CHANGELOG](../CHANGELOG.md)與 [協議實作](../research_service/protocol.py)：版本變更與設定。

內部審查、交接與封存紀錄不屬公開文件入口；摘要不替代原始輸出、資料庫快照、登記回執或具名驗收。
