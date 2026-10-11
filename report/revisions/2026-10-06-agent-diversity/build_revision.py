from pathlib import Path
import re, hashlib, json, shutil

root=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
app=(root/'application.tex').read_text(encoding='utf-8')
ssrn=(root/'stance-shift-ssrn.tex').read_text(encoding='utf-8')

def subsection(src,title):
    start=src.index('\\subsection{'+title+'}')
    m=re.search(r'\\(?:subsection|section)\{',src[start+len('\\subsection{'+title+'}'):])
    end=start+len('\\subsection{'+title+'}')+m.start() if m else len(src)
    return src[start:end].split('%% =====================================================================')[0].strip()+'\n'

def body(src,title):
    return subsection(src,title).split('\n',1)[1].strip()

def sec(title): return '\n\\section{'+title+'}\n'
def sub(title): return '\n\\subsection{'+title+'}\n'
def third(title): return '\n\\subsubsection{'+title+'}\n'

rq1='在相同案例資料與相同名目決策呼叫次數下，自我反駁式立場交換辯論（D）的 60 日方向準確率與年化 Sharpe 是否高於固定立場辯論（C）？'
rq2='當看多與看空代理人由不同基礎模型擔任時，自我反駁式立場交換辯論（D）相對固定立場辯論（C）的投資決策效果是否改變？'
rq3='相較於將四類金融資訊整合後交由共同多空代理人辯論，若改由技術面、基本面、情緒面與總經面代理人分別在各自資訊領域進行多空辯論，再由上層整合機制形成最終投資決策，是否能改善方向準確率與風險調整後績效？'

outline=[
('摘要【部分修改】',[('中文摘要【部分修改】',['研究目的與方法【部分修改】','結果與結論【待實驗】']),('英文摘要【部分修改】',['Purpose and Methods【部分修改】','Results and Conclusions【待實驗】'])]),
('一 引言 Introduction【部分修改】',[('研究背景【大量保留】',['LLM in Finance【大量保留】','Multi-Agent Debate 與 Role-Switching【部分修改】']),('研究動機【部分修改】',['自我反駁機制的增量價值【大量保留】','模型同質性與推理差異【新增】','Generalist資訊集中與領域分工【新增】']),('研究目的【部分修改】',['立場交換機制【大量保留】','模型異質性【新增】','領域專業化【新增】']),('Research Questions【部分修改】',['RQ1 原始機制【大量保留】','RQ2 Model Heterogeneity【新增】','RQ3 Domain-Specialized Debate【新增】']),('研究範圍【大量保留】',['樣本與資料時間邊界【大量保留】','預測期間與決策層【部分修改】'])]),
('二 文獻探討 Literature Review【部分修改】',[(x,[y]) for x,y in [('Multi-Agent Debate【大量保留】','辯論與自我一致性的公平對照【大量保留】'),('Role-Switching / Self-Rebuttal【大量保留】','機制假說與失效條件【部分修改】'),('Model Heterogeneity【新增】','異質性、能力組成與模型偏向【新增】'),('Financial LLM and Investment Agents【大量保留】','金融語言與代理人工作流【大量保留】'),('Domain Specialization / Task Decomposition【新增】','摘要分工與決策分工的區分【新增】'),('Look-Ahead Bias and Financial Evaluation【大量保留】','資料時間邊界與模型訓練記憶【大量保留】'),('Literature Synthesis / Research Gap【部分修改】','機制、模型與任務的連續問題【部分修改】')]]),
('三 研究方法 Methodology【部分修改】',[('研究架構【部分修改】',['共同資料層與三個實驗分支【部分修改】','Judge 與 Gatekeeper【大量保留】']),('資料收集【大量保留】',['四類資料與時間控制【大量保留】','資料品質與版本風險【大量保留】']),('實驗設計【部分修改】',['Common Experimental Setup【部分修改】','Fixed-role Debate C【大量保留】','Role-Switching Debate D【大量保留】','RQ1 Design【大量保留】','RQ2 Heterogeneous Model Design【新增】','RQ3 Domain-Specialized Design【新增】','Evaluation【大量保留】','Statistical Analysis【部分修改】']),('工具及設備【大量保留】',['既有工具鏈與GPU【大量保留】'])]),
('四 系統設計與實作【部分修改】',[('系統架構【部分修改】',['既有流程與新增模組狀態【部分修改】']),('功能模組【部分修改】',['Coordinator與Data Snapshot【大量保留】','Research Agents【大量保留】','Short-term Memory / Long-term Memory【大量保留】','Judge / Gatekeeper / Backtest【大量保留】','Model Router【新增】','Domain Debate Module【新增】','Final Aggregator【新增】']),('介面設計【大量保留】',['既有研究台與新版分支規劃【部分修改】']),('實作流程與驗證【大量保留】',['既有開發流程【大量保留】','Audit Trail與版本核對【大量保留】']),('Implementation Challenges【新增】',['異質格式與context handling【新增】','資源公平與domain output normalization【新增】','模型能力混淆【新增】'])]),
('五 結果與討論 Results and Discussion【部分修改】',[('RQ1 Results【待實驗】',['C vs D 主要端點與敏感性【待實驗】']),('RQ2 Results【待實驗】',['Homogeneous / Heterogeneous C/D效果【待實驗】','Counterbalancing與模型偏向診斷【待實驗】']),('RQ3 Results【待實驗】',['Generalist / Domain-specialized績效與成本【待實驗】','Domain stance與衝突整合【待實驗】']),('舊協議 Prior Results【大量保留】',['舊qwen績效與檢定【大量保留】','正反分歧案例與未支持解釋【大量保留】']),('Exploratory Cross-model Analysis與前導診斷【大量保留】',['Gemini homogeneous比較【大量保留】','舊協議記憶與匿名辨識探針【大量保留】']),('Integrated Discussion【待實驗】',['機制、模型與任務之價值及替代解釋【待實驗】']),('研究限制【大量保留】',['既有誠信與可重現性限制【大量保留】','能力差距、成本與跨領域整合限制【新增】'])]),
('六 結論與建議【部分修改】',[('研究結論【待實驗】',['RQ1–RQ3逐題回答【待實驗】']),('應用與價值【部分修改】',['可追溯決策輔助【大量保留】','Multi-Agent System Design【新增】']),('未來展望【部分修改】',['Temporal-scale robustness【部分修改】','模型、路由、消融及独立樣本外【部分修改】'])]),
('七 參考文獻【大量保留】',[('作者年份格式【大量保留】',['原文獻與需補範圍【部分修改】'])]),
('附列 新版正式實驗開始前必須鎖定事項【新增】',[('RQ2【新增】',['模型、指派與生成設定【新增】']),('RQ3【新增】',['領域規則、schema與公平預算【新增】']),('共同【新增】',['資料、outcome、統計及protocol hash【新增】'])])]
toc=['# Part B 新版目錄','\n依系上七章格式。以下列到三級標題；註記是編輯狀態，不代表已實作或已執行。摘要與參考文獻是特殊格式，三級條目亦提供寫作內容定位。']
for title,subs in outline:
    toc.append('\n## '+title)
    for st,ts in subs:
        toc.append('\n### '+st)
        toc += ['- '+t for t in ts]
