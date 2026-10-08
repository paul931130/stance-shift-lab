from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
backup = root / 'revisions' / '2026-10-05-review' / 'before'
backup.mkdir(parents=True, exist_ok=True)
for name in ('stance-shift-ssrn.tex', 'application.tex', 'references.bib', 'stance-shift-ssrn.pdf', 'application.pdf'):
    if (root / name).exists() and not (backup / name).exists():
        shutil.copy2(root / name, backup / name)

p = root / 'stance-shift-ssrn.tex'
t = p.read_text(encoding='utf-8')

def replace(old, new):
    global t
    if old not in t:
        raise ValueError('Missing replacement: ' + old[:90])
    t = t.replace(old, new)

def between(start, end, new):
    global t
    a, b = t.index(start), t.index(end, t.index(start))
    t = t[:a] + new + '\n\n' + t[b:]

replace('中華民國一一五年九月', '中華民國一一五年十月')
between('本專題以投資決策輔助為應用情境', r'\vspace{0.6cm}', r'''本研究檢驗在相同資料與相同名目決策呼叫次數下，自我反駁式立場交換辯論（\grp{D}）是否優於固定立場辯論（\grp{C}）。四組決策機制讀取同一案例內鎖定之中立研究報告；\grp{D} 在交換輪改持相反立場、僅讀自身第一輪論述，並引用及反駁原主張。單次判斷（\grp{A}）與獨立投票（\grp{B}）作為補充對照，\grp{B}、\grp{C}、\grp{D} 各使用七次名目決策呼叫。

主要分析使用 qwen3:32b、季度協議 v3-1002.3，涵蓋九檔美股於 2021--2025 年的 180 個季度案例。樣本與分析規則於 2026 年 10 月 2 日鎖定登記，但同批資料曾用於前導研究及規則調整，因此本批屬規則鎖定後對既有樣本之回溯比較。共同主要端點為 60 日方向準確率與年化 Sharpe；僅當兩端點差異皆為正且各自經 Holm 校正後 $p<0.05$，才判定 \grp{D} 優於 \grp{C}。方向準確率為 55.0\% 對 58.3\%（差 $-3.3$ 個百分點，McNemar $p=0.21$），Sharpe 為 0.54 對 0.59（差 $-0.05$，Ledoit--Wolf $p=0.80$），未達上述判準。敏感性分析亦未提供 \grp{D} 較佳之顯著證據；四組之 Sharpe 點估計均低於相同部位配置之買進持有參照（1.01）。

Gemini 3 Flash 的同批案例比較屬探索性分析，其 \grp{D} 準確率亦低於 \grp{C}，但不是獨立樣本的複製。標的匿名化無法完全排除模型辨識與訓練記憶風險，且僅有 16 個主要比較不一致案例、未量測同案重跑變異；故結果不支持 \grp{D} 較佳，亦不證明兩機制等效。月度設計尚未執行。''')
between(r'\noindent Using investment decision support', r'\clearpage' + '\n' + r'\pagenumbering{arabic}', r'''\noindent This study asks whether self-rebuttal role-switching debate (D) outperforms fixed-role debate (C) with the same case-level neutral report and the same nominal decision-call budget. In the switched round, each agent takes the opposite stance, reads only its own first-round argument, and quotes and rebuts its original claim. Independent voting (B) and single decisions (A) provide supplementary comparisons; B, C and D each use seven nominal decision calls.

\noindent The primary analysis uses qwen3:32b under quarterly protocol v3-1002.3 on 180 cases covering nine U.S. stocks in 2021--2025. Cases and analysis rules were registered and locked on 2 October 2026, but prior runs and rule revisions had used the same sample. This is therefore a retrospective comparison under locked rules. D is judged superior only if both differences in 60-day direction accuracy and annualized Sharpe are positive and each Holm-adjusted $p$-value is below 0.05. Accuracy was 55.0\% for D versus 58.3\% for C (difference $-3.3$ percentage points, McNemar $p=0.21$); Sharpe was 0.54 versus 0.59 (difference $-0.05$, Ledoit--Wolf $p=0.80$). The superiority criterion was not met, including in sensitivity analyses. All four arms had lower Sharpe point estimates than the buy-and-hold reference using the same position allocation (1.01).

\noindent An exploratory comparison using Gemini 3 Flash on the same cases also found lower accuracy for D than C, but does not constitute replication on an independent sample. Anonymization cannot rule out asset identification or training-data memory. With only 16 discordant cases and no repeated-run variability assessment, the results neither support superiority nor establish equivalence. The monthly design remains unexecuted.''')
replace('也未在呼叫預算對齊、無前視偏差的回測中檢驗。', '這些結果尚不足以說明，在資訊不增加且名目呼叫次數對齊時，反向論證能否改善高雜訊的未來報酬預測。')
replace('但不預設它有效，而在三個條件下檢驗：', '以此檢驗原有證據的重新檢查是否有增量價值，而在三個條件下比較：')
replace('分析日之後的資料絕不進入輸入，且研究樣本於執行前事前登記。', '資料快照排除分析日之後才公開的資訊，且本批樣本與分析規則於執行前鎖定登記。資料時間邊界不代表模型訓練記憶已被排除，同批樣本的前導使用亦限制登記的確認性效力。')
marker = r'\subsection{研究問題}'
replace(marker, r'''\paragraph{機制動機與可能失效的條件。}
\citet{lord1984opposite} 的人類社會判斷實驗指出，考慮與既有信念相反的可能性可減少特定判斷偏誤。本研究據此提出機制假說：要求代理人引用並反駁自己的論點，可能暴露先前忽略的反證，改善裁決對證據的權衡。此推論從人類判斷延伸至 LLM 金融預測，尚須實證檢驗；論述更完整不必然代表未來報酬預測更準確。\citet{huang2024selfcorrect} 發現，缺乏外部回饋的內生自我修正，在其推理基準上可能無效甚至降低表現；若模型共享相同錯誤、輸入資訊缺乏預測訊號，或市場噪音主導結果，自我反駁也可能只改變敘事而無績效增益。

''' + marker)
between(r'\begin{enumerate}[label=RQ', r'\subsection{研究貢獻}', r'''\begin{enumerate}[label=RQ\arabic*：,leftmargin=4em]
  \item 主要比較：在相同案例資料與相同名目決策呼叫次數下，自我反駁式立場交換辯論（\grp{D}）的 60 日方向準確率與年化 Sharpe 是否高於固定立場辯論（\grp{C}）？\grp{A}、\grp{B} 的比較僅作補充分析。
  \item 跨模型比較（探索性）：同批案例改用 Gemini 3 Flash 後，\grp{D} 相對 \grp{C} 的準確率差之方向是否與 qwen3:32b 一致？此處的一致只指差異方向，不代表效果相等或独立複製。
  \item 跨時間尺度比較（未執行）：月度設計（每月分析、20 個交易日預測）是否得到與季度設計相同之主要比較結論？列為後續研究。
\end{enumerate}

\paragraph{工作假設 H1。} \grp{D} 的方向準確率與年化 Sharpe 皆高於 \grp{C}。本假設形式化主要比較的改善主張；判定沿用既有登記的雙尾檢定、差異須為正及兩端點 Holm 校正規則，不因本次論述修訂改為單尾檢定。未達判準不等於兩組等效。

\noindent \grp{D} 同時包含立場互換、隔離對手與強制引用自身原主張，故比較對象為整套自我反駁流程。尚未以消融區分個別要素，亦未排除驗證重試及隨機生成對決策的影響。RQ2 不合併兩模型之協議統計，RQ3 不列為已回答問題。'''.replace('独立', '獨立'))
between(r'\subsection{研究貢獻}', r'\subsection{研究範圍}', r'''\subsection{貢獻類型}

\begin{enumerate}[label=\arabic*.]
  \item 實證貢獻：在規則鎖定後之 180 案回溯比較中，未取得自我反駁流程優於固定立場辯論的證據；報告負面結果與不確定性，而不宣稱提出新理論。
  \item 比較設計：明確界定自我反駁流程，對齊 \grp{B}、\grp{C}、\grp{D} 的名目決策呼叫次數。立場交換已有前例 \citep{liu2025roleswitch,chowdhury2026proclaim}；本研究的設計價值限於可稽核的機制比較，尚未分離各要素，亦未對齊 token 與重試成本。
  \item 系統貢獻：建立具資料時間邊界、不可變快照、程式與模型版本鎖定及完整呼叫紀錄的回測框架。這些功能提高可審查性，但不構成預測效力或完全排除前視偏差的證明。
\end{enumerate}''')
between(r'\citet{lopezlira2023chatgpt} 顯示', r'\subsection{前視偏差與評估}', r'''\citet{lopezlira2023chatgpt} 在其樣本與設定中發現，LLM 對金融新聞標題的判讀含有與後續報酬相關的訊息；FinBERT \citep{araci2019finbert} 與 FinGPT \citep{liu2023fingpt} 提供金融語言處理方法，FNSPID \citep{dong2024fnspid} 則提供具時間戳記的新聞資料。這些工作說明資訊整理的可能用途，但不能直接推得任何辯論流程有增量價值。

TradingAgents \citep{xiao2024tradingagents} 與 StockAgent \citep{zhang2024stockagent} 將 LLM 分工與交易決策置於回測或模擬環境；其研究對象包含整套代理人系統，與本研究控制案例輸入後比較 \grp{D}、\grp{C} 的估計量不同。\citet{glasserman2023lookahead} 的前視風險分析，以及 \citet{huang2024selfcorrect} 對無外部回饋自我修正的審慎結果，均提醒：流暢推理與模擬績效不能單獨證明可用的未來預測訊號。本研究的缺口因而限定為：在名目呼叫次數對齊、資料時間邊界可稽核的設定下，重新檢查既有證據的自我反駁流程是否改善方向與風險調整績效，而非僅將既有辯論方法搬至金融領域。''')
replace('在模型端以無資料回想測試檢視模型是否記得後續報酬，並在回測中扣除交易成本。', '以舊協議的無資料回想與匿名辨識探針作前導風險診斷（第~\\ref{sec:memorydiagnostic} 節），並在回測中扣除交易成本。探針並非新版主樣本的完整汙染檢驗。')
replace('資料時間邊界、無資料回想測試、證據與數字驗證', '資料時間邊界、前導探針之範圍揭露、證據與數字驗證')
replace('每個案例於分析日建立一份資料快照', '每個案例以分析日為時間邊界建立一份資料快照')
replace('資料來源與時間處理方式如表~\\ref{tab:data}。', '資料來源與時間處理方式如表~\\ref{tab:data}。此九檔為資料可取得性導向的目的性樣本，不是依 2021 年當時成分股或市值排名抽樣。協議紀錄顯示 ASTS 因凍結新聞來源未涵蓋而排除，LLY 因早期新聞缺口於 v3-0923.1 改為 INTC；完整初始候選池與選樣時點未保存於本文所用紀錄。因此不能排除存活及事後選樣偏誤，不推廣為全市場績效。')
replace('這些案例全數保留於主分析，並於事前登記之敏感性分析中排除後重算。', '主分析保留全部案例。文中敏感性子集的 37 案由上述 36 案與另列的 MCD 2023-12-31 案構成；此為來源／覆蓋診斷集合，並非以統一新聞則數門檻定義之「低密度」。該 37 案的逐案名單與來源分類仍須對照新版資料快照核對。')
replace('以固定版本之 FinBERT 逐則評分', '以 ProsusAI/finbert 逐則評分（模型 revision 未在現有紀錄中核對）')
replace('方向準確率以 RET60 之正負判定。', '方向準確率依未扣成本之標的開盤對開盤價格變動判定（買進且上漲、或賣出且下跌為正確）；扣成本之淨報酬另用於績效計算。成本可能使方向正確的交易仍虧損，兩者不可混同。')
replace('四組決策機制與所有重跑皆讀取同一份快照。', '同一模型同一案例內的四組決策機制讀取同一份快照與鎖定報告。行情使用 yfinance 的 auto\_adjust=True；調整係數反映下載時可得之拆股與股利處理，並非各分析日保存的調整版本，仍有事後修訂風險。')
replace('差異僅在決策方式。', '決策機制於報告鎖定後分流；下注限制與記憶權限另依組別設定。')
replace('需另設消融組。', '需另設消融組。此外，\\grp{D} 有引用自身原文之額外驗證，驗證失敗可觸發重試；\\grp{C} 沒有同一要求。因此七次是名目決策呼叫數，不能解讀為兩組實際呼叫、驗證負擔或運算成本完全相等。')
replace('新舊規則產生的結果不可合併。', '舊版結果保留於稽核紀錄，未納入本批表格及主要推論；新舊規則產生的結果不可合併。')
replace('研究樣本於執行前以批次方式事前登記，僅登記後建立之實驗計入正式結果。分析日另依年份分為訓練（2021--2023）、驗證（2024）與測試（2025）三段。', '本批樣本於執行前以批次方式登記，僅登記後建立且符合凍結規則之實驗納入主要結果。本研究未訓練或調適模型，2021--2025 年全數納入回溯比較；不將年份標籤視為已完成的訓練／驗證／測試切分。')
replace('固定隨機種子、上下文 8192 tokens', '基礎隨機種子 905、上下文 8192 tokens')
replace('而非全新之樣本外測試。', '而非全新之樣本外測試。實際每次呼叫的種子由基礎值加上呼叫鍵雜湊之前八位十六進位值，再對 $2{,}147{,}483{,}647$ 取模，記錄於呼叫稽核。固定種子不保證跨硬體或服務端完全重現。')
replace('Holm 校正 \\citep{holm1979} 只在這兩者間進行，', '兩項改善須同時成立，屬交集式優越性判準；為沿用登記規則，保留雙尾檢定，且 Holm 校正 \\citep{holm1979} 只在這兩者間進行。Holm 是額外保守的門檻，不宣稱為此聯合主張所必需；')
replace('並排除 37 個低新聞密度案例重算主要比較。', '並排除前述 37 個新聞來源／覆蓋診斷案例重算主要比較。')
insert = r'''\paragraph{日報酬序列與年化。} 對第 $i$ 案，進場日計開盤至收盤，其後逐日計收盤至收盤，出場日計前收盤至出場開盤；以初始資金為基準的做多／放空部位權益扣除進出場價差，得到日報酬 $r_{i,g,t}=E_{i,g,t}/E_{i,g,t-1}-1$。持有與非該案交易期間以零報酬計。各案日期對齊後，固定權重日序列為
\[
 r_{g,t}=\frac{1}{180}\sum_{i=1}^{180}r_{i,g,t},\qquad
 SR_g=\sqrt{252}\,\frac{\bar r_g}{s(r_g)},\quad
 R_g=\prod_{t=1}^{T}(1+r_{g,t})-1.
\]
日期集合為全部案例持有期間內有價格紀錄之交易日聯集；持有期可重疊。標準差採樣本標準差（$T-1$ 分母），無風險基準明設為零，非扣除同期市場無風險利率。$R_g$ 為此日序列之累積報酬，不是平均 60 日案例報酬。最大回撤由 $V_{g,t}=\prod_{u\leq t}(1+r_{g,u})$ 相對歷史最高值計算。此固定案例權重序列供組間比較，並非滿倉九檔股的實際交易組合，其低曝險會影響報酬與回撤的經濟解讀。

Ledoit--Wolf 採學生化循環區塊自助法，區塊長度 20 個交易日、重抽樣 1,999 次、種子 905，原樣本標準誤採 Bartlett HAC（落後 19 日）；Sharpe 差以同日期的日序列配對。方向差之日期群聚區間採 1、2、4 個分析日之循環區塊、1,999 次重抽樣，基礎種子 905，為依賴性敏感性檢查，非等效性檢定。

持有機會成本為持有案例之 $\max(0,|100(P_{exit}/P_{entry}-1)|-b_i)$ 平均值，$b_i$ 為該案中性帶（百分點）。它是超出中性帶之絕對價格變動，未扣成本且不知道事前方向，不是可實現的放棄獲利。

'''
replace('RQ1 以 60 日為事前指定之主要期間', insert + 'RQ1 以 60 日為事前指定之主要期間')
replace('實作過程中遇到之主要問題與對策如下：', '主要處理及稽核方式如下：')
between('守門員之規則為：', '\n\n%% =====================================================================\n\\section{實驗結果}', '守門員以波動度、基準率歷史、引用與四面向覆蓋檢查風險，處理結果保存於稽核紀錄。主要分析使用守門員前候選決策；本批守門員僅改變一個案例，故不將此模組視為績效改善的證據。短期紀錄與長期記憶亦未做消融，不能歸因其個別貢獻。')
replace('正式 RQ1', '主要 RQ1')
replace('持有機會成本 & 總報酬', '持有機會成本 & 累積報酬')
replace('組合將每個', '持有機會成本之單位為百分點；累積報酬與回撤依第~\\ref{sec:methods} 節日序列公式計算。組合將每個')
replace('低新聞密度案例', '新聞來源／覆蓋診斷案例')
replace('低新聞案例', '新聞診斷案例')
replace('\\grp{D} 之賣出多於 \\grp{C}，', '\\grp{D} 之賣出多於 \\grp{C}（43 對 35 案，未檢定），')
replace('案例示範：自我反駁如何改變裁決', '兩個分歧案例的描述')
replace('兩案之研究報告、證據與模型完全相同，差別僅在辯論流程。', '每一案例內兩組的研究報告、證據與模型相同。兩案在結果已知後選取，只供描述，不估計自我反駁的因果機制。')
replace('此案中，交換輪迫使原看多之代理人正視自己第一輪輕描淡寫之基本面衰退，裁決者隨之轉為賣出；', '此案的交換輪文字強調基本面衰退，\\grp{D} 裁決為賣出、\\grp{C} 為買進；')
replace('同樣的機制也可能帶來反效果。', '另一個分歧案例的 \\grp{D} 判斷錯誤。')
replace('\\grp{D} 有 12 案判斷賣出，正確 5 案、錯誤 11 案。', '\\grp{D} 有 12 案判斷賣出；就全部 16 個分歧案例而言，\\grp{D} 正確 5 案、\\grp{C} 正確 11 案。')
replace('立場交換改變了辯論內容與部分決策，但未帶來更準確的結果。', '兩組的部分文字與決策不同，但本資料未支持 \\grp{D} 較佳；這些觀察無法分離自我反駁、驗證重試與生成噪音的影響。')
between(r'\paragraph{對 RQ1 之回答。}', r'\subsection{探索性分析', r'''\paragraph{對 RQ1 與 H1 之回答。} 兩個主要端點之點估計皆偏向 \grp{C}，且未達登記之優越性判準，因此本資料不支持 H1；不解讀為兩機制無差異或等效。180 案中只有 16 個不一致案例提供 McNemar 的差異資訊。若條件化於 16 個不一致案例且暫假設配對彼此獨立，雙尾精確 $\alpha=0.05$ 檢定至少需 13 對 3 的不一致分布才顯著（$p=0.0213$），相當於 180 案中 $5.6$ 個百分點的差異。此僅為離散拒絕門檻診斷，不是具 80\% 檢定力的 MDE；日期依賴與雙端點門檻使規劃更複雜。本研究未完成事前檢定力分析，亦未用不同種子重跑 \grp{C}，無法將觀察到的分歧全歸因於機制。主要區間 $[-7.2,+0.6]$ 個百分點仍須保守解讀。

四組之 Sharpe 點估計低於相同配置之買進持有參照，此為描述性比較，未對基準進行優越性檢定。\grp{C}、\grp{D} 與可持有的 \grp{A}、\grp{B} 同時具有下注限制、記憶權限等差異，因此補充比較不能單獨歸因於辯論。''')
replace('探索性分析：跨模型複製與基準比較', '探索性分析：跨模型與基準比較')
replace('\\paragraph{跨模型複製。}', '\\paragraph{跨模型比較。}')
replace('以 Gemini 3 Flash 依相同流程、相同 180 案與相同匿名化設定重跑四組', '原分析以 Gemini 3 Flash 依相同案例集合、流程與匿名化設定重跑四組')
replace('兩模型之決策高度相似，', '此為相同標的、日期與來源資訊上的模型替換比較，不是獨立資料複製。新版 Gemini 完整 API model ID、實際溫度、存取日期、種子套用狀態與逐案研究報告雜湊，未在現有本機新版匯出中核對；因此不能宣稱兩模型逐位元讀取相同研究報告，也不能把模型替換解讀為純粹的能力改變。兩模型之決策高度相似，')
replace('一律看多（事後參照） & \\multicolumn{2}{c}{62.2\\%}', '一律看多（全 180 案；僅與 C／D 同基底） & \\multicolumn{2}{c}{62.2\\%}')
replace('\\end{tabular}\n\\end{table}\n\n\\paragraph{與一律看多之比較。}', '\\end{tabular}\n\\par\\smallskip\n\\raggedright\\footnotesize 兩模型均報告 180 案。qwen 的 A、B 有出手案例為 141、143 案（覆蓋率 78.3\\%、79.4\\%），C、D 為 180 案。Gemini 的 A、B 出手數及覆蓋率尚未由逐案匯出核對；C、D 依強制下注規則為 180 案。A、B 的條件準確率不能直接與全樣本 62.2\\% 比較；其出手子集之一律看多基準尚待逐案資料重算，本文不作此比較。\n\\end{table}\n\n\\paragraph{與一律看多之比較。}')
between(r'\paragraph{與一律看多之比較。}', r'\paragraph{被否證之解釋。}', r'''\paragraph{與一律看多之比較。} 180 案中 112 案於 60 日內上漲（62.2\%）、68 案下跌（37.8\%）。只有覆蓋全部案例的 \grp{C}、\grp{D} 可直接與此事後方向參照比較；兩模型的這兩組準確率點估計均較低。對 qwen，表~\ref{tab:confusion} 由既有決策總數與正確數重建完整分布，不作為新的逐案驗證。賣出精確率分別為 40.0\%（14/35）與 34.9\%（15/43），相對全樣本下跌率 37.8\% 一高一低；下跌召回率為 20.6\% 與 22.1\%。因此可描述其下跌召回偏低，不能概括為完全沒有辨識力。

\begin{table}[H]
\centering\small
\caption{qwen3:32b 的方向混淆分布（60 日，候選決策）}
\label{tab:confusion}
\begin{tabular}{@{}llrrr@{}}
\toprule
組別 & 預測方向 & 實際上漲 & 實際下跌 & 合計 \\
\midrule
\grp{C} & 買進 & 91 & 54 & 145 \\
         & 賣出 & 21 & 14 & 35 \\
\grp{D} & 買進 & 84 & 53 & 137 \\
         & 賣出 & 28 & 15 & 43 \\
\bottomrule
\end{tabular}
\par\smallskip
\raggedright\footnotesize 每組總數 180；正確數 C=105、D=99。由本文既有彙總數代數重建，尚未以新版逐案匯出另行稽核。A／B 的持有分布與 Gemini 的完整分布不由四捨五入準確率反推。
\end{table}''')
replace('被否證之解釋。', '本資料未支持的解釋。')
replace('此推測不成立。', '各模型僅相差一案，且季別為事後分類；此資料未能支持上述推測，但不能宣稱已否證。')
between(r'\paragraph{後續假說。}', r'\subsection{研究限制}', r'''\paragraph{對 RQ2 之回答。} 兩模型之 \grp{D}$-$\grp{C} 準確率差均為負，符合 RQ2 對「差異方向一致」的描述性定義；未檢定模型與機制交互作用、等效性或跨模型 Sharpe 的聯合判準。因使用同批樣本、分析屬探索性且模型紀錄仍待補齊，不能宣稱已確認跨模型穩健性。

\paragraph{後續假說。} 本研究在兩個模型的既有準確率結果中均未觀察到 \grp{D} 改善。輸入資訊之預測力不足是可能解釋之一，但市場噪音與效率、提示設計、模型限制、樣本數及生成變異也可能造成此結果，本文未以實驗區分。後續可在新期間或新標的，先登記資訊集擴充與消融方案，再檢驗跨標的訊號是否有增量價值 \citep{nosek2018prereg}；不可在同一批產生假說的資料上將探索結果改稱確認性證據。

\subsection{前導記憶與匿名辨識診斷}
\label{sec:memorydiagnostic}

專案已保存 2026 年 9 月 28 日 qwen3:32b 的前導探針，並非未執行。無資料回想測試使用 63 題、60 日期間、溫度 0、種子 905；2022、2023、2024 年各 9 題的方向正確率為 33.3\%、33.3\%、55.6\%，2025 年 36 題為 72.2\%，皆未高於各組多數方向基準（66.7\%、66.7\%、55.6\%、72.2\%）。這只能說明此問法未觀察到超越基準的回想表現，不證明沒有記憶。

另以 2023-06-30、2024-06-30 各九檔的匿名證據前 6,000 字元詢問公司身分，qwen 辨識 6/18（33.3\%）；產品名稱與財報規模仍提供線索。此為開放式公司回答，不是九選一測試，故不直接採 1/9 作統計虛無基準。兩項探針使用舊協議 39f71a9c，未完整保留可比對的模型權重與新版研究報告身分；不能當作 v3-1002.3 全部 180 案之辨識率。專案另有 Gemini 2.5 Flash 等舊模型探針，也不能替代本批 Gemini 3 Flash 的汙染檢驗。新版兩模型的完整匿名報告探針仍待執行。''')
between('第一，研究範圍為九檔美國大型股', '%% =====================================================================\n\\section{結論與未來研究}', r'''第一，九檔為資料可取得性導向的目的性样本，未納入退市公司，無法排除存活與事後選樣偏誤，亦不推廣至其他市場或模型。第二，\grp{D} 包含立場互換、隔離對手、強制引用與額外驗證負擔，尚未消融；七次名目呼叫不代表重試與 token 成本一致。第三，匿名化仍保留數值、日期與產品線索；前導探針為舊協議小樣本，未量測新版 180 案的匿名辨識率，不能排除訓練記憶。第四，同批資料已用於前導研究與規則調整，本批是規則鎖定後之回溯比較，登記不能恢復未見樣本的確認性。

第五，\grp{C}、\grp{D} 必須下注且可用已到期記憶，\grp{A}、\grp{B} 可持有且無記憶，補充比較混合多項差異；A／B 出手子集基準與 Gemini 覆蓋率仍待新版逐案資料補齊。第六，主要比较只有 16 個不一致案例，180 案共享 20 個日期；日期群聚區間僅是敏感性檢查，未完成事前檢定力或等效性分析。第七，各案僅執行一次，尚無不同種子的 C 對 C$'$ 重跑，无法分離生成噪音與流程差異。第八，新聞來源與密度隨年份、個股改變，排除 37 案是來源／覆蓋診斷；FinBERT revision、行情下載時調整版本，以及 Gemini 完整執行設定仍限制精確重現。第九，跨模型比較共用同批案例，研究報告是否完全一致尚待雜湊核對；月度設計未執行。

'''.replace('样本', '樣本').replace('比较', '比較').replace('无法', '無法'))
between('主要 RQ1（qwen3:32b', r'\vspace{0.8cm}', r'''主要 RQ1（qwen3:32b，v3-1002.3，180 案）是規則鎖定後的回溯比較。\grp{D} 對 \grp{C} 的方向準確率為 55.0\% 對 58.3\%（$p=0.21$）、年化 Sharpe 為 0.54 對 0.59（$p=0.80$），未達兩端點差異皆為正且 Holm 校正後顯著的優越性判準，因此本資料不支持 H1。此結論不等於兩組無差異或等效；日期群聚方向差區間為 $[-7.2,+0.6]$ 個百分點，且同案重跑變異尚未量測。

\grp{D} 的賣出案例數較多（43 對 35，未檢定），文字新穎率的參照輪不同，僅能作描述，不能推出自我反駁使代理人取得更多新資訊。四組的 Sharpe 點估計均低於相同配置的買進持有參照，未觀察到實務績效增益。目的性選樣、回溯性質、匿名化不完全與少量不一致案例限制推廣。

RQ2 的同批跨模型準確率比較已報告 Gemini 3 Flash 的探索性結果，兩模型之 \grp{D}$-$\grp{C} 差異方向均為負，但不構成獨立複製或跨模型等效性證據。RQ3 的月度擴充（v3-1002.4，540 案）尚未執行。後續應先在新版報告量測匿名辨識與同案重跑變異、補齊逐案基準與模型紀錄，再於新期間或新標的事前登記資訊集擴充、消融及月度比較。輸入資訊不足只是待檢驗假說之一。''')
p.write_text(t, encoding='utf-8')

b = root / 'references.bib'
bib = b.read_text(encoding='utf-8')
bib += r'''
@article{lord1984opposite,
  author = {Lord, Charles G. and Lepper, Mark R. and Preston, Elizabeth},
  title = {Considering the Opposite: A Corrective Strategy for Social Judgment},
  journal = {Journal of Personality and Social Psychology},
  volume = {47}, number = {6}, pages = {1231--1243}, year = {1984},
  doi = {10.1037/0022-3514.47.6.1231}
}

@inproceedings{huang2024selfcorrect,
  author = {Huang, Jie and Chen, Xinyun and Mishra, Swaroop and Zheng, Huaixiu Steven and Yu, Adams Wei and Song, Xinying and Zhou, Denny},
  title = {Large Language Models Cannot Self-Correct Reasoning Yet},
  booktitle = {International Conference on Learning Representations},
  year = {2024}, url = {https://arxiv.org/abs/2310.01798}
}
'''
b.write_text(bib, encoding='utf-8')
print('Revised main report; backups preserved at', backup)
