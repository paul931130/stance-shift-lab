# 用實驗室電腦的 GPU 跑後續實驗（2026-11-04）

程式和資料留在這台電腦，透過 SSH 通道使用實驗室電腦上的 Ollama（GPU）跑 RQ2／RQ3 的資格檢查與 pilot。
詳細步驟仍以 [正式實驗前操作單](preformal-runbook-20261017.md) 為準；這頁補連線設定和目前狀態。

## 一、目前進度（2026-11-04）

| 項目 | 狀態 |
|---|---|
| RQ1（D vs C，qwen3:32b，180 案） | 完成。C 105/180、D 99/180，McNemar p≈0.21，D 沒有優於 C。屬已見樣本的回溯比較 |
| RQ2（異質模型 AA/AB/BA/BB）與 RQ3（領域辯論＋兩個對照） | 程式、合成測試、離線封裝完成；**沒有真實模型資格、pilot、登記或結果** |
| 上次真實模型嘗試 | 2026-10-15 GPUtw 的 qwen canary 因反向代理 HTTP 524 中斷，不是模型失敗 |
| 模型 | A＝qwen3:32b（研究、裁決），B＝gemma3:27b；兩者都放在實驗室 Ollama（VRAM ≥ 48 GB），不再租 GPUtw |
| 程式分支 | `protocol/monthly-v3-0929.2` |

## 二、開跑前必須先修（2026-11-04 教授式審查，已逐項對照原始碼）

10/22 審查列出的三個程式問題已在 2026-11-04 修好並補測試（全套 499 項，0 失敗、1 項 POSIX-only skip；Ruff 通過），細節見 CHANGELOG。其餘兩項是報告與登記程序，仍待處理。

| 等級 | 問題 | 位置 | 做法 |
|---|---|---|---|
| ✅ 已修 P1 | 同 ticker／protocol 較早案例還在 running 時，另一個 worker 可領取較晚案例，記憶順序會依競速改變（預設 4 個 worker 就會觸發） | `research_service/storage.py` claim | 較早同 ticker 案例 running 時不領較晚案例；不同 ticker 照常平行。測試 `test_second_worker_waits_for_an_earlier_running_case_of_the_same_ticker` |
| ✅ 已修 P1 | RQ3 同一案四組在同一天一起缺報酬時仍通過，缺的那天被當成 0 | `research_service/rq3_inference.py` build_panel | 每組須剛好有 entry 到 maturity 的 61 個交易日，且窗口內其他案例有交易的日子都要有；RQ1 實際 720 組全部符合 |
| ✅ 已修 P2 | Sharpe 不可估時整個推論拋錯，和分析計畫 `report_not_estimable_no_family_reduction` 不符 | `research_service/rq3_inference.py` infer_panel | 標 `not_estimable`，Holm 仍以六項計算，輸出 `overall_superiority_claim_allowed=false` |
| 必改 | 報告寫「RQ1 回答立場交換本身」，但 D 同時改了立場交換、隔離對手、強制引用、驗證重試 | `site/sources/application-meeting-20261020_v11.tex:143,209` | 改成「比較整套立場交換流程與固定立場流程」 |
| 必改 | RQ1 升格稽核列的缺口（登記回執、統計程式不在 protocol hash、研究者確認） | `docs/rq-prep/rq1-promotion-audit.md` | 正式登記 RQ2/RQ3 時把統計程式與 Ollama 版本 digest 一起鎖定 |

這次改了 `storage.py`（source digest 的模組之一），source digest 已變：舊的凍結工作不能用新程式續跑，10/17 的離線封裝要重做（第五節步驟 4）。

研究設計上的建議（不擋開跑，但要在登記前決定；選項與建議整理在 [design-decisions-20261105.md](design-decisions-20261105.md)）：

- **RQ3 只跑 fixed**，只能回答「領域分工 vs 通才」的架構差，回答不了「資訊異質性會不會改變 D−C」。要回答它需要加 D_domain（約兩倍成本），否則報告要改述。
- **檢定力**：180 案、不一致比例 0.2–0.3 時，偵測 5 個百分點差異的檢定力只有約 23–32%，10 個百分點約 69–85%（常態近似粗估）。報告信賴區間，「不顯著」不寫成「等效」，必要時加 TOST。
- 180 案是已見樣本，結果標「探索性回溯」；確認性結論需要知識截止日後的新案例。
- 日期區塊 bootstrap 只有 20 個日期，區塊長 1／2／4 的敏感性一起報告。
- 若要辨識單一機制，另加小型消融：D 去掉立場交換、保留引用與重試。

## 三、架構：這台跑程式，實驗室出 GPU

```
這台電腦（程式、資料庫、研究服務）
   │  SSH 通道：本機 127.0.0.1:11435 → 實驗室 127.0.0.1:11434
   ▼
實驗室電腦（Ollama；qwen3:32b＝A、gemma3:27b＝B，同一個 Ollama，VRAM ≥ 48 GB）
```