(out/'Part-B-新版目錄.md').write_text('\n'.join(toc)+'\n',encoding='utf-8')

# Read originals before producing D. Snapshot exact inputs for a recoverable revision.
baseline=out/'source-baseline'
baseline.mkdir(exist_ok=True)
for fn in ['application.tex','stance-shift-ssrn.tex','references.bib']:
    shutil.copy2(root/fn,baseline/fn)

preamble=app[:app.index('本專題建立一套')]
preamble=preamble.replace('多代理人立場交換辯論機制\\\\ 應用於投資決策\\par','多代理人立場交換辯論機制\\\\ 應用於投資決策\\par')
preamble=preamble.replace('\\vspace{0.8cm}\n{\\fontsize{14}{21}\\selectfont Multi-Agent', '\\vspace{0.3cm}\n{\\fontsize{12}{18}\\selectfont 模型異質性與領域專業化之延伸\\par}\n\\vspace{0.5cm}\n{\\fontsize{14}{21}\\selectfont Multi-Agent')
preamble=preamble.replace('%% 編譯：pdfLaTeX + BibTeX；需同時上傳 references.bib 與 figures/', '%% 2026-10-06 新版研究設計修訂稿；bibliography 已嵌入。原介面圖片存在時沿用，否則呈現文字說明。')
text=preamble+r'''
本專題延續多代理人立場交換辯論機制，檢驗在相同案例資料與相同名目決策呼叫次數下，自我反駁流程能否改善投資決策，並檢查模型同質性及資訊處理集中兩項可能限制。系統保留僅含分析日前可得資訊之資料快照、四類研究代理人、證據追蹤、裁決、守門及回測。RQ1 比較固定立場 C 與立場交換 D；D 第二輪須引用並反駁自己第一輪的論點，第三輪回原立場。RQ2 操弄多空代理人的模型組成，平衡模型與原始立場指派，固定 Judge 與 Gatekeeper。RQ3 規劃四領域各自辯論後由 Final Aggregator 整合；辯論規則、呼叫預算與公平比較方式仍待鎖定。研究維持九檔美股、2021--2025 年季度 180 案與 60 交易日，主要指標為方向準確率及年化 Sharpe。

研究結果：【待實驗結果】。三組正式新版實驗尚未完成，舊協議結果另列 prior result；結論將於正式實驗完成後報告。同批樣本的前導使用、模型訓練記憶、選樣與計算資源差異仍限制推論，不預設異質模型或領域分工有效。

\vspace{0.6cm}
\noindent 關鍵詞：大型語言模型、多代理人辯論、立場交換、模型異質性、領域專業化、投資決策
\clearpage
\begin{center}{\fontsize{16}{24}\selectfont Abstract\par}\end{center}
\noindent This project retains self-rebuttal role-switching debate as its core investment decision mechanism. Auditable point-in-time snapshots, four research agents, evidence tracing, judging, gatekeeping and backtesting are retained. RQ1 compares fixed-role debate C and role-switching debate D with the same case data and nominal decision calls. In round two, each D agent takes the opposite stance and quotes and rebuts its own first-round claims, before returning to its original stance in round three. RQ2 changes the debater model composition, counterbalances model identities and initial stances, and fixes the Judge and Gatekeeper. RQ3 plans four domain-specific debates followed by a Final Aggregator; debate rules, call budgets and resource comparisons remain to be locked. The scope remains 180 quarterly cases of nine U.S. stocks in 2021--2025, evaluated over 60 trading days using directional accuracy and annualized Sharpe.

\noindent Results: pending formal experiments. All three revised experiments are treated as incomplete. Prior protocol results are reported separately and are not automatically reused as revised formal results. Conclusions will follow completion of the experiments. Prior exposure to this sample, model training memory, purposive sampling and resource differences constrain interpretation; improvements from heterogeneity or specialization are not assumed.
\vspace{0.6cm}
\noindent Keywords: large language models, multi-agent debate, role switching, model heterogeneity, domain specialization, investment decisions
\clearpage
\tableofcontents
\clearpage
\pagenumbering{arabic}
'''
text+=sec('引言')+sub('研究背景')+third('LLM in Finance')+body(app,'研究背景')
text+=third('Multi-Agent Debate 與 Role-Switching')+r'''
原研究以固定立場辯論 C 與自我反駁式立場交換 D 的比較為核心。D 不只是閱讀對方後模仿反方，而是第二輪只能讀自己的第一輪論述、引用並反駁原主張，第三輪回原立場整合反證。新版從此核心出發，檢查模型組成及任務分工是否改變其效果。
'''
text+=sub('研究動機')+third('自我反駁機制的增量價值')+body(app,'研究動機')
text+=third('模型同質性與推理差異')+r'''
Bull 與 Bear 雖有相反角色提示，使用相同基礎模型時仍可能共享知識邊界、推理偏好與錯誤。角色差異不保證有效推理差異；異質模型是否提供互補性仍需檢驗 \citep{zhang2025stop}。不同模型的能力、訓練資料及輸出風格也可能不同，因此模型替換帶來的績效差不能直接歸因於異質性。
'''+third('Generalist 資訊集中與領域分工')+r'''
既有四個研究代理人提供資料整理分工，決策推理仍集中於共同 Bull/Bear。技術、基本、新聞情緒與總經證據的時間尺度及訊號型態不同，合併後可能壓縮特定領域反證或增加 context 負擔。此為研究假說，不是已由舊負面結果證實的原因。RQ3 將分工延伸至領域內多空論證，再由上層整合，評估收益、衝突與資源負擔。
'''
text+=sub('研究目的')+third('立場交換機制')+'檢驗自我反駁式立場交換相對固定立場辯論的增量價值，維持原核心問題。\n'
text+=third('模型異質性')+'檢驗同一辯論內的模型組成是否改變 D 相對 C 的效果，區分角色差異與模型差異。\n'
text+=third('領域專業化')+'檢驗領域內辯論及上層整合相對 Generalist 的績效與成本，評估任务分解的價值。\n'
text+=sub('Research Questions')
for title,rq in [('RQ1 原始機制',rq1),('RQ2 Model Heterogeneity',rq2),('RQ3 Domain-Specialized Debate',rq3)]: text+=third(title)+'\\begin{quote}'+rq+'\\end{quote}\n'
text+='三題構成機制、模型組成與任務分工的連續研究，但 RQ2/RQ3 不是必須等待 RQ1 不顯著才執行的事後補救。三題正式新版實驗均尚待執行；舊 RQ1 是否沿用須先核對身分與規則並由研究者確認。\n'
scope=body(app,'研究範圍').replace('模型 & 開源模型 qwen3:32b','模型 & RQ1 基準模型、RQ2 Model A/B 與固定 Judge 正式實驗前待鎖定；qwen3:32b 為既有執行模型')
text+=sub('研究範圍')+third('樣本與資料時間邊界')+scope
text+=third('預測期間與決策層')+r'''
維持九股、20 季末、180 個 stock $\times$ date cases、60 trading days。C/D 候選裁決沿用 Buy/Sell，Gatekeeper 可降為 Hold 或不交易；A/B 允許 Hold，僅作補充對照。主要分析沿用候選決策層，守門後實際風險處理另列敏感性。原月度／20 日比較移至未來展望，不任意替換正式樣本。
'''

