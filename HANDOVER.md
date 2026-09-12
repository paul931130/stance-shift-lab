# Stance Shift Research v3 — 系統設計交接文件

> **封存說明（2026-09-12）**：這份文件記錄 `v3-0908.x` 的設計與當時缺陷，供歷史稽核，不是目前操作規格。現行版本是 `v3-0912.1`；請改讀 [v3-0912.1 交接清單](docs/handoff-v3-0912.1.md)、[最終審查](docs/final-review-2026-09-12.md) 與 [遷移說明](docs/migration-v3-0912.1.md)。

版本基準：`v3-0908.1`（含 Fix 0–3 之後為 `v3-0909.1`）
撰寫日期：2026-09-09
對象：接手這個 codebase 的人，或六個月後的自己

---

## 0. 三十秒版本

這是一個**研究台**，不是交易系統。它回答一個問題：

> 讓兩個 LLM agent 針對同一份資料辯論、而且中途強制交換多空立場，
> 產生的投資決策會不會比「單次判斷」「多次投票」「不交換立場的辯論」更好？

作法是把四種決策協議（A/B/C/D）餵給**完全相同的一份不可變資料快照**，
輸出 Buy/Hold/Sell，然後用配對統計檢定比較 D 對 A、D 對 B、D 對 C。

執行路徑只有一條：
`research.ps1` → Docker Compose → `research_service` FastAPI → `http://127.0.0.1:8000`

---

## 1. 研究設計

### 1.1 四個 arm

| Arm | 名稱 | 呼叫數 | 機制 |
|---|---|---|---|
| A | 單次判斷 | 1 | 直接對中立報告出決策 |
| B | 自我一致性投票 | 7 | 同 prompt、不同 seed、取樣後多數決 |
| C | 固定立場辯論 | 7 | 3 輪 × (Bull, Bear) + 1 次裁決；立場不變 |
| D | **立場交換辯論** | 7 | 同 C，但第 2 輪雙方互換立場 |

呼叫數對齊（B=7 對上 C/D=7）是刻意的 compute matching。A=1 是不對齊的，
它的角色是「最便宜的 baseline」而不是等算力對照。

### 1.2 為什麼是「交換立場」而不是別的

理論定位（這是論文的核心貢獻，不要在實作時弄丟）：

**立場交換是一個論證完整性的診斷工具，不是真理發現機制。**

如果第 1 輪的 Bull 已經把所有支持買進的證據挖乾淨了，那麼第 2 輪被指派成 Bull 的
（原 Bear）agent 在**只讀中立報告**的情況下，應該找不到什麼新東西。
反過來，如果它找到一堆第 1 輪 Bull 沒提的證據，就代表第 1 輪的論證是不完整的。

這個推論**只在交換的那一輪被資訊隔離時成立**。如果交換後的 agent 看得到對手
第 1 輪講了什麼，它可以直接複述，量到的「新穎度」就變成複述能力而非完整性訊號。

`v3-0908.1` 的實作沒有隔離，這是已知的識別性缺陷；Fix 2 修的就是這件事。

對照組是 C：C 的第 2 輪是同一個立場的自然延伸，它的新穎度就是「第二輪自然新增證據」
的 baseline。論文的 claim 應該寫成 `D.novelty > C.novelty`，不是 `D.novelty > 0`。

### 1.3 樣本設計

- 股票池 `STUDY_TICKERS`：AAPL、NVDA、GOOGL、MSFT、AMZN、JPM、MCD、LLY、GE（9 檔）
  - ASTS 在 `CIKS` 裡但不在 `STUDY_TICKERS`，因為 FNSPID 沒有它的新聞。
  - 9 × 20 = **180 cases**，不是簡報上寫的 200。這個數字要在論文裡改對。
- 分析日 `QUARTER_DATES`：2021Q1–2025Q4 的季末，共 20 個
- 主要期間：分析日後 **60 個交易日**（30 / 90 為 robustness）
- 每個 case 跑四個 arm，180 × 4 = 720 次決策
- 每次決策的模型呼叫數：4（研究代理人）+ 1 + 7 + 7 + 7 = 26 次 → 全研究約 4,680 次呼叫

---

## 2. 系統架構