- 程式、RQ1 來源快照、結果資料庫都留在這台，不必 clone、不必搬資料。
- 實驗室的 Ollama 維持只聽 `127.0.0.1`，不開放任何埠；流量走 SSH 加密。
- A、B 在同一個 Ollama，兩個 `--model-*-base` 填同一個網址即可（程式允許）。
- 不再需要租 GPUtw。程式只有在網址是 `gputw.ai` 時才會用 GPUtw 密碼，也不會自動開 GPUtw 機器。

若之後 180 案正式批次要跑很多小時，可以改成把程式放到實驗室上跑（`scripts/lab_bundle.py` 打包兩個 SQLite 帶過去，見附錄），避免這台睡眠或網路中斷。pilot 階段用連線即可。

## 四、實驗室電腦一次性設定（SSH 登入後）

1. 下載兩個模型並記下 digest：

   ```bash
   ollama pull qwen3:32b
   ollama pull gemma3:27b
   ollama list
   ```

2. 讓兩個模型能同時常駐、一次只處理一個請求（和 RQ1 相同的順序執行）。Linux（systemd）：

   ```bash
   sudo systemctl edit ollama
   # 在打開的檔案加入：
   [Service]
   Environment="OLLAMA_MAX_LOADED_MODELS=2"
   Environment="OLLAMA_NUM_PARALLEL=1"
   Environment="OLLAMA_KEEP_ALIVE=24h"
   # 存檔後
   sudo systemctl restart ollama
   ```

   Windows 主機：在「系統環境變數」加同樣三個變數，重開 Ollama。不要設 `OLLAMA_HOST=0.0.0.0`。

3. 實驗室主機若有別人同時用 GPU，先確認時段，`nvidia-smi` 看剩餘記憶體；兩模型合計約 37 GB，加上 8192 context 的快取。

## 五、這台電腦每次開跑

**最短路徑：開好 SSH 通道後，一個指令跑完下面的步驟 2–6。**

```powershell
.\scripts\lab-run.ps1 -SshTarget <帳號>@<實驗室主機>   # 腳本自己開通道、斷線自動重開（需要 SSH 金鑰）
.\scripts\lab-run.ps1                                  # 或者：通道已在另一個終端開好
.\scripts\lab-run.ps1 -Stage check                     # 只檢查連線與權重
.\scripts\lab-run.ps1 -Offline                         # 不呼叫模型，只跑環境檢查、封裝與離線 pilot
.\scripts\lab-run.ps1 -Resume work\lab-run-<時間>      # 從停下的地方接著跑
```