text+=sec('文獻探討')
text+=sub('Multi-Agent Debate')+third('辯論與自我一致性的公平對照')+body(ssrn,'多代理人辯論')
text+=sub('Role-Switching / Self-Rebuttal')+third('機制假說與失效條件')+body(ssrn,'角色交換與多視角推理')
start=ssrn.index('\\paragraph{機制動機與可能失效的條件。}')
end=ssrn.index('\\subsection{研究問題}',start)
text+=ssrn[start:end]
text+=sub('Model Heterogeneity in Multi-Agent Systems')+third('異質性、能力組成與模型偏向')+r'''
\citet{zhang2025stop} 對多代理人辯論評估與模型異質性提出檢驗，提供不同底層模型共同推理的研究動機。其基準結果不能直接外推到金融未來報酬或本研究自我反駁規則。RQ2 將同一辯論內 A/B 共存與整套系統換成 B 區分；後者仍是 homogeneous setting。模型能力、偏向、Judge 親和與錯誤相關性須分別診斷。

【需補文獻】異質模型辯論的能力匹配對照、錯誤互補與模型偏向量測，以及在共同金融資料下對機制交互作用的識別。未宣稱已完成全面文獻搜尋。
'''
text+=sub('Financial LLM and Investment Agents')+third('金融語言與代理人工作流')+body(ssrn,'金融 LLM 與投資代理人')
text+=sub('Domain Specialization / Task Decomposition')+third('摘要分工與決策分工的區分')+r'''
TradingAgents 與 StockAgent 提供金融代理人工作流的既有脈絡 \citep{xiao2024tradingagents,zhang2024stockagent}。資訊摘要分工、策略角色分工與四個資料領域各自執行多空辯論並不相同；不能以既有專業分析師模組直接證明新版 RQ3 的效果。領域切分可能保留局部反證，也可能失去跨領域脈絡或增加整合錯誤，兩者均須評估。

【需補文獻】直接比較 Generalist 與領域內辯論的研究、task decomposition 的資訊損失／資源公平、cross-domain aggregation 與 context 負荷。此處是待檢驗設計，不以「首次提出」界定貢獻。
'''
text+=sub('Look-Ahead Bias and Financial Evaluation')+third('資料時間邊界與模型訓練記憶')+body(ssrn,'前視偏差與評估').replace('第~\\ref{sec:memorydiagnostic} 節','舊協議前導診斷小節')
text+=sub('Literature Synthesis / Research Gap')+third('機制、模型與任務的連續問題')+r'''
本研究承接辯論、自我一致性、角色交換、金融語言處理與前視偏差文獻，從固定案例資料下自我反駁有無增量價值出發，再檢驗指定模型組成與領域分工是否改變決策。原文獻不足以證明同質性或資訊負荷已導致舊結果失效；新版三題提供可稽核比較，而不預设任何架構必然較佳。文獻中的問答正確性、事實查核與投資報酬預測端點不同，不能直接等同。原自我一致性、角色交換與負面結果來源皆保留。
'''