```
使用者（瀏覽器 / PowerShell CLI）
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ FastAPI (app.py)                                          │
│  · HMAC 簽章 session cookie / Bearer 存取控制             │
│  · 路由：資料集、job、批次、統計、匯出、備份              │
│  · 背景 worker thread：claim → advance → save_step 迴圈   │
└───────────────────────────────────────────────────────────┘
        │
        ├─── 資料採集（一次性，寫入不可變快照）
        │      data.py: download_prices / fetch_fundamental
        │               fetch_sentiment / fetch_macro
        │      → validate_dataset → Store.add_dataset
        │      → dataset_id = SHA-256(整份內容)
        │
        └─── 實驗執行（多次，只讀快照）
               engine.py: Engine.step（LangGraph 單節點，每次推進一步）
                 step 1  載入 inputs + 四組 memory
                 step 2  4 個研究代理人平行跑（technical/fundamental/sentiment/macro）
                 step 3  鎖定中立報告 → report_hash
                 step 4+ decision wave：A/B/C/D 依 round 依賴逐波推進
                 step n  Gatekeeper 產出四組最終決策
                 step n+1 回測 + 完成
               ↓
               backtest.py → cases / daily
               ↓
               reporting.py: study_report（跨 case 彙總 + 統計檢定）
```

### 2.1 為什麼用「每次只推進一步」的設計

`Engine.step` 是一個大 if-elif 鏈，每次呼叫只做一個階段，然後回傳完整 state。
Worker 拿到 state 就 `save_step` 寫進 SQLite。

好處：
- **任意時點可中斷可續跑**。服務重啟時 `Store.recover()` 把 running 改 paused，
  使用者按繼續就從上次的 state 接下去。
- **失敗隔離**。單一 case 的例外不會炸掉批次；錯誤訊息會做 API key 遮蔽後寫進 job。
- **每一步都有 checkpoint**，不需要重跑昂貴的 LLM 呼叫。

代價：state 是一個會長到 500 KB+ 的 JSON blob，每步都整份重寫。
180 cases 下這是可接受的；再大就要拆表（Fix 3.9 已經開始拆了）。

LangGraph 在這裡其實只包了一個節點，形同 no-op。保留它是為了未來擴充，
但如果要簡化依賴，可以無痛拿掉。

---

## 3. 資料層

### 3.1 四個研究域

| 域 | 來源 | 時間邊界依據 | 已知限制 |
|---|---|---|---|
| technical | Yahoo Finance（yfinance，fallback query1 Chart API） | 分析日前的 bar | 還原價會隨公司行動事後回算，**不是不可變 vintage** |
| fundamental | SEC XBRL companyfacts | `filed < analysis_date` **且** `end <= analysis_date` | 每個 tag 只取最新一筆，未區分 10-K/10-Q、FY/Q、amendment |
| sentiment | Alpha Vantage NEWS_SENTIMENT + FNSPID 本機 CSV | 分析日前 90 天，`available_at < analysis_date` | **v3-0908.1 沒有 relevance 過濾，證據多為泛市場文章**（Fix 0） |
| macro | FRED/ALFRED | `realtime_start = realtime_end = analysis_date` | 只有 FEDFUNDS、CPIAUCSL、UNRATE 三個序列 |

### 3.2 時間邊界的鐵律

這部分是整個系統做得最紮實的地方，**改動時要極度小心**：

- 所有證據比較都用**嚴格小於**（`available_at < analysis_date`），分析日當天發布的一律排除。
- `research_inputs` 要求分析日前至少 61 個交易日，否則 raise。
- 技術指標全部從分析日前的 close 計算，`available_at` 標成最後一根 bar 的日期。
- 總經證據強制要有 `vintage_date`，且 `vintage_date <= available_at`。
- 長期記憶（`Store.memory`）只取 `maturity_date < analysis_date` 的過去 case，
  也就是「當時已經結算完的歷史績效」。

任何新增資料來源都必須維持這條線。**沒有 look-ahead 是這個研究唯一的護城河。**

### 3.3 不可變快照

`Store.add_dataset` 用整份內容的 SHA-256 當主鍵。同樣的內容不會存兩份，
不同的內容一定是不同 ID。job config 記 `dataset_id` 與 `dataset_hash`（兩者相同）。

**跑實驗時絕不重新呼叫資料 API。** `prepare()` 會檢查
`dataset.requested_analysis_date == payload.analysis_date`，
避免拿 Q1 的快照去跑 Q2（90 天新聞窗會錯位）。

