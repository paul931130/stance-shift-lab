# RQ2／RQ3 正式前整備狀態（2026-10-17）

**本機前置整備已完成，可依操作單接真實模型驗收；正式研究尚未放行。** 沒有新增正式登記或排入正式案例。完整測試 465 項：464 通過、1 項因 Windows 不支援 POSIX 檔案權限而跳過，無失敗／錯誤；包含實際 Chrome 的 RQ1、RQ3 控制組與示範播放器測試。

操作入口：[正式實驗前操作單](../rq-prep/preformal-runbook-20261017.md)。分析候選：[完整計畫](../rq-prep/analysis-plan-20261015.json)。報告仍為 application-meeting-20261015_v9；本次沒有重跑研究結果或把提案改寫成觀察結果。

## 本次補齊

- 啟動封裝：實際來源的完整 180 案、digest、資料 coverage、案例順序與 SHA256 manifest；保存完整計畫、RQ3 runtime 與執行／分析腳本 hashes。
- 明確區分 RQ2 三 seed（905／906／907）與 RQ3 單 seed（905）；RQ3 不再攜帶會被引擎拒絕的 RQ2 專用 model_endpoints，改以明確 runtime 設定連 A。
- 離線 RQ2 綁定工具：從 standalone report-bank backup 唯讀產生三個正式 BatchInput；拒絕缺案／重複來源、已見決策、舊程式、改動模板、權重不一致或 artifact／pipeline hash 不符。它不建立登記、工作，也不宣稱權重已通過線上驗證。
- 逐 seed Sharpe interaction／樣本 SD 已補上；任一 seed 不可估計時 SD 為未知並揭露可估計數，避免只用部分 seed 計算變異。
- 正式協議停止保護：凍結樣本內的正式工作 paused／cancelled 時停止認領同協議後案；資格與報告庫工作另有用途限制，不用它們阻擋正式研究。
- Python／固定依賴檢查工具與正式前操作單；更正歷史交接中的舊狀態，保留原始審查紀錄。

## 本次實際驗收

1. 全套 465 tests、Ruff、所有前端 JS 語法檢查通過；本機 Python 3.12.10、固定依賴版本吻合、pip check 通過。
2. 來源透過 SQLite backup 建立新的 standalone 快照，原資料庫主檔 SHA256 不變。對完整登記 180 案執行啟動封裝成功。
3. 使用實際歷史資料的 RQ2／RQ3 各三案離線 pilot 準備成功，來源不變、未建立 job、未探測模型。
4. 額外用明確標示 SYNTHETIC 的 180 案報告庫驗證完整綁定，輸出 540 筆請求、三個不同 protocol hash、來源 hash 不變。此項只測綁定整合，不是模型資格或研究輸入庫。

可重查的本機證據位於 ignored 的 work/preformal-20261017：test-result.json、tests.txt、environment-final.json、launch-final/、rq2-offline-final/、rq3-offline-final/、binding-integration.json、release-manifest.json。實際使用前要換成可用端點重新封裝；現有端點為實驗室本機通道範例。SYNTHETIC-* 檔案一律不可投入正式研究。

## 仍需真實環境完成的啟動門檻

- GPUtw 前次 Qwen canary 因 HTTP 524 失敗，後續呼叫未執行；不能視為資格通過。使用者已於 10 月 16 日確認測試機關閉。既有 API 憑證為 401，本輪不重開 GPU、不重試失效金鑰。
- 實際模型 A/B 的完整 digest、Ollama／image 與套件環境、穩定載入、基礎 canary 與記憶探針尚待本輪重新驗收。GPUtw 範本內的 Open WebUI Python 3.11 不能代替本專案的 Python 3.12 環境。
- RQ2／RQ3 真實三案 pilot 尚未完成；需要核對所有 arms、引用／schema、截斷、tokens、重試、成本／時間與身份一致性。只依格式和執行品質修正，不以研究績效選設定。
- 真實 180 案 report bank 尚未建立；分析候選仍須與 runtime/source 一起凍結封存後，再建立新登記。報告與操作單不得被當成已完成研究的證明。

正式啟動流程已整理為：環境與模型資格 → 兩種設計 pilot → 凍結程式／計畫 → 180 案報告庫 → 三 seed 綁定 → 同 Store 逐案 preflight → 新登記 → enqueue。操作單附指令；本輪停在正式登記以前。