text+=sec('研究方法')+sub('研究架構')+third('共同資料層與三個實驗分支')+r'''
既有 Coordinator、Data Snapshot 與四類 Research Agents 保留。共同資料層產生不含投資方向的鎖定研究資料與證據登錄。RQ1/RQ2 讀取同一 Neutral Report；RQ3 Generalist 仍讀整合報告，Domain 分支使用相同研究輸出的領域切片，不另抓新資料或以不同摘要模型重製輸入。概念架構如下，新增分支尚待實作驗證。
\begin{figure}[H]\centering
\begin{tikzpicture}[node distance=6mm,box/.style={draw,align=center,font=\small,text width=125mm,inner sep=4pt},arr/.style={-{Stealth[length=2mm]}}]
\node[box] (data) {Data：同案例、filing date、historical vintage、timestamp};
\node[box,below=of data] (research) {Immutable Snapshot $\rightarrow$ Four Research Agents $\rightarrow$ Evidence Registry};
\node[box,below=of research] (branches) {RQ1：Homogeneous C/D，same Neutral Report\\RQ2：Heterogeneous C/D，AB/BA counterbalance\\RQ3：Generalist／四個 Domain Bull/Bear Debates};
\node[box,below=of branches] (judge) {RQ1/2 固定 Judge；RQ3 Final Judge / Aggregator};
\node[box,below=of judge] (gate) {既有 Gatekeeper：證據、資料覆蓋與風險驗證};
\node[box,below=of gate] (back) {Backtest $\rightarrow$ Accuracy / Sharpe / Cost / Diagnostics};
\draw[arr] (data)--(research);\draw[arr] (research)--(branches);\draw[arr] (branches)--(judge);\draw[arr] (judge)--(gate);\draw[arr] (gate)--(back);
\end{tikzpicture}
\caption{新版研究概念架構。三分支以共同資料、候選決策及評估口徑銜接；RQ3 的規則與資源預算尚未鎖定。}\label{fig:flow}\end{figure}
'''+third('Judge 與 Gatekeeper')+r'''
Judge 綜合辯論、核對證據並形成投資方向。Final Aggregator 是 RQ3 整合四個 Domain Views 的上層裁決者，不再額外假設其後需要另一個決策 Judge。Gatekeeper 在投資方向形成後檢查引用、coverage、volatility、risk threshold、基準率歷史並必要時降級；它不承擔四領域投資觀點整合。
'''
text+=sub('資料收集')+third('四類資料與時間控制')+body(app,'資料收集').replace('共 83,093 則','舊版資料統計為 83,093 則，新版凍結數量待核對')
text+=third('資料品質與版本風險')+body(ssrn,'資料品質處理')+r'''
新聞依發布 timestamp 與時區篩選，財報以 filing date 判定實際可得，macro 以分析日已發布的 historical vintage 建立；價格輸入只使用 cutoff 以前。每案記錄 data version、snapshot hash、evidence ID、code version、model version 與 audit trail。同案跨條件共用快照不能單獨證明資料內容正確，須驗證可用時間與来源。舊版 FinBERT revision、37案新聞排除集合與調整行情下載版本均仍待核對，不因新版 RQ 改變而取消揭露。
'''
text+=sub('實驗設計')+third('Common Experimental Setup')+r'''
共同使用固定案例、快照、outcome 與回測。研究代理人模型、輸出與 Neutral Report 凍結，避免 RQ2 更換辯論者時同時改變資訊摘要。C/D 的 Judge、Gatekeeper、溫度與名目輪次對齊；呼叫種子依版本化規則保存。原 qwen 溫度0.2、基礎seed905、context8192、輸出2048與投票溫度0.8為舊協議執行紀錄，新版是否沿用須重新鎖定，不能跨模型假設種子必然有效。

原三輪C/D各七次名目決策呼叫可沿用，另記實際成功、失敗、retry calls及輸入／輸出tokens。記憶僅含分析日前已到期同股案例；其來源、各分支可見範圍與更新政策必須相同且正式前凍結。若各組累積各自的歷史決策，須承認後續輸入受先前處理影響，估計為動態整套流程效果。正式批次不得讀試跑結果，執行順序、模型service drift、截斷規則與失敗處置亦需記錄。
'''
arms_start=app.index('\\paragraph{四組決策機制。}')
arms_end=app.index('\\paragraph{比較量。}',arms_start)
text+=third('Fixed-role Debate C')+r'''
C 的 Bull/Bear 三輪維持原始立場，每輪各一次呼叫，依原資訊可見規則批評與整合，再交固定 Judge，名目共七次。A 單次判斷、B 七次獨立投票僅供補充。下表保留既有流程，不代表新版三題已完成。
'''+app[arms_start:arms_end]
d_start=app.index('\\paragraph{比較量。}')
d_end=app.index('\\paragraph{偏誤控制。}',d_start)
text+=third('Role-Switching Debate D')+app[d_start:d_end]+r'''
Model identity 在三輪固定：只有 stance 在第二輪反轉、第三輪回復。強制引用自己第一輪原文的驗證規則與重試屬處理的一部分，正式前保存 validator hash。現有原文核對採至少70\%字詞連續相同；這只檢查引用來源，不能證明反駁語意有效。
'''
text+=third('RQ1 Design')+rq1+r'''

RQ1 維持同質辯論者、同資料與七次名目決策呼叫，估計整套D相對C的方向準確率及Sharpe差。單次判斷及獨立投票不取代核心對照。下述舊偏誤控制敘述屬既有protocol紀錄，新版登記與身分核對尚待完成；即使舊RQ1文字相同，也不得自行升格舊結果。
'''
bias_start=app.index('\\paragraph{偏誤控制。}')
bias_end=app.index('\\paragraph{評估方法。}',bias_start)
text+=app[bias_start:bias_end]
text+=third('RQ2 Heterogeneous Model Design')+r'''
RQ2 主要操弄多空辯論者的模型組成；固定 case、snapshot、Neutral Report、Research Agents、三輪、Role-Switching rule、Judge、Gatekeeper、outcome與backtest。Homogeneous為A/A；Heterogeneous有兩個平衡配置：AB（原Bull=A、原Bear=B）與BA（原Bull=B、原Bear=A）。兩個配置均需有C與D，不讓A永遠是Bull。
\begin{table}[H]\centering\small
\caption{異質D的身份與立場，model identity不交換}
\begin{tabularx}{\textwidth}{@{}lYY@{}}\toprule
輪次 & AB配置 & BA配置\\\midrule
Round 1 & A Bull；B Bear & B Bull；A Bear\\
Round 2 & A Bear；B Bull & B Bear；A Bull\\
Round 3 & A Bull；B Bear & B Bull；A Bear\\\bottomrule\end{tabularx}\end{table}
正式實驗前待鎖定：Model A/B、Judge model及版本、各模型prompt與生成參數、AB/BA指派與匯總方式。建議每案執行AB/BA以檢查模型偏向，但不自動決定實驗量；兩配置共享同一案例與outcome，不是360個獨立案例。單次隨機平衡分派亦須事前登記。

主要比較為C\_hetero與D\_hetero，再與C\_homo/D\_homo之差比較。A/A對A/B同時改變能力組成；建議另考慮B/B對照，尚未納入正式必跑條件。即使加入B/B，也不能宣稱完全分離能力、互補性與家族差異。固定Judge也可能偏好某模型文風；模型標籤盲化、輸入順序及context上限須控制。不要同時替換Judge、Gatekeeper或研究摘要模型。
'''
text+=third('RQ3 Domain-Specialized Design')+r'''
Generalist使用同一四類整合研究報告，由共同Bull/Bear辯論。Domain架構從同一鎖定四類研究輸出分流：Technical Bull/Bear形成Technical View；Fundamental Bull/Bear形成Fundamental View；Sentiment Bull/Bear形成Sentiment View；Macro Bull/Bear形成Macro View。四個Views送Final Judge/Aggregator，再經既有Gatekeeper與同一Backtest。每領域必須有多空論證與交互檢查，不以四份摘要替代辯論。

局部代理人使用其領域相同快照的證據切片，禁止偷用其他領域資料；同一資訊在領域間的归屬與共享背景規則須先定義。各域View均针对同一60交易日投資方向；短期證據不是改用20日outcome。模型組成、裁決層、記憶、輸出與風險規則盡量控制。若domain採D而generalist採C，效果同時混入分工與switching，不可稱純分工效果。

\begin{enumerate}
\item 各Domain採Fixed only、Role-Switching only或兩者皆跑：正式實驗前待鎖定。
\item 各Domain nominal call budget、View生成與Aggregator是否另計呼叫、重試上限：正式實驗前待鎖定。
\item 與Generalist比較的decision calls、tokens、compute cost與latency如何匹配或呈現：正式實驗前待鎖定。
\item Final Judge input schema（Views、原證據、transcripts、記憶、順序及長度）：正式實驗前待鎖定。
\item Domain View standardized output schema（stance、confidence、evidence、counter-evidence、uncertainty、missingness等候選欄位）：正式實驗前待鎖定，候選欄位不是已定schema。
\end{enumerate}
可以提出固定預算比較、同輪次但不同資源的整體架構比較或成本效益前緣作選項，目前不採定。四組辯論可能增加compute，應報所有研究、辯論、View生成、Aggregator與retry成本，不能只數Final Judge。四領域分歧4:0、3:1、2:2僅適用四個有效二元方向；缺失或棄權需另列。
'''
text+=third('Evaluation')
eval_start=app.index('\\paragraph{評估方法。}')
eval_end=app.index('\\subsection{工具及設備}',eval_start)
ev=app[eval_start:eval_end].split('%% =====================================================================')[0]
text+='以下保留原RQ1評估定義與計算參數，作新版沿用基礎；參數與code版本仍須正式前確認，不代表已完成新版評估。\n'+ev
text+=r'''
Secondary metrics包含cumulative return、maximum drawdown、decision distribution、confidence、transaction-cost adjusted return與disagreement。RQ2另報Bull/Bear分歧、模型決策差與model-specific bullish/bearish bias；RQ3報四域stance、一致程度與跨領域衝突的處理。分歧增加、引用更完整或更常看空均不直接代表績效改善；confidence是自報值，不自动视为校準機率。候選層與守門後層分開報coverage、条件accuracy及日報酬，無風險基準零与低曝險配置亦須揭露。
'''
text+=third('Statistical Analysis')+r'''
RQ1沿用配對McNemar、Ledoit--Wolf／區塊bootstrap、雙尾檢定、共同兩端點Holm及日期群聚敏感性；兩端點差皆為正且校正後顯著才支持優越性。樣本共享20日期、股票反覆出現與重疊持有期，獨立性假設须以群聚/區塊方法檢查；日期群聚數有限，不把敏感性當成充分校正證明。未顯著不等於等效或非劣，等效界值不能看結果後補訂。

RQ2首先於事先指定指派單位比較D\_hetero與C\_hetero。是否再估計$(\mathrm{Acc}_{D,h}-\mathrm{Acc}_{C,h})-(\mathrm{Acc}_{D,a}-\mathrm{Acc}_{C,a})$之交互差，僅提出共同案例/日期區塊重抽樣或配對交互模型的建議，正式前待鎖定。此為實驗因素比較，不直接套用觀察研究的DID。不能由一邊顯著而另一邊不顯著推論交互作用。AB/BA平均後正確性非二元，不可直接普通McNemar；Sharpe须重新計算配對日序列，不能平均兩個Sharpe或拼接成雙倍T。

RQ3待domain rule、call budget與output unit鎖定後，才選定配對accuracy與策略日序列檢定；可沿用同case配對与日期區塊方法作候選，不预先确定最终统计方案。各領域不是四个独立金融案例。三題比較、多端點与diagnostics的檢定family、Holm範圍與探索分析標籤須一併登記；RQ1原兩端點校正不自动處理全部新增檢定。失敗、缺失、排除與重跑規則均須看結果前凍結。
'''
text+=sub('工具及設備')+third('既有工具鏈與 GPU')+body(app,'工具及設備').replace('部署開源模型 qwen3:32b','既有部署開源模型 qwen3:32b；新版模型待鎖定')

