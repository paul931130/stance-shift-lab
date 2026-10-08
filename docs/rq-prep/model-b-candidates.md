# RQ2 模型 B 選擇備忘

模型 A＝`ollama/qwen3:32b`（Ollama digest `030ee887…7840`，約 20 GB，Qwen 沒有公布知識截止日）。本文件沒有呼叫任何模型或付費 API。外部事實引用官方頁面（2026-10-08 讀取），無法確認的項目標為**未核對**。

## 研究者決定（2026-10-08）

- **模型 B＝`ollama/gemma3:27b`**，放在實驗室 Ollama 伺服器上（A 仍在 RTX 5090）。
- **備案＝`gemini/gemini-2.5-flash`**：只有在實驗室硬體不足（VRAM < 24 GB、無法固定 Ollama 版本，或無法保留足夠時段）時才改用。
- gemma3:27b 還沒有任何探針結果；第五節的資格檢查全部【待執行】，完成前不能登記。下方的比較表保留，作為決策紀錄。

## 一、結論（決定前的建議）

1. **若實驗室 Ollama 伺服器可用，而且 VRAM ≥ 24 GB**：建議選一個與 Qwen 不同家族的開放權重模型（首選 `gemma3:27b`，次選 `mistral-small3.2:24b`），放在實驗室伺服器上；A 繼續放在 RTX 5090。好處是可以鎖權重 digest、不會互相擠占 VRAM、不必支付 API 費用。
2. **若實驗室不可用**：用 `gemini/gemini-2.5-flash`。它是唯一已經做過記憶探針與匿名辨識的候選，費用低，但無法鎖權重，seed 也可能沒有套用。
3. **不建議**把 A、B 都放在同一張 32 GB 的 5090 上輪流載入：每輪都要重新載入模型，慢，而且載入時間還沒有實測。
4. 不論選哪一個，正式登記前都要跑完第五節的資格檢查。

## 二、可重現性：本機權重 digest 對 API 模型

| 面向 | Ollama 開放權重（本機或實驗室） | Gemini API |
|---|---|---|
| 權重身分 | 登記時鎖定 digest，每一步推理前後核對，digest 改變則整案作廢（RQ1 實測 9,727 次核對通過） | 只有模型名稱字串，供應商可能在背後更新；無法提供 digest，`model_identity` 只能記錄名稱與回應中的版本欄位 |
| Seed | 程式把 seed 寫入 Ollama 的 `options.seed` | 程式只在 LiteLLM 回報支援時才送 seed（`models.py`：「Some providers (e.g. Gemini) reject `seed`」）；是否套用以 audit 的 `seed_applied` 為準。即使套用，也不保證結果完全相同 |
| 版本 | Ollama 伺服器版本與量化格式可以固定，但目前資料庫沒有記錄 Ollama 版本（見 RQ1 稽核第 5 項） | 由供應商決定；官方頁面寫 2.5 Flash「最近更新 2025 年 6 月」 |
| 長期可用性 | 權重檔可以自行保存 | 官方頁面寫 2.5 系列不會被棄用、會持續提供「until further notice」，但目前只開放給曾經用過 2.5 的帳號，並建議新專案改用較新的 Flash 版本[^g1] |
| 資料外流 | 不出本機或實驗室 | 證據（已匿名化）會送到 Google |

API 模型的重現性只能做到「記錄」，做不到「鎖定」。報告中必須寫明這一點，並在執行前後各跑一次 canary，比對回答是否改變。

## 三、VRAM 與部署

- 只算權重：qwen3:32b 約 20 GB＋`gemma3:27b` 17 GB[^o1]＝約 37 GB；＋`mistral-small3.2` 15 GB[^o2]＝約 35 GB；＋`gpt-oss:20b` 14 GB[^o3]＝約 34 GB。三種組合都超過 32 GB，還沒算 KV cache（context 8192）。
- 結論：在一張 5090 上，A、B 無法同時常駐。Ollama 會依 `OLLAMA_KEEP_ALIVE` 與 `OLLAMA_MAX_LOADED_MODELS` 卸載模型[^o4]，所以每次換人發言都可能重新載入。
- 輪流載入的代價（**未實測**）：每次 15–30 秒、每案約 7 次切換 → 每案多 1.8–3.5 分鐘，180 案約多 5–10.5 小時。
- 能和 A 同時放進 32 GB 的模型，大約只有 8 GB 以下的小模型，但它們與 32B 的能力差距太大，RQ2 會變成「強模型配弱模型」，不建議。
- 建議部署：A 在 5090（與 RQ1 相同的映像與 digest），B 在實驗室伺服器或 API。程式需要支援「每個模型各自的端點」（目前只有一個 Ollama 端點），這屬於 Model Router 的開發範圍。