### 3.4 證據選取（`research_inputs`）

從快照的全部證據中選出要進 prompt 的子集：

- fundamental / macro：全數納入
- sentiment：上限 12 筆，來源間 round-robin 平衡
- technical：固定 4 個衍生指標（return20、mean20、mean60、volatility60_annual）

選取結果記在 `evidence_selection`，包含每域的 available / selected / strategy，
會進中立報告、進 prompt、進匯出檔。這是可審計的關鍵。

**快照保留全部下載到的證據；只有 prompt 看到子集。** 這樣事後可以重新選取。

---

## 4. 模型層

### 4.1 兩種 provider

```python
if protocol.model.startswith("ollama/"):
    # 直接打 /api/chat，用 Ollama 原生 structured output（format = JSON Schema）
    # keep_alive = -1 讓模型在整個 decision wave 期間留在記憶體
else:
    # lazy import litellm，走 response_format json_schema strict
```

lazy import 是刻意的：純本機操作不應該碰到任何雲端 SDK。

### 4.2 Ollama 的序列化陷阱

`Engine.step` 裡有這段：

```python
decision_workers = min(self.parallel_workers, len(prepared))
if self.uses_builtin_provider and protocol.model.startswith("ollama/"):
    decision_workers = 1
```

Ollama 預設單 runner。整波平行送過去，排隊中的 CPU request 會活得比 runner
keep-alive 還久，結果每個 socket 都等到 provider timeout，job 看起來永遠在跑。
**本機 Ollama 一定要序列化**；雲端 provider 才用 `RESEARCH_PARALLEL_WORKERS`（1–8，預設 4）。

注意這裡用 `uses_builtin_provider = model_call is generate` 來判斷，
所以注入式測試 model_call 不受影響。

### 4.3 決定性

`Engine.call_model` 的 seed：

```python
seed = (protocol.inference_seed + int(digest(call_key)[:8], 16)) % 2_147_483_647
```

同一個 call_key 永遠拿到同一個 seed。B 組 7 個 sample 的 key 不同
（`b-sample-1` … `b-sample-7`），所以 seed 不同。

**但 seed 不同不等於輸出不同**——`v3-0908.1` 的 temperature=0.2 讓 7 個 sample
逐字近乎相同（Fix 1b）。

### 4.4 輸出驗證的三道關

1. **JSON Schema**（provider 端強制）：`DECISION_SCHEMA` / `RESEARCH_SCHEMA`。
   辯論回合的 schema 會把 `action` enum 收窄成單一值（Bull → 只能 Buy）。
2. **`validate_decision`**：型別、範圍、引用 ID 是否存在於證據池。
3. **`validate_financial_numbers`**（只對 fundamental 域）：
   用 Decimal 抽出摘要裡的所有數字，比對被引用證據裡的數字集合，
   出現來源沒有的數字就拒絕。防止模型改寫財報數值、換單位、混期間。

第 3 道是這個系統少見的亮點，別把它拿掉。

### 4.5 研究代理人失敗時的 degraded fallback

研究代理人（4 個域摘要）失敗時**不會**讓整個 case 掛掉，而是退回
「把前 6 筆證據原文串起來」的確定性摘錄，標記 `status = "degraded"`。

然後 `reporting.py:study_report` 會把任何含 degraded 域的 job 整個排除在統計之外。
也就是說：degraded 讓流程走完並保留可審計紀錄，但不會污染研究結論。

---

## 5. 決策協議層（`protocol.py`）

### 5.1 `StudyProtocol`

frozen dataclass，`fingerprint` = `SHA-256(asdict(self))`。
**任何欄位變動都會產生新的 protocol_hash，不同 hash 的 job 不能合併統計**
（`study_report` 會 raise）。

`v3-0908.1` 的欄位：