每次都寫到新的 `work\lab-run-<時間>\`，附 `summary.json`（每步結束碼、秒數、git commit）；任何一步失敗就停下並指出記錄檔。

- **接續**：`-Resume` 跳過已成功的步驟，失敗的那一步改用新的輸出名稱（`-try2`）重跑，舊輸出保留。程式（git commit 或未提交的修改）和原本那次不同時會拒絕接續，因為改過程式就要重做受影響的檢查。
- **不睡眠**：腳本執行期間電腦不會進入睡眠，結束後恢復。
- **自動驗收**：兩個 pilot 跑完後自動執行 `scripts/check_pilot.py`，逐項檢查操作單第 3 節的項目（各組完整、原始回應可追溯、無引用／schema 失敗或降級、28 份提案提示未截斷、tokens／重試／延遲齊全、權重未變、記憶無未完成早案），並估算 180 案所需時間。模型文字裡沒對應到來源的數字，協議規定只記錄、保留原文，所以這項只報比例（`info`，不判失敗），並附 RQ1 快照的比例（2,940／9,702，30.3%）供比較；真的刪改數字仍判失敗。另有 `debate_engagement`（info）：報告 C 組第 3 輪是否重複自己、有沒有引用並回應對方，附 RQ1 參考值，用來確認辯論真的有交鋒。`all_prompts_within_context` 檢查每一次 Ollama 呼叫的 prompt tokens 都小於上下文減輸出上限（8192 − 2048 = 6144），超過就判失敗（代表被截斷）；雲端模型只報最大值（info）。Gemini 試跑時最大的是裁決者約 5,200–5,500 tokens，qwen 的算法不同，實驗室 pilot 要看這一項。也可以單獨執行：`.\.venv\Scripts\python.exe scripts/check_pilot.py <pilot 輸出資料夾>`。截斷是用 prompt tokens 間接判斷，namespace 失敗只能從無效引用看出，這兩項仍要人工看一眼。它只在這個 PowerShell 視窗清掉 GPUtw 設定、指向通道，不登記、不排正式案例、不續跑舊工作。pilot 跑完代表程式完成，仍要照操作單第 3 節人工驗收輸出。下面是腳本內部的各步驟，出問題時可以逐步手動執行。

1. 開 SSH 通道（另開一個終端，整段實驗期間保持開著）：

   ```powershell
   ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=6 -L 11435:127.0.0.1:11434 <帳號>@<實驗室主機>
   ```

   校外要先連學校 VPN。通道斷掉時，進行中的案例會因模型無法連線而暫停，重開通道後用續跑即可，不要另建工作。

2. 在跑實驗的終端清掉 GPUtw 設定，指向通道（只影響這個終端）：

   ```powershell
   Remove-Item Env:GPUTW_OLLAMA_API_KEY, Env:GPUTW_OLLAMA_PASSWORD, Env:GPUTW_INSTANCE_ID -ErrorAction SilentlyContinue
   $env:OLLAMA_BASE_URL = 'http://127.0.0.1:11435'
   $env:GPUTW_OLLAMA_BASE_URL = 'http://127.0.0.1:11435'
   $env:RESEARCH_MODEL_CONTEXT_LENGTH = '8192'
   $env:RESEARCH_MODEL_TIMEOUT_SECONDS = '900'   # 冷載入 20 GB 需要時間
   ```

   `GPUTW_OLLAMA_API_KEY` 一定要清：模型身分檢查會把它當 Bearer 送給任何端點。`.env.research` 本身不用改。

3. 檢查連線與權重（不建立工作；`--generate` 會在實驗室 GPU 載入兩個模型各回一個字）：

   ```powershell
   .\.venv\Scripts\python.exe scripts/check_lab_ollama.py --base http://127.0.0.1:11435
   .\.venv\Scripts\python.exe scripts/check_lab_ollama.py --base http://127.0.0.1:11435 --generate --output work/lab-ollama-check-1104.json
   ```

   會列出兩個模型的完整 digest、量化格式、Ollama 版本，並比對 qwen3:32b 是否和 RQ1 同一份權重（`030ee887…`）。不同也可以做 RQ2／RQ3（它們自己重跑 AA／C 對照），但 RQ1 的數字不能當基準，登記時要寫明。

4. 環境檢查與重做離線封裝（不呼叫模型；10/17 的封裝因 source digest 變了不能再用）：

   ```powershell
   .\.venv\Scripts\python.exe scripts/check_experiment_environment.py --output work/lab-runtime-1104.json
   .\.venv\Scripts\python.exe scripts/prepare_experiment_launch.py --source-db work/preformal-20261017/rq1-source-backup.sqlite3 --registration-hash b1da80ee8dbc9c372d9eab02455734a140714a233c2d669bb0177fe9ab267cd6 --plan docs/rq-prep/analysis-plan-20261015.json --output work/launch-lab-1104 --model-a-base http://127.0.0.1:11435 --model-b-base http://127.0.0.1:11435
   ```

   `formal_launch_ready=false` 是預期結果。

5. 模型資格：記憶探針 recall／identify 與 canary，A、B 各一次（指令見 [experiment-launch-20261015.md](experiment-launch-20261015.md) 第 2 節，埠一律用 11435，`--data-dir` 用 `work/final-review-20261015/probe-snapshot`）。

6. 三案 pilot：照 [操作單](preformal-runbook-20261017.md) 第 3 節，`--cases` 用 `work/launch-lab-1104/` 底下的檔案；先不加 `--execute` 確認整合，再用新 output 加 `--execute`。只看完整性、引用、tokens、重試、延遲，不看準確率或 Sharpe。

7. pilot 通過、程式凍結，且第二節剩下的必改項處理完後，才進操作單第 4、5 節（報告庫、綁定、事前登記、正式案例）。

## 六、建議的後續實驗順序

1. ~~修第二節三個程式問題並補測試~~（2026-11-04 完成）。
2. 開通道、`check_lab_ollama.py`、重做離線封裝。
3. A、B 的記憶探針、canary、三案 pilot。
4. RQ2 先跑單 seed 905 的 AA/AB/BA/BB，看時間與失敗率，再補 906、907。
5. RQ3 先跑 C 與 C_domain，再跑 C_budget、C_partition；不夠時間時優先保留 C_budget（區分「分工」和「算力」）。
6. 之後再考慮 D 消融與知識截止日後的新案例。

每一步的輸出都用新路徑，保留舊紀錄；完成後回到這頁更新第一節。

## 附錄：把程式搬到實驗室上跑（選用）

git 不帶 `work/` 裡的 RQ1 快照（約 0.74 GB × 2，資料不公開）。需要時：

```powershell
# 這台
.\.venv\Scripts\python.exe scripts/lab_bundle.py pack --out E:\lab-bundle
# 實驗室（clone 並切到 protocol/monthly-v3-0929.2、建好 Python 3.12 venv 後）
python scripts/lab_bundle.py restore --bundle E:\lab-bundle
```

`restore` 驗證 SHA-256 後放回原路徑；金鑰不打包。兩個檔案目前的 SHA-256：

- `work/preformal-20261017/rq1-source-backup.sqlite3`：`f8299f9bca2e9dcad6be9cd31d4f00819c842714e5926f7f5cb56401473bad1b`
- `work/final-review-20261015/probe-snapshot/research.sqlite3`：`3cfa201f7816496f199dffb6e2fdfd74cdc6506d0430d799d32d99dabe544e80`

`research-inputs/`（約 28 GB 新聞原檔）不需要，180 案資料都已在快照裡。