text+=sec('系統設計與實作')+sub('系統架構')+third('既有流程與新增模組狀態')+body(app,'系統架構')+r'''
上述是既有系統；新版將從共同research outputs分至三題分支。下述Model Router、Domain Debate Module與Final Aggregator為新增設計需求，尚未由本次文件修訂完成實作或驗證；不將概念圖當執行證據。
'''
text+=sub('功能模組')
for title,paragraph in [
('Coordinator 與 Data Snapshot','協調者固定案例、protocol、cutoff與模型設定，資料代理人建立不可變快照，內容hash與evidence ID連結執行紀錄。'),
('Research Agents','四面向研究代理人各自摘要與引用同一時間邊界內證據，產生鎖定Neutral Report與領域輸出；驗證失敗時的來源摘錄降級亦記錄。'),
('Short-term Memory / Long-term Memory','短期紀錄保留每次prompt hash、種子、用量、辯論與裁決；長期記憶只讀分析日前已到期同股案例。舊C/D Judge可讀長期記憶、A/B不可；新版各分支的來源與權限待固定，禁止未來outcome寫回後被過去案例讀取。'),
('Judge / Gatekeeper / Backtest','Judge逐項核對論點與證據後輸出候選方向；Gatekeeper檢查引用、coverage、volatility與基準率歷史，必要時降級。Backtest計算相同開盤進出、成本與日序列，不把四域View當四個部位。'),
('Model Router','新增待實作：保存agent identity、初始stance、round stance與model ID/version，按AB/BA配置呼叫不同模型；第二輪只改stance，引用仍指向同agent第一輪。禁止fallback靜默改模型，API seed支援與provider drift需記錄。'),
('Domain Debate Module','新增待實作：將同一快照的領域證據分流給各域Bull/Bear，執行尚待鎖定的Fixed或Switch規則，保存domain transcripts與Domain Views。證據namespace與可讀權限须驗證。'),
('Final Aggregator','新增待實作：按待鎖定schema讀取四個Views，評估衝突、反證與缺資料，輸出一個最終候選決策；其prompt、輸入順序與記憶須版本化，之後仍進相同Gatekeeper。')]: text+=third(title)+paragraph+'\n'
text+=sub('介面設計')+third('既有研究台與新版分支規劃')+body(app,'介面設計')
text+=r'''
此圖為既有介面，不代表新增模組已上線。後續需呈現model assignment、domain debates、四Views、Aggregator、名目與實際資源紀錄；新版介面實作狀態仍待驗證。
'''
text+=sub('實作流程與驗證')+third('既有開發流程')+body(app,'實作流程')
text+=third('Audit Trail 與版本核對')+body(ssrn,'驗證與可審查性')
text+=sub('Implementation Challenges')
text+=third('異質格式與 context handling')+'不同模型的structured output、tokenizer與context能力不同，轉接器不能加入額外金融訊息或默默截去某方反證。需统一輸出契約、保存raw response與截斷日志，約束輸入長度並記錄失敗。\n'
text+=third('資源公平與 domain output normalization')+'相同calls不等於相同tokens、成本或latency；平行四域還有wall-clock與累計推理時間之差。Views長度、缺失值、證據與反證欄位標準化會影響上層裁決，schema與prompt必須先鎖定，不能依事後績效調權重。\n'
text+=third('模型能力混淆')+'Router能指定異質模型不代表能隔離異質性效果。需解釋能力組成、Judge文風偏好與不同訓練記憶風險；B/B控制、盲化及重跑僅是待採的研究建議，不假稱已驗證。\n'

