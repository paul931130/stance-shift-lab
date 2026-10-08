# Part B 新版目錄

依系上七章格式。以下列到三級標題；註記是編輯狀態，不代表已實作或已執行。摘要與參考文獻是特殊格式，三級條目亦提供寫作內容定位。

## 摘要【部分修改】

### 中文摘要【部分修改】
- 研究目的與方法【部分修改】
- 結果與結論【待實驗】

### 英文摘要【部分修改】
- Purpose and Methods【部分修改】
- Results and Conclusions【待實驗】

## 一 引言 Introduction【部分修改】

### 研究背景【大量保留】
- LLM in Finance【大量保留】
- Multi-Agent Debate 與 Role-Switching【部分修改】

### 研究動機【部分修改】
- 自我反駁機制的增量價值【大量保留】
- 模型同質性與推理差異【新增】
- Generalist資訊集中與領域分工【新增】

### 研究目的【部分修改】
- 立場交換機制【大量保留】
- 模型異質性【新增】
- 領域專業化【新增】

### Research Questions【部分修改】
- RQ1 原始機制【大量保留】
- RQ2 Model Heterogeneity【新增】
- RQ3 Domain-Specialized Debate【新增】

### 研究範圍【大量保留】
- 樣本與資料時間邊界【大量保留】
- 預測期間與決策層【部分修改】

## 二 文獻探討 Literature Review【部分修改】

### Multi-Agent Debate【大量保留】
- 辯論與自我一致性的公平對照【大量保留】

### Role-Switching / Self-Rebuttal【大量保留】
- 機制假說與失效條件【部分修改】

### Model Heterogeneity【新增】
- 異質性、能力組成與模型偏向【新增】

### Financial LLM and Investment Agents【大量保留】
- 金融語言與代理人工作流【大量保留】

### Domain Specialization / Task Decomposition【新增】
- 摘要分工與決策分工的區分【新增】

### Look-Ahead Bias and Financial Evaluation【大量保留】
- 資料時間邊界與模型訓練記憶【大量保留】

### Literature Synthesis / Research Gap【部分修改】
- 機制、模型與任務的連續問題【部分修改】

## 三 研究方法 Methodology【部分修改】

### 研究架構【部分修改】
- 共同資料層與三個實驗分支【部分修改】
- Judge 與 Gatekeeper【大量保留】

### 資料收集【大量保留】
- 四類資料與時間控制【大量保留】
- 資料品質與版本風險【大量保留】

### 實驗設計【部分修改】
- Common Experimental Setup【部分修改】
- Fixed-role Debate C【大量保留】
- Role-Switching Debate D【大量保留】
- RQ1 Design【大量保留】
- RQ2 Heterogeneous Model Design【新增】
- RQ3 Domain-Specialized Design【新增】
- Evaluation【大量保留】
- Statistical Analysis【部分修改】

### 工具及設備【大量保留】
- 既有工具鏈與GPU【大量保留】

## 四 系統設計與實作【部分修改】

### 系統架構【部分修改】
- 既有流程與新增模組狀態【部分修改】

### 功能模組【部分修改】
- Coordinator與Data Snapshot【大量保留】
- Research Agents【大量保留】
- Short-term Memory / Long-term Memory【大量保留】
- Judge / Gatekeeper / Backtest【大量保留】
- Model Router【新增】
- Domain Debate Module【新增】
- Final Aggregator【新增】

### 介面設計【大量保留】
- 既有研究台與新版分支規劃【部分修改】

### 實作流程與驗證【大量保留】
- 既有開發流程【大量保留】
- Audit Trail與版本核對【大量保留】

### Implementation Challenges【新增】
- 異質格式與context handling【新增】
- 資源公平與domain output normalization【新增】
- 模型能力混淆【新增】

## 五 結果與討論 Results and Discussion【部分修改】

### RQ1 Results【待實驗】
- C vs D 主要端點與敏感性【待實驗】

### RQ2 Results【待實驗】
- Homogeneous / Heterogeneous C/D效果【待實驗】
- Counterbalancing與模型偏向診斷【待實驗】

### RQ3 Results【待實驗】
- Generalist / Domain-specialized績效與成本【待實驗】
- Domain stance與衝突整合【待實驗】

### 舊協議 Prior Results【大量保留】
- 舊qwen績效與檢定【大量保留】
- 正反分歧案例與未支持解釋【大量保留】

### Exploratory Cross-model Analysis與前導診斷【大量保留】
- Gemini homogeneous比較【大量保留】
- 舊協議記憶與匿名辨識探針【大量保留】

### Integrated Discussion【待實驗】
- 機制、模型與任務之價值及替代解釋【待實驗】

### 研究限制【大量保留】
- 既有誠信與可重現性限制【大量保留】
- 能力差距、成本與跨領域整合限制【新增】

## 六 結論與建議【部分修改】

### 研究結論【待實驗】
- RQ1–RQ3逐題回答【待實驗】

### 應用與價值【部分修改】
- 可追溯決策輔助【大量保留】
- Multi-Agent System Design【新增】

### 未來展望【部分修改】
- Temporal-scale robustness【部分修改】
- 模型、路由、消融及独立樣本外【部分修改】

## 七 參考文獻【大量保留】

### 作者年份格式【大量保留】
- 原文獻與需補範圍【部分修改】

## 附列 新版正式實驗開始前必須鎖定事項【新增】

### RQ2【新增】
- 模型、指派與生成設定【新增】

### RQ3【新增】
- 領域規則、schema與公平預算【新增】

### 共同【新增】
- 資料、outcome、統計及protocol hash【新增】
