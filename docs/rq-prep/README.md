# RQ 準備文件索引（2026-10-08）

**目前操作入口：[2026-10-17 正式實驗前操作單](preformal-runbook-20261017.md)。** 舊表格與預算只保留歷史脈絡。

> 2026-10-15 更新：以下決策表保留 10 月 8 日的規劃脈絡，不代表目前仍未實作。Model Router、Domain Debate、Final Aggregator 與 web 接線均已存在；v7 將 RQ2 的 BB、至少三 seed 與 RQ3 的兩個對照列為必要。現況以 [修正進度](../review/remediation-status-2026-10-15.md) 為準。草稿內舊預算與建議不可直接用作正式登記。

依據 `report/application-meeting-20261006.tex` 的新版 RQ1／RQ2／RQ3，以及 `report/revisions/2026-10-06-agent-diversity/Part-C-研究方法Review.md`。這裡的文件都是草稿或稽核紀錄，不是正式登記。

| 文件 | 內容 |
|---|---|
| [rq1-promotion-audit.md](rq1-promotion-audit.md) | 已完成的 RQ1（v3-1002.3，`b1da80ee…`，180/180）依 Part-C 清單逐項唯讀稽核 |
| [rq2-preregistration-draft.md](rq2-preregistration-draft.md) | RQ2 異質模型事前登記草稿（A＝qwen3:32b，B＝gemma3:27b），含決策表與預算 |
| [rq3-preregistration-draft.md](rq3-preregistration-draft.md) | RQ3 領域分工事前登記草稿，含決策表與預算 |
| [model-b-candidates.md](model-b-candidates.md) | 模型 B 比較、可重現性、VRAM 限制、實驗室 Ollama 使用方式 |
| [gemma3-qualification-runbook.md](gemma3-qualification-runbook.md) | gemma3:27b 三項資格檢驗的實際指令（SSH 通道、記憶探針、canary） |

## 已就緒

- RQ1 的紀錄稽核：14 項中 6 項已核對、7 項部分、1 項未核對（研究者確認）。主要比較的數字（C 105/180、D 99/180、方向不同 16 案、McNemar p≈0.21）已由資料庫重算，與報告一致。
- RQ2 的設計骨架、資格檢查清單、呼叫與 GPU 預算；模型 B 已決定為 `ollama/gemma3:27b`（備案 Gemini 2.5 Flash）。
- RQ3 的設計骨架、五項優先待決事項、各方案的呼叫與 GPU 預算。

## 需要研究者決定（依阻擋程度排序）

1. **RQ1 是否升格為新版正式結果**（稽核第 14 項），以及是否先補上事前登記文件中 `b1da80ee` 的補記。這會影響報告的結果章節，也決定 RQ2／RQ3 是否需要重跑 homo／Generalist 組。
2. **RQ2、RQ3 的 homo／Generalist 組要重跑還是沿用 RQ1**。建議重跑（同一 hash 與映像），每題每案多 14 次呼叫，約多 5.2 小時。
3. **RQ3 的領域辯論規則**：只跑固定立場、只跑立場交換、或兩者都跑。這決定 Domain 模組要實作的範圍，以及每案 25–58 次呼叫的預算。
4. **RQ3 的公平比較與 Aggregator 輸入**：匹配什麼資源、Aggregator 只讀 View 還是也讀證據或逐字稿、View 的結構與 abstain 規則。
5. **RQ2 的 AB／BA 執行與合併方式、B/B 控制、Judge 模型與盲化**。
6. 三題的多重檢定 family、失敗與缺失處理規則、記憶規則（建議沿用 RQ1）。
7. 實驗室 Ollama 的存取條件（見 `model-b-candidates.md` 第六節）。若硬體不足，改用備案 Gemini 2.5 Flash。

## 10 月 8 日開發清單（核心程式現已實作；正式研究完整度另核對）

- Model Router：一個協議內支援兩個模型、各自的端點與 digest 鎖定，並記錄 agent identity、原始立場、各輪立場。
- Domain Debate Module 與 Final Aggregator：依領域切分證據、驗證引用範圍、產生 View、整合。
- 建議把 Ollama 伺服器版本寫入稽核紀錄（RQ1 稽核的缺口）。

## 需要 GPU／API 時間

| 工作 | 資源 | 估計 |
|---|---|---|
| RQ1：以凍結映像重算 Sharpe／LW／群聚區間 | 只需 CPU | 數分鐘 |
| gemma3:27b 資格檢查：記憶探針、匿名辨識、canary、3–5 案 pilot | 實驗室 GPU＋5090 | 約 1–2 小時 |
| qwen3:32b 在新協議下重跑探針（建議） | 5090 | 不到 1 小時 |
| RQ2 正式 180 案（含 homo 重跑；加 B/B 再約 +5 小時） | 5090＋實驗室 GPU | 約 15.5 小時（約 US$11.7 的 5090 費用）；B 的延遲未實測 |
| RQ3 正式 180 案（固定立場、V＝0、重跑 G_C、加低預算敏感性） | 5090 | 約 15.2 小時，約 US$11.4 |

預算的換算依據：E2′ 實測約 22 案／小時，相當於約 7.4 秒／呼叫，RTX 5090 每小時 US$0.75。正式執行前都要用 canary 重新量測。