def result_table(rows,columns):
    head=' & '.join(columns)+r'\\'
    lines=[r'\begin{table}[H]\centering\small',r'\begin{tabularx}{\textwidth}{@{}l'+('Y'*(len(columns)-1))+r'@{}}\toprule',head,r'\midrule']
    for row in rows: lines.append(row+' & '+' & '.join(['【待實驗結果】']*(len(columns)-1))+r'\\')
    return '\n'.join(lines)+r'\bottomrule\end{tabularx}\end{table}'+'\n'

text+=sec('結果與討論')+'新版三組正式實驗尚未完成。前三節全部為結果框架，第四、五節是舊協議紀錄，不自动納入新版正式推論。\n'
text+=sub('RQ1 Results')+third('C vs D 主要端點與敏感性')+result_table(['60日方向準確率','年化Sharpe'],['指標','C','D','差與CI／校正p'])
text+='【待實驗結果】完成後依預先指定共同端點回答RQ1，報candidate/post-gate、coverage、配對案例、方向分歧數、return、drawdown、成本與日期群聚區間；負面或不確定結果仍報告。\n'
text+=sub('RQ2 Results')+third('Homogeneous / Heterogeneous C/D 效果')+result_table(['A/A','AB','BA'],['模型配置','C績效','D績效','D−C'])
text+='【待實驗結果】依正式前鎖定的配置匯總與統計方法呈現accuracy與Sharpe；若採B/B另行列出。交互作用僅在事前指定後檢定，不以兩組p值大小比較推論效果改變。\n'
text+=third('Counterbalancing 與模型偏向診斷')+'【待實驗結果】分原stance及model identity呈現分歧、bullish/bearish bias、AB/BA一致性、呼叫失敗及tokens；分歧增加不等於績效改善。\n'
text+=sub('RQ3 Results')+third('Generalist / Domain-specialized 績效與成本')+result_table(['Generalist','Domain-specialized'],['架構','Accuracy／Sharpe','Return／Drawdown','資源與延遲'])
text+='【待實驗結果】正式比較對應相同debate rule及已鎖定公平預算；若未匹配compute，僅描述整套架構與成本效益，不將增益歸因純分工。\n'
text+=third('Domain stance 與衝突整合')+'【待實驗結果】報Technical、Fundamental、Sentiment、Macro stance與4:0／3:1／2:2分布，缺失或abstain另列。追蹤Final Judge對跨域證據衝突之處理；規則若看結果後調整，另標探索性。\n'
text+=sub('舊協議 Prior Results')+r'''
\noindent\textbf{本節所有數字、檢定及案例均為舊協議prior result，尚未經研究者確認可列新版正式Results。}下列沿用原報告的完成敘述只指既有qwen季度protocol，不表示新版三組實驗完成。本次未重新核對raw outputs或重算表格。保留負面結果、原表註及case描述，避免因改題消失。
'''+third('舊 qwen 績效與檢定')+body(app,'實驗結果')
text+=third('正反分歧案例與未支持解釋')+r'''
以下原case分析在結果已知後選取，只供描述，不識別因果機制。原文「研究問題」與「事前標準」均指舊protocol；少數case不代表全16案模式。
'''+body(app,'結果分析')
text+=sub('Exploratory Cross-model Analysis 與前導診斷')+third('Gemini homogeneous 比較')+r'''
整套系統改用 Gemini 仍然是 homogeneous-model setting，不等於新版 RQ2 所研究的 heterogeneous debate。以下從較詳盡原稿保留同批探索性結果及未支持假說；舊文的跨模型RQ2不再列正式Research Question。
'''
expl=body(ssrn,'探索性分析：跨模型與基準比較')
expl=expl.replace('\\label{sec:exploratory}','').replace('\\paragraph{對 RQ2 之回答。}','\\paragraph{對舊跨模型探索問題之回答。}').replace('符合 RQ2 對','符合舊跨模型探索問題對')
expl=expl.replace('第~\\ref{sec:methods} 節','研究方法之評估定義')
text+=expl
text+=third('舊協議記憶與匿名辨識探針')+body(ssrn,'前導記憶與匿名辨識診斷')
text+=sub('Integrated Discussion')+third('機制、模型與任務之價值及替代解釋')+r'''
【待實驗結果】討論首先回答自我反駁流程是否有增量價值，再檢查指定模型組成及領域分工是否改變該價值。若RQ1效果有限，不能先斷言同質性或資訊集中就是原因；若RQ2/RQ3提高績效，仍須檢查能力差距、資源、輸入長度、Judge與隨機生成等替代解釋。最後依證據討論有用差異存在於角色、模型或任務／領域分工，允許三者均未顯示穩定改善或呈現不同成本交換。此問題的答案不預先寫定。
'''
text+=sub('研究限制')+third('既有誠信與可重現性限制')+body(ssrn,'研究限制')
text+=third('能力差距、成本與跨領域整合限制')+r'''
新增限制包括：異質模型與能力組成、訓練記憶差異難以完全分離；同temperature或seed不代表相同生成機制；四域切分為人工設計，不證明最優分工；局部推理可能遺失跨域互動；Aggregator prompt、順序與文風可能改變整合；四組domain增加calls或tokens會混入資源效果；缺失領域與長context截斷可能造成不同輸入有效量。三題均使用已看過的歷史樣本，不能由新登記恢复完全確認性。原結果不顯著不證明等效，disagreement或文字豐富程度也不證明績效。新版未完成的重跑、消融及汙染檢驗均如實保留待執行狀態。
'''