## 四、候選比較

| 候選 | 家族 | 大小（Ollama） | 知識截止 | 記憶／辨識探針 | 費用 | 授權 | Seed／思考 | 備註 |
|---|---|---|---|---|---|---|---|---|
| `gemini/gemini-2.5-flash`（**備案**） | Google Gemini（API） | — | 2025 年 1 月[^g1] | **已做**（舊協議 39f71a9c）：2022／2023／2024 方向正確率 44%／33%／44%，都低於多數方向基準 67%／67%／56%；2025 年 69% 對 72%；匿名辨識 6/18（AAPL ×2、AMZN、JPM、MSFT、NVDA） | 輸入 $0.30／M、輸出 $2.50／M（含思考 tokens）；有免費層[^g2]；RQ2 約 US$4–8 | Google API 條款 | seed 可能不套用；Flash 可以關閉思考（`models.py`） | 截止日落在樣本期間（2021–2025）中間，所以 2021–2024 有被記住的風險，雖然探針沒有顯示；目前只開放給既有使用者 |
| `gemma3:27b`（**已選定**） | Google Gemma | 17 GB（q4_K_M）；q8_0 30 GB[^o1] | 2024 年 8 月[^m1] | 【待執行】 | 只有 GPU 時間 | Gemma Terms of Use（自訂條款，非 OSI）[^m1] | Ollama seed 可用；不是推理模型 | 與 Qwen 不同家族，大小與 A 接近；結構化 JSON 的遵循度需要 canary 驗證 |
| `mistral-small3.2:24b` | Mistral | 15 GB，128K context[^o2] | 官方沒有公布（**未核對**） | **未做** | 只有 GPU 時間 | Apache 2.0[^m2] | Ollama seed 可用；不是推理模型 | 授權最寬鬆；截止日要靠記憶探針實測 |
| `gpt-oss:20b` | OpenAI | 14 GB[^o3] | 模型卡沒有寫（**未核對**） | **未做** | 只有 GPU 時間 | Apache 2.0[^m3] | 推理強度只有 low／medium／high，模型卡沒有說可以關閉[^m3] | 與「關閉思考」的設定不一致，不建議作為首選 |
| `llama3.3:70b` | Meta Llama | 43 GB[^o5] | 2023 年 12 月[^m4] | **未做** | 只有 GPU 時間 | Llama 3.3 Community License（自訂）[^m4] | Ollama seed 可用 | 5090 放不下；實驗室若有 ≥48 GB 的 GPU 才考慮。參數量是 A 的兩倍多，能力混淆更嚴重 |
| `gemini-3-flash-preview` | Google Gemini（API） | — | 模型列表沒有寫（**未核對**） | **未做**（報告已註明 2.5 Flash 的探針不能代替） | 未核對 | Google API 條款 | 同上 | 報告的探索性複製用的就是它；目前是 Preview，身分不穩定 |

不要選 Qwen 系列，也不要選以 Qwen 蒸餾的模型（例如部分 DeepSeek-R1 distill），否則就不是「不同基礎模型」。

## 五、登記前必須完成的資格檢查（每個候選都一樣）