| 欄位 | 預設 | 說明 |
|---|---|---|
| `version` | `"v3-0908.1"` | 白名單驗證；舊版 job 隔離不可 resume |
| `study` | `"study1"` | study1 = 單模型內比較；study2 = 跨模型彙總（尚未實作） |
| `model` | `"ollama/gemma3:4b"` | **Fix 1a 改為 qwen3:14b 並加小模型閘門** |
| `temperature` | 0.2 | **Fix 1b 加 `voting_temperature`** |
| `max_output_tokens` | 900 | |
| `max_rounds` | 3 | 硬性檢查 == 3 |
| `voting_samples` | 7 | 只能 5 或 7；7 才 `compute_matched` |
| `primary_horizon` | 60 | 硬性檢查 == 60 |
| `horizons` | (30, 60, 90) | **v3-0908.1 中 `evaluate` 沒有讀它**（Fix 3.5） |
| `cost_models` | ("zero", "corwin_schultz") | 同上 |
| `anonymize_ticker` | False | 開啟時整份報告的 ticker 換成 "ASSET" |
| `dataset_kind` | `"historical"` | historical / synthetic |
| `missing_data_policy` | `"allow_decision"` | 缺資料時是否強制 NoTrade |
| `bootstrap_seed` / `replicates` / `block_length` | 905 / 1999 / 20 | |
| `inference_seed` | 905 | |
| `provider_retry_attempts` | 2 | 1–3 |
| `study_universe` | 9 檔 | 硬性檢查 == `STUDY_TICKERS` |

### 5.2 `decision_plan`

產生 22 個 `DecisionCall`（1 + 7 + 7 + 7）：

```
a-decision                          A / decision      / NEUTRAL
b-sample-1 … b-sample-7             B / sample        / NEUTRAL
c-r{1,2,3}-agent-{a,b}              C / debate        / BULL, BEAR（固定）
c-adjudication                      C / adjudication  / NEUTRAL
d-r{1,2,3}-agent-{a,b}              D / debate        / 第 2 輪交換
d-adjudication                      D / adjudication  / NEUTRAL
```

agent-a 原始立場 BULL、agent-b 原始立場 BEAR。D 組 round 2 兩者互換。

### 5.3 `visible_history` — 資訊隔離規則

```python
if call.group in ("A", "B"):
    return []                     # A 與 B 永遠看不到任何辯論紀錄
return [同組、kind=debate、
        (裁決 → 全部；辯論 → round 嚴格小於當前 round)]
```

三條不變量：
- **A 和 B 的 prompt 是逐位元組相同的**（同一份報告、空 history、無 memory）。
  這是 B 作為 self-consistency 對照的前提。
- 跨組永遠不可見。C 看不到 D，反之亦然。
- 同輪不可見。round 2 的兩個 agent 看不到彼此的 round 2，
  所以「平行辯論」的語意成立。

Fix 2 會在最前面加上「D 組 round 2 完全隔離」這一條。

### 5.4 `decision_wave`

回傳「當下所有可執行的呼叫」，不跨越 round 依賴：
A 與 B 的全部未完成呼叫一律可跑；C/D 各自找到第一個未完成的 round，
該 round 的兩個呼叫一起放進 wave；該組三輪都完成才放裁決。

`Engine.step` 拿到 wave 之後會做 **A→B→C→D 交錯排序**，
讓四組的進度大致同步推進（對 UI 的即時感受有幫助，對結果無影響）。

---

## 6. Gatekeeper（`engine.py:gate`）

在候選決策與最終決策之間的風控層。它**不改變論證**，只可能收緊行動。

| 條件 | 觸發 reason | 效果 |
|---|---|---|
| 四域中有域完全無證據 | `missing_research_domains` | `force_no_trade` 政策下 → NoTrade |
| 有效引用率 < 0.8 或無引用 | `insufficient_valid_citations` | 同上（**v3-0908.1 中是死碼**，Fix 1c-ii） |
| confidence < 0.6 | `confidence_below_0.60` | Buy/Sell → Hold |
| 年化波動 > 0.8 | `annual_volatility_above_0.80` | Buy/Sell → Hold |
| 歷史準確率 < 0.5（n ≥ 5） | `historical_accuracy_below_0.50` | **僅警告，不改行動** |

輸出同時保留 `candidate_action`（進 gate 的候選）與 `action`（gate 後）。
Fix 4 之後這條鏈變成四段：`model_action`（模型自述）→ `derived_action`
（由 `expected_return_pct` 對中性帶推導）→ `candidate_action`（依
`protocol.action_source` 取前兩者之一）→ `action`（Gatekeeper 之後）。
`action_disagreement` 記錄前兩者不一致的 case，是審計訊號而非錯誤。