text+=sec('結論與建議')+sub('研究結論')+third('RQ1–RQ3 逐題回答')
text+='RQ1：【待實驗結果】。\n\nRQ2：【待實驗結果】。\n\nRQ3：【待實驗結果】。\n\n正式結論將依共同端點、資源對照及不確定性逐題回答；舊負面結果仍見prior result，不作新版答案。\n'
text+=sub('應用與價值')+third('可追溯決策輔助')+body(app,'應用與價值')
text+=third('Multi-Agent System Design')+r'''
研究價值也在於系統設計的可辨識比較：不同代理人名稱不足以證明有用差異；是否需要heterogeneous models、複雜資訊是否適合specialists、以及domain decomposition的效益都應以受控結果與成本評估回答。若未觀察改善，仍可提供架構適用邊界與可重現評估經驗，不能把負面結果改成分工必然有用。
'''
text+=sub('未來展望')+third('Temporal-scale robustness')+r'''
原月度／20日設計移為Temporal-scale robustness。較短尺度是否減輕一次整合資訊的負担需另做研究，不等同本次domain分工；原每月擴充至540案例為既有規劃且未執行，不任意併入本次180案正式樣本。
'''
text+=third('模型、路由、消融及獨立樣本外')+r'''
後續可考慮更多模型、heterogeneous Judge、adaptive routing、dynamic debate、domain weighting、compute efficiency與不同辯論輪數。保留原只讀自身但不換立場的消融、空頭及高波動檢查、同案多種子C/C'重跑與完整汙染探針；參數與權重學習須另有開發／驗證資料，最後採新期間或新標的獨立樣本外評估，不在同批產生假說的資料上改稱確認性證據。
'''

