# Power planning

這是設計規劃，不是正式結果。程式使用 paired McNemar 的 Monte Carlo 敏感度分析，讓 directional coverage、cluster size 與 ICC 明確進入假設。

```powershell
python scripts\power_plan.py --total-cases 180 --cluster-size 9 --replicates 2000 --seed 905
```

輸出中的 `nominal_directional_cases` 是把 coverage 套到 180 cases 後的數字，`effective_directional_cases` 再用 design effect 調整。`accuracy_delta` 是 treatment accuracy 減 control accuracy；`discordant_rate` 是兩方法產生不一致方向的比例。這些都要在正式執行前固定，不能看完結果再挑選。

目前預設 grid 只是起始範圍：delta 5%、10%、15%；directional coverage 50%、70%、90%；ICC 0%、5%、10%；cluster size 9。180 個案例同時有股票群聚、日期重疊與可能的時間相依，因此單一獨立樣本 power 不能直接套用。

報告時至少呈現整個敏感度範圍、有效方向性樣本數與最小可偵測差異。不要把 `MIN_CASES_FOR_INFERENCE = 30` 說成 power analysis；它只是正式 aggregate inference 的最低資料門檻。