**主分析必須用 `candidate_action`**，否則無法分辨績效差異來自辯論機制還是風控層。
`v3-0908.1` 的回測只跑 `action`，Fix 1c-iii 加上 `decision_layer` 維度。

---

## 7. 記憶

### 7.1 短期記憶

就是 `visible_history` 回傳的同組辯論紀錄，隨 case 結束消失。沒有獨立儲存。

### 7.2 長期記憶（`Store.memory`）

只給裁決者（`messages_for` 裡的 `matured_same_group_memory`），
辯論回合看不到。內容是：

- 同 protocol_hash、同 ticker、**同 arm** 的過去 case
- 分析日嚴格早於當前 case
- 60 日期間、corwin_schultz 成本、status complete
- **maturity_date 早於當前分析日**（也就是當時已經結算完的）
- 排除任何含 degraded 研究域的 job
- 同一個 analysis_date 只取一筆（重跑不算新的獨立歷史）
- 最多 20 筆，新到舊

**per-arm 命名空間是刻意的**：A 的裁決者不能看到 D 的歷史，否則跨臂污染。

已知效能問題：它會反序列化每一筆 job 的完整 state（Fix 3.9）。

---

## 8. 回測（`backtest.py`）

### 8.1 目前的口徑（v3-0908.1）

| 項目 | 值 |
|---|---|
| 進場 | 分析日後第 1 個交易日的 **open** |
| 出場 | 第 `horizon` 個交易日的 **close** ← 基準不一致，Fix 3.4 改 open-to-open |
| 部位 | Buy = +1 單位多、Sell = −1 單位空、Hold/NoTrade = 0 |
| 成本 | Corwin-Schultz 高低價價差估計，進出各半個價差 |
| 進場成本估計 | `spread(past[-2], past[-1])` ← 單次兩日估計，變異極大，Fix 3.3 |
| 出場成本估計 | `spread(selected[-2], selected[-1])` |
| 基準 | 同一標的、同一持有窗口的 buy-and-hold（**不是 SPY 或指數**） |
| 無風險利率 | 0（明示標註為 explicit zero baseline） |
| 破產 | equity ≤ 0 標 `invalid_insolvent_short`，且**整個 case 被排除**，Fix 3.1 |

### 8.2 Corwin-Schultz 實作正確性

```python
def spread(previous, current):
    beta = ln(H_p/L_p)² + ln(H_c/L_c)²
    gamma = ln(max(H)/min(L))²
    denominator = 3 - 2√2
    alpha = max(0, (√(2β) − √β)/denominator − √(γ/denominator))
    return 2 * tanh(alpha / 2)
```

最後一行等價於論文的 `S = 2(e^α − 1)/(e^α + 1)`，**這是對的**。
`max(0, ...)` 是標準的負價差歸零處理。

未做的部分：原論文對隔夜跳空有調整，這裡沒有。屬於已知簡化。

### 8.3 `metrics`

從日報酬序列算 total_return、max_drawdown、Sharpe（年化 ×√252）。
`std <= 1e-12` 時 Sharpe 回 `None` ——這正是 v3-0908.1 全 Hold 時發生的事。

---

## 9. 統計（`statistics.py` + `reporting.py`）

### 9.1 三個檢定

| 方法 | 用途 | 假設 | 已知弱點 |
|---|---|---|---|
| `mcnemar` 精確二項式 | 方向準確率的配對比較 | case 獨立 | **同期不同股票被當成獨立**（回傳值自帶 warning） |
| `jobson_korkie_memmel` | Sharpe 差異 | IID 聯合常態 | 金融日報酬不滿足，只作參考 |
| `ledoit_wolf_block` | Sharpe 差異（主要） | 平穩、有限四階動差 | 需要 n ≥ 3 × block_length |

`ledoit_wolf_block` 的實作細節（Ledoit & Wolf 2008, eq. 2, 5–9）：
- 原樣本 studentizer 用 **Bartlett HAC**，帶 `n/(n−4)` 修正
- bootstrap 樣本 studentizer 用**自然非重疊 block sums**（eq. 9）
- circular block 重抽樣，`method="higher"` 取分位數
- 退化樣本超過 10% 就 raise，不給不可靠的推論

這一段實作品質高於一般碩論水準，**改的時候要對照論文，不要憑感覺調**。