| 步驟 | 指令／作法 | 通過條件（建議） | 是否需要 GPU／API |
|---|---|---|---|
| 1. 記憶探針 | `python scripts/memory_probe.py --model <B> --protocol-hash <新 hash>`，63 題、溫度 0 | 每一年的方向正確率都沒有明顯高於多數方向基準；結果存成 `docs/<B>-memory-probe.json` | 要 |
| 2. 匿名辨識 | `python scripts/memory_probe.py --mode identify --model <B> ...`，2023-06-30、2024-06-30 共 18 題 | 只記錄、不設門檻；報告中寫明辨識率與線索 | 要 |
| 3. 格式 canary | `python scripts/run_model_canary.py --model <B>` | `status=pass`（JSON、引用、交換輪的立場遵循） | 要 |
| 4. 能力 pilot | 3–5 案、獨立資料庫副本，跑 AB／BA 的 C、D | 驗證重試率、`unsupported_numbers`、輸出截斷、延遲都在可接受範圍；**不看準確率** | 要 |
| 5. 身分鎖定 | Ollama：記錄 digest 與伺服器版本；API：記錄解析後的模型版本字串 | 可以寫進 `preregistration_meta` | — |

注意：現有的 Gemini 2.5 Flash 與 qwen3:32b 探針都是用舊協議 `39f71a9c` 跑的。如果 RQ2 的證據格式改變，建議用新協議重跑步驟 1、2，兩個模型都要。

## 六、實驗室 Ollama 使用方式

### 要問實驗室管理員的事

1. GPU 型號、張數、每張 VRAM；是否和其他人共用；能不能保留一段連續時間（180 案約需 10–20 小時）。
2. Ollama 版本（RQ1 用的是 0.35.0），能否固定版本、不自動更新。
3. 可以自行 `ollama pull` 嗎？允許哪些模型？硬碟空間是否足夠。
4. 遠端存取方式：SSH 帳號、VPN、跳板機；是否限制連出或連入。
5. `OLLAMA_NUM_PARALLEL`、`OLLAMA_KEEP_ALIVE`、`OLLAMA_MAX_LOADED_MODELS` 的設定。RQ1 要求單併發，模型常駐可以避免重複載入。
6. 有沒有使用規範，例如資料是否可以放在伺服器上、紀錄保存多久。

### 安全的連線方式

Ollama 預設只綁定 `127.0.0.1:11434`；改成 `0.0.0.0` 就會對整個網路開放，而官方 FAQ 沒有提供任何驗證機制，只建議另外架反向代理[^o4]。任何能連到 11434 埠的人都可以呼叫、下載或刪除模型。

- **建議：SSH 本機轉發**。伺服器端維持 `127.0.0.1:11434`，本機執行 `ssh -N -L 11435:127.0.0.1:11434 <帳號>@<實驗室主機>`，研究服務改連 `http://127.0.0.1:11435`（容器內則用 `host.docker.internal:11435`）。流量經 SSH 加密，不需要開放任何埠。
- **可以接受**：校內 VPN 加上防火牆，只允許特定 IP 連 11434；或用有驗證的反向代理（HTTPS＋token）。
- **不要**：把 11434 直接開放到公網或整個校園網路。
- 連線中斷時，RQ1 的斷路器會暫停派發並等待恢復；SSH 通道建議用 `autossh` 或在中斷後手動重連。digest 在推理前後都會核對，所以就算連到別台機器也會被擋下。

## 來源

[^g1]: Google AI for Developers, Gemini 2.5 Flash 模型頁：https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash ；模型總覽：https://ai.google.dev/gemini-api/docs/models
[^g2]: Gemini API 價格：https://ai.google.dev/gemini-api/docs/pricing
[^o1]: Ollama gemma3 tags：https://ollama.com/library/gemma3/tags
[^o2]: Ollama mistral-small3.2：https://ollama.com/library/mistral-small3.2
[^o3]: Ollama gpt-oss：https://ollama.com/library/gpt-oss
[^o4]: Ollama FAQ（OLLAMA_HOST、KEEP_ALIVE、MAX_LOADED_MODELS、NUM_PARALLEL）：https://docs.ollama.com/faq
[^o5]: Ollama llama3.3：https://ollama.com/library/llama3.3
[^m1]: Gemma 3 model card（知識截止 2024 年 8 月；Terms of Use）：https://ai.google.dev/gemma/docs/core/model_card_3
[^m2]: Mistral-Small-3.2-24B-Instruct-2506（Apache 2.0）：https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506
[^m3]: gpt-oss-20b model card：https://huggingface.co/openai/gpt-oss-20b
[^m4]: Llama 3.3 model card（預訓練資料截止 2023 年 12 月）：https://github.com/meta-llama/llama-models/blob/main/models/llama3_3/MODEL_CARD.md
