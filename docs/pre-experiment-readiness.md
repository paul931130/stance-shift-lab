# 正式實驗前置就緒度

狀態基準日：2026-09-20

這份文件把「正式模型不呼叫、不產生正式結果」時可以先完成的工作固定下來。正式研究仍維持 `0/22`：一個案例的 22 次決策呼叫尚未完成，不得把 synthetic、smoke test 或單一 pilot 當成正式結果。

## 已確認的現況

| 項目 | 目前證據 | 研究處理 |
| --- | --- | --- |
| 正式案例 | 0/22 呼叫完成 | 結果頁保留占位，不做績效結論 |
| 模型 | gemma3:4b 引用驗證幾乎全失敗；qwen3:8b 立場交換輪失敗；14B 在 CPU 不實際 | 先跑 synthetic model canary，再決定 GPU、雲端或其他通過驗證的模型 |
| 基準 | A、B、C、D 已存在；D vs C 是 role-switch 的直接比較；Buy-and-hold 是回測基準 | D vs C 設為 primary；A/B 與成本基準做 secondary / sensitivity |
| 資料時間 | 輸入依 `available_at < analysis_date`、SEC filing cutoff、macro vintage 過濾；價格只在回測使用未來資料 | 保留 point-in-time 規則，另揭露模型記憶洩漏無法由 prompt 消除 |
| LLY | 7 個案例沒有情緒資料 | 不補造資料、不默默補值；freeze 前補來源，否則排除 primary denominator 並報告缺口 |
| 回測成本 | zero 與 Corwin–Schultz 已有；Buy-and-hold 現在與策略採同一成本 basis | 仍明確列出尚未含佣金、稅、借券、融資與市場衝擊 |
| 重複性 | deterministic seed 與 provider audit 已記錄；完整 test–retest 報告已加上 | 正式執行前先固定重複次數、案例與 seed policy |
| power | 原本只有 30-case inference gate，沒有 power | 使用 `scripts/power_plan.py` 做敏感度規劃，不宣稱 180 一定足夠 |

## 實驗前必須過的 gates

1. **方法 gate**：freeze primary comparison、方向性 coverage、成本口徑、hold 處理、重複跑規則與 power 假設。
2. **資料 gate**：每一個案例有資料集 hash、分析日、四域狀態、新聞／FinBERT 狀態與 LLY 缺口處理紀錄。
3. **模型 gate**：模型能完成引用格式、所有 evidence ID 真實存在、D 的 switched round 能遵守指定立場，並記錄 model identity、digest、context、timeout。
4. **執行 gate**：服務可恢復、API 不被長推論卡死、逾時可設定、舊錯誤不殘留、Docker 或 native fallback 至少有一條可重現路徑。
5. **報告 gate**：簡報與報告只使用已存在的 artifact；結果、信賴區間與限制在正式案例完成前不得填寫。

## 已固定的比較口徑

- Primary：`D vs C`，同一資料、同一模型、同一呼叫預算，唯一關鍵差異是 role-switch。
- A：單次 decision，作為低計算量 control；B：7 次 self-consistency，作為 voting control；C：固定立場 debate；D：role-switch debate。
- Buy-and-hold：用於報酬參考，不是 role-switch 的因果 control；在 Corwin–Schultz 報告中使用同一 benchmark transaction-cost basis。
- Hold：視為 abstention，報告 coverage、selective accuracy 與 hold opportunity cost，不把 Hold 當成免費正確。
- Primary endpoint：candidate layer、60 sessions、Corwin–Schultz、固定 case weight。
- McNemar 只使用 mutually directional cases；Holm correction 依既定 family 執行。少於 30 個 unique completed cases 時不做正式 aggregate inference。

## 資料洩漏處理

資料的時間邊界只能控制輸入快照，不能證明 LLM 沒有在預訓練中看過未來事件。正式執行前要把以下欄位寫入 run manifest：模型版本與 digest、公開的 knowledge-cutoff／release date 證據、分析日、資料集 hash、prompt hash。

2025 Test split 在模型 knowledge cutoff 未能確認早於測試資料時，只能標為 contamination-risk exploratory holdout，不得把它寫成乾淨的 out-of-sample 因果證據。Prompt 中的「只用 supplied report」是研究規則，不是防洩漏技術。

## LLY 缺口規則

不使用合成情緒、不用事後新聞、不把空集合改成中性分數。freeze 前若能取得符合公開時間與來源驗證的情緒資料，建立新 dataset version 並重新檢查 readiness；若不能，7 個案例從 primary denominator 排除，並在 flow diagram、表格與限制段落固定報告排除原因與剩餘樣本數。可另做 missing-sentiment sensitivity，但不得與 primary 混合。

## 目前可直接使用的工具

- `scripts/run_model_canary.py`：兩個 synthetic provider checks，不建立 job、不接觸歷史資料。
- `scripts/power_plan.py`：paired McNemar 的 design-effect 敏感度規劃。
- `GET /api/studies/{protocol_hash}/stability`：重複完整執行的 action agreement、forecast SD、confidence SD、evidence Jaccard。
- `GET /api/jobs/{id}`：預設只回傳摘要；需要完整 state 時加 `?detail=true`。
- `/docs`、`/redoc`、`/openapi.json`：API 合約已重新開放；remote mode 仍受研究室金鑰保護。

## 尚未完成且不能偽裝成完成

- 尚未找到能穩定完成正式 22-call 的模型；canary 只能作資格預檢。
- API 與推論仍在同一服務行程；worker isolation 仍是工程待辦。
- Docker daemon 目前未就緒，舊容器未重建；重建前必須先確認沒有工作執行。
- Windows owner / `dubious ownership` 根因尚未用系統管理權限修復。
- GitHub Support ticket 尚未送出；草稿見 `docs/github-support-ticket.md`。