### 9.2 多重比較

`holm_adjust` 在每個 `(horizon, cost_model, method)` family 內對
D vs A/B/C 三個 p 值做 Holm 校正。

### 9.3 `study_report` 的樣本納入規則

按順序：
1. 只取 `status == "complete"` 的 job
2. 排除任何含 degraded 研究域的 job
3. 檢查所有 job 的 protocol_hash 相同，否則 raise
4. **同一 (ticker, analysis_date) 只取 `created_at` 最早的那一筆**
   ——「看過結果再重跑」不能替換已觀察到的結果，這是防選擇偏誤的關鍵設計
5. 該 case 必須四組都有 complete 的 row，否則整個 case 跳過

第 5 條在 v3-0908.1 造成「任一組做空爆掉 → 整個 case 消失」的偏誤（Fix 3.1）。

### 9.4 投組建構

對每個 `(horizon, cost_model)`：
- 收集每組每日的 sleeve 報酬到 `by_day[group][date][case]`
- 取四組日期的交集
- 每個日期做等權平均 → 該組的日報酬序列
- 基準用同樣手法對 `benchmark_return` 做

`statistics.py:aligned_portfolio_returns` 寫了正確的固定權重版本但**沒被呼叫**，
`reporting.py` 自己用 `np.mean` 對「當天恰好有部位的 case」平均，
投組成分隨日期變動。文件與實作不一致（Fix 3.7）。

---

## 10. 儲存（`storage.py`）

### 10.1 Schema

```sql
datasets(id TEXT PK, ticker TEXT, content TEXT, created_at TEXT)
jobs(id TEXT PK, status TEXT, wants_run INTEGER,
     config TEXT, state TEXT, error TEXT, created_at TEXT, updated_at TEXT)
```

`PRAGMA journal_mode=WAL`。沒有 migration 機制，只有
`CREATE TABLE IF NOT EXISTS`（Fix 3.9 會加第三張表，需要一併補回填程序）。

### 10.2 Job 狀態機

```
queued ──claim()──> running ──save_step(ok)──> queued（還沒完成）
                                            └─> complete（finished）
                       │
                       ├──save_step(error)──> paused
                       └──control(pause)────> paused
paused ──control(resume)──> queued
任意 ──control(cancel)────> cancelled（終態）
服務重啟 ── recover() ──> running 全部改 paused
```

`claim()` 用 `BEGIN IMMEDIATE` 取得寫鎖，確保單一 worker 語意。

### 10.3 版本隔離

`claim()` 與 `control("resume")` 都會檢查 job 的 protocol version
是否等於當前 `StudyProtocol().version`。不等於就拒絕執行，
但**紀錄完整保留、仍可匯出**。要重跑必須用 `/api/jobs/{id}/clone` 複製到新版。

這是防止「不同協議版本的結果被混在一起」的最後一道防線。

---

## 11. API 與安全

### 11.1 存取控制

- `RESEARCH_ACCESS_KEY`：遠端模式（`RESEARCH_REMOTE=true`）強制至少 32 字元
- 登入後發 HMAC-SHA256 簽章的 session cookie，TTL 12 小時，httponly
- 也接受 `Authorization: Bearer <access_key>`（供 CLI 使用）
- Host header 白名單 `RESEARCH_ALLOWED_HOSTS`
- WebSocket 額外檢查 origin 與 client host

**這是單一研究室的共用憑證模型。** 沒有使用者隔離、沒有配額、沒有加密憑證庫。
要變成多人服務必須整個重做（見 §13）。

### 11.2 憑證儲存

`settings.py:Settings` 把 API key 寫進 `<data_root>/private/settings.json`，
權限 0o600、目錄 0o700、用 `os.replace` 原子寫入，並同步到 `os.environ`。

`/api/settings` 是 **write-only**：GET 只回「這個欄位有沒有設定」的布林值，
不回實際值。錯誤訊息會對所有已知 key 做字串替換遮蔽。

### 11.3 主要路由

