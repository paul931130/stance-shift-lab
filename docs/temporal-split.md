# 時間切分與驗收

本研究台以研究分析日決定資料角色，不以資料下載時間決定：

| 角色 | 分析日 | 用途 |
| --- | --- | --- |
| Training | 2021–2023 季末 | 建構提示詞、規則與候選模型 |
| Validation | 2024 季末 | 調整超參數與門檻 |
| Test | 2025 季末 | 凍結設定後的獨立最終評估 |

這個系統是固定提示詞的多代理人推論引擎，並不是用梯度訓練分類器。因此 Training 在這裡代表「可用來設計與選擇設定的案例」，不會在執行時偷偷更新模型權重；Test 案例也不應被拿來調整 prompt、門檻、模型或 seed。

查看目前完整度：

```powershell
.\research.ps1 splits
```

建立只供審查的批次計畫（不會自動啟動實驗）：

```powershell
.\scripts\create-temporal-split-plan.ps1
```

產出的 `work\temporal-split-plan.json` 會保留完整資料集 ID、股票、研究日、切分角色、排除原因與 Test 凍結標記。確認 Training／Validation 的設定後，再從網頁批次研究匯入；Test 結果最後獨立報告。

服務 API `GET /api/readiness/splits` 與網頁、終端使用同一份 readiness 計算。缺少證據、FinBERT 或後續行情會分開計數，不會把「有行情但研究證據不完整」誤報成完全可用。