# Embed all original SSRN bibliography entries to avoid a separate BibTeX project requirement.
bbl=(root/'stance-shift-ssrn.bbl').read_text(encoding='utf-8')
bbl=bbl.replace('\\begin{thebibliography}{}','\\begin{thebibliography}{99}')
text+='\n\\clearpage\n\\setcounter{section}{7}\n\\renewcommand{\\refname}{七、參考文獻}\n'+bbl
text+=r'''
\noindent 原書目沿用作者年份格式；全部原BibTeX另存於修訂附件。異質辯論能力控制、domain-specialized debate及task decomposition的直接對照仍【需補文獻】，不以佔位文獻冒充reference。原文獻年份採原書目版本，本次新動機所用Zhang、TradingAgents與Huang來源另經原始頁面核對。
\clearpage
\section*{新版正式實驗開始前必須鎖定事項}
\addcontentsline{toc}{section}{新版正式實驗開始前必須鎖定事項}
\subsection*{RQ2}
\begin{itemize}
\item Model A、Model B、Judge model、provider/API ID、model version/weights digest與服務存取日期。
\item AB/BA counterbalancing、逐案或分層分派、重複配置匯總與B/B補充對照是否採用。
\item prompt與hash、temperature、seed及實際套用狀態、context/output limits、重試／fallback規則與Judge順序盲化。
\end{itemize}
\subsection*{RQ3}
\begin{itemize}
\item 每個domain採Fixed、Switch或兩者；對應Generalist baseline及各域模型組成。
\item 每域calls、View生成calls、Final Aggregator calls、retry budget與研究層成本計入方式。
\item Final Aggregator prompt、input schema、domain output schema、evidence permissions、missing/abstain與長度處理。
\item call-budget fairness、token／compute cost handling、latency、wall-clock與總推理時間的比較口徑。
\end{itemize}
\subsection*{共同}
\begin{itemize}
\item data version、immutable snapshot/hash、Neutral Report hash、四類evidence registry、filing/vintage/timestamp驗證與FinBERT revision。
\item sample、180案名單、exclusion rule、37案新聞集合、失敗／缺失與重跑規則。
\item outcome、60交易日開盤進出、價格調整、成本、candidate/post-gate、daily panel T與無風險基準。
\item statistical plan、檢定families、Holm範圍、群聚/區塊、interaction是否採用、指派匯總與檢定力規劃。
\item code version/hash、protocol version/hash、preregistration時間、變更紀錄、raw輸出與aggregation一致性。
\item Judge固定設定、Gatekeeper固定實作與thresholds、記憶來源／成熟時間／讀寫隔離。
\item 舊RQ1正式沿用前，逐項比對data、protocol、prompt、model、sample、seed、outcome、evaluation與preregistration status，交由研究者確認；未確認前維持prior result。
\end{itemize}
\noindent\small 本文僅供學術研究與教學使用，不構成任何投資建議。
\end{CJK}
\end{document}
'''

# Retain original image when available; provide an explicit captioned fallback in a single-file editor.
text=text.replace(r'\includegraphics[width=\textwidth]{figures/ui-pipeline.png}',r'\IfFileExists{figures/ui-pipeline.png}{\includegraphics[width=\textwidth]{figures/ui-pipeline.png}}{\fbox{\parbox{0.9\textwidth}{既有介面圖資：原報告 figures/ui-pipeline.png。此單檔預覽以文字保留圖意：資料來源、資料代理人、快照、四類研究代理人、中立報告、決策分支、守門、回測與統計；原截图保留於既有報告，非新版功能證據。}}}')
# Remove/replace legacy cross references after reorganization.
text=text.replace('第~\\ref{sec:methods} 節','研究方法之評估小節').replace('第~\\ref{sec:memorydiagnostic} 節','舊協議前導診斷小節')
text=text.replace('本章說明實際完成並用於實驗之系統','本章保留既有完成系統的说明')
(root/'application-meeting-20261006.tex').write_text(text,encoding='utf-8')
shutil.copy2(root/'references.bib',out/'references-preserved.bib')

# Full readable Markdown companion, keeping table content and provenance (TeX remains authoritative).
def plain(tex):
    tex=re.sub(r'^%.*$','',tex,flags=re.M)
    tex=re.sub(r'\\(?:sub)*section\*?\{([^{}]*)\}',lambda m:'\n'+('#'*(1+m.group(0).count('sub')))+' '+m.group(1)+'\n',tex)
    tex=re.sub(r'\\paragraph\{([^{}]*)\}',r'\n**\1** ',tex)
    tex=re.sub(r'\\cite[pt]\{([^{}]*)\}',lambda m:'〔'+m.group(1)+'〕',tex)
    tex=re.sub(r'\\(?:grp|textbf|emph|texttt|textsf)\{([^{}]*)\}',r'\1',tex)
    tex=re.sub(r'\\(?:label|ref)\{[^{}]*\}','',tex)
    return tex
start=text.index('本專題延續')
md='# Part D 完整修改稿\n\n正文以原application.tex逐章保留與修訂；本檔是完整可讀對照，LaTeX為排版母稿。TeX表格保留於程式碼區供精確檢查。舊結果均為prior result。\n\n'+plain(text[start:])
md=re.sub(r'(\\begin\{table\}.*?\\end\{table\})',lambda m:'\n```latex\n'+m.group(1)+'\n```\n',md,flags=re.S)
md=re.sub(r'(\\begin\{figure\}.*?\\end\{figure\})',lambda m:'\n```latex\n'+m.group(1)+'\n```\n',md,flags=re.S)
(out/'Part-D-完整修改稿.md').write_text(md,encoding='utf-8')

manifest={'date':'2026-10-06','source':'application.tex','supplement':'stance-shift-ssrn.tex','status':'All revised formal RQ1/RQ2/RQ3 pending; old results prior only; no experiment or code changes','sources':{fn:hashlib.sha256((root/fn).read_bytes()).hexdigest() for fn in ['application.tex','stance-shift-ssrn.tex','references.bib']},'output':hashlib.sha256((root/'application-meeting-20261006.tex').read_bytes()).hexdigest()}
(out/'revision-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'tex_chars':len(text),'rq1_exact':rq1 in text,'sections':re.findall(r'\\section\{([^}]+)\}',text),'files':[p.name for p in out.iterdir()]},ensure_ascii=False,indent=2))