| 路由 | 用途 |
|---|---|
| `POST /api/datasets/download` | 四域平行採集，寫入不可變快照（`refresh=false` 會重用） |
| `POST /api/datasets/import` | 匯入已授權的離線資料 |
| `POST /api/sources/check` | 實機驗證各來源是否可用 |
| `GET /api/readiness` | 9×20 case 矩陣的資料完整度 |
| `POST /api/jobs` / `POST /api/batches` | 建立單一或批次實驗（批次上限 200） |
| `POST /api/jobs/{id}/{pause\|resume\|cancel}` | 生命週期控制 |
| `POST /api/jobs/{id}/clone` | 複製到當前協議版本 |
| `GET /api/jobs/{id}/export` | 產出研究 ZIP（見 §12） |
| `GET /api/studies/{protocol_hash}` | 跨 case 統計報告 |
| `GET /api/backup` | WAL-safe SQLite 快照 |

---

## 12. 匯出產物

`GET /api/jobs/{id}/export` 產生確定性 ZIP（timestamp 由 job metadata 推導，
所以同樣的 job 匯出兩次的位元組完全相同）：

| 檔案 | 內容 |
|---|---|
| `manifest.json` | schema 版本、job metadata、**每個檔案的 SHA-256**、模型 digest |
| `protocol.json` | 完整 job config（含 protocol 與 protocol_hash） |
| `neutral_report.json` | 四組共用的中立報告（決策前鎖定） |
| `evidence_registry.json` | 進入 prompt 的全部證據 |
| `decisions.json` | 四組的 candidate + gated 決策與 gate 診斷 |
| `debate_transcript.md` | 22 次呼叫的 rationale 與引用，人類可讀 |
| `state_trace.json` | 完整 state（含每次呼叫的 audit、seed、prompt_hash、usage） |
| `memory.json` | 本次使用的長期記憶 |
| `cases.csv` | 逐 case × group × horizon × cost 的回測結果 |
| `daily_returns.csv` | 逐日報酬與基準 |
| `summary.csv` / `statistics.json` | 跨 case 彙總與統計檢定 |

`csv_text` 對以 `=`、`+`、`-`、`@` 開頭的字串加單引號前綴，
防止試算表把模型輸出當公式執行。

---

## 13. 已知限制（誠實清單）

改任何東西之前先讀這一節。

### 研究效度
1. **v3-0908.1 的 sentiment 證據多數與目標公司無關**（Fix 0）
2. **四個 arm 在 4B 模型下輸出完全相同**，實驗零檢定力（Fix 1）
2b. **系統性 Hold 偏誤**（Fix 4）：prompt 含一條永遠成立的 Hold 條款
   （「or no personal risk preference was supplied」，而 risk preference 從不提供）；
   「materially positive」無數值定義；Hold 的 `correct = None` 使它在分析口徑上
   永遠不會錯；對稱辯論讓裁決者只能數票且票數恆為 1:1；
   裁決者 prompt 直接寫「inconclusive → choose Hold」；報告缺基準率錨點
3. **立場交換沒有資訊隔離**，完整性診斷不可識別（Fix 2）
4. 基準是同標的 buy-and-hold，不是市場指數，算不出 alpha
5. 沒有借券費、融資成本、稅、滑價、強制平倉模型
6. 重疊持有期（每季開新倉、持有 60 日）造成同期相依，McNemar 沒有處理
7. Yahoo 還原價會事後回算，快照不是真正的 point-in-time vintage
8. SEC fact selector 沒有區分 form / fiscal period / duration / amendment
9. 只有 3 個總經序列、4 個技術指標，特徵規格未預註冊

### 工程
10. SQLite 沒有 migration 機制
11. `Store.memory()` 是 O(全部 job × state 大小)
12. FNSPID 每個 case 都全檔掃描 CSV，沒有索引
13. 取消只在 wave 邊界生效，不會中斷進行中的模型呼叫
14. 前端每 5 秒無條件輪詢 `/api/dashboard`，即使沒有執行中的 job
15. 沒有 `pyproject.toml`、沒有 CI、沒有 LICENSE
16. 根目錄還留著舊版 Next/Sites 原型（`app/`、`lib/`），有 4 個 high severity npm 依賴問題

### 治理
17. 沒有 preregistration，主分析口徑尚未凍結
18. 沒有不可變的 study manifest（180 個 dataset_id + run_id 的固定清單）
19. 資料授權未處理：FNSPID 的 LICENSE 與 README 對商業權利說法不一致；
    Yahoo、Alpha Vantage 有使用範圍限制；FRED 有指定顯示文字要求

---

## 14. 正式研究的執行順序

不要跳步。

1. **修 Fix 0–3**，全測試通過。
2. **重建兩個資料集並人工抽查**（NVDA 2024-12-31、AAPL 2023-06-30）。
   打開 `evidence_registry.json`，逐筆確認 sentiment 證據真的跟這家公司有關。
3. **跑 pilot：3 檔 × 4 季 × 4 arm = 48 次決策**。
   看 `pilot_diagnostics`：
   - 任一組 hold_rate > 40% → **停下來換模型**
   - D vs A 分歧率 < 20% → **停下來檢查 prompt 與 temperature**
   - B 的 vote_agreement > 0.95 → **停下來調 voting_temperature**
   - band 外 case 的方向準確率 < 45% → **停下來查 prompt**。
     這條比 hold_rate 更重要：它代表 Fix 4 只是把 Hold 換成了硬幣，
     比全 Hold 更糟。不要靠調 `hold_band_sigma` 讓它看起來變好。
4. **凍結 preregistration**。一份不可修改的文件，明列：
   主要假設、主要比較（D vs C 還是 D vs 全部）、
   主分析的四個維度（decision_layer=candidate、horizon=60、
   cost_model=corwin_schultz、portfolio_basis=all）、
   效果量、排除規則、停止規則。其他設定一律只作敏感性分析。
5. **建立 study manifest**：180 個 (ticker, date, dataset_id) 的固定清單，
   連同 code commit hash 一起凍結。
6. **跑正式批次**。跑完不修改任何東西再看結果。
7. **分析與寫作**。

---

## 15. 常見操作

```powershell
# 首次設定（隱藏輸入，寫進 git-ignored 的 .env.research）
.\research.ps1 setup

# 啟動 / 檢查 / 日誌
.\research.ps1 start
.\research.ps1 doctor
.\research.ps1 logs

# 單一 case
.\research.ps1 collect NVDA 2024-12-31
.\research.ps1 run NVDA 2024-12-31
.\research.ps1 jobs

# 測試
docker compose -f compose.research.yaml run --rm --no-deps research `
  python -m unittest discover -s research_service/tests -p "test_*.py"
node --check research_service\static\app.js
```

環境變數速查：

| 變數 | 預設 | 用途 |
|---|---|---|
| `RESEARCH_DATA_DIR` | `research-data` | SQLite 與私有設定的根目錄 |
| `RESEARCH_ACCESS_KEY` | 空 | 存取金鑰；remote 模式需 ≥32 字元 |
| `RESEARCH_REMOTE` | `false` | 遠端模式（強制 secure cookie） |
| `RESEARCH_PARALLEL_WORKERS` | 4 | 1–8；本機 Ollama 會被強制降為 1 |
| `RESEARCH_ENABLE_LIVE` | `false` | Finnhub 即時功能開關 |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | |
| `OLLAMA_KEEP_ALIVE` | `-1` | 讓模型在 wave 期間常駐 |
| `FNSPID_NEWS_PATH` | 空 | 本機 FNSPID CSV 路徑 |
| `SEC_USER_AGENT` | 空 | **必須含 `@`**，否則 SEC 域直接跳過 |
| `ALPHA_VANTAGE_API_KEY` / `FRED_API_KEY` / `FINNHUB_API_KEY` | 空 | |

---

## 16. 給接手的人的三句話

1. **時間邊界不能碰。** 這個研究唯一站得住的地方就是沒有 look-ahead，
   任何「順手放寬一下」的改動都會毀掉整個結論。
2. **protocol_hash 是研究的身分證。** 改任何 `StudyProtocol` 欄位就是新研究，
   舊結果不能混進來。系統會擋，別想繞過。
3. **測試通過不等於研究成立。** `v3-0908.1` 的 38 個測試全部綠燈，
   但四個 arm 輸出一模一樣、統計全部無法計算。
   驗收標準是 `pilot_diagnostics` 的 `verdict == "proceed"`，不是測試綠燈。
4. **降低 Hold 率本身不是目標。** 逼模型多下注很容易，但如果多出來的
   Buy/Sell 只是硬幣，方向準確率會掉到 50% 且變異放大，那比全 Hold 更糟。
   要看的是「band 外 case 的準確率顯著高於 50%」，不是 Hold 率的數字。
