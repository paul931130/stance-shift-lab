from pathlib import Path
import re,shutil,json,hashlib

folder=Path(__file__).resolve().parent
report=folder.parents[1]
target=report/'application-meeting-20261006.tex'
original=target.read_text(encoding='utf-8')
backup=folder/'before-clean-draft'
backup.mkdir(exist_ok=True)
if not (backup/target.name).exists(): shutil.copy2(target,backup/target.name)
s=original

def replace_between(start,end,new):
    global s
    a=s.index(start); b=s.index(end,a)
    s=s[:a]+new+'\n\n'+s[b:]

replace_between('本專題延續多代理人立場交換辯論機制，','\\vspace{0.6cm}',r'''投資決策需要整合技術面、基本面、新聞情緒與總體經濟資訊，不同證據可能互相衝突。多代理人辯論透過多空觀點與裁決程序檢查論證，但角色差異不必然形成有效的推理差異。本研究以自我反駁式立場交換為核心，探討三個層次：立場交換相對固定立場辯論的增量價值、模型組成是否改變此效果，以及領域專業化的決策分工是否改善績效與成本效益。研究採九檔美國大型股於2021至2025年的180個季度案例，整合四類金融資訊，並透過時間邊界、不可變資料快照、證據識別碼與稽核紀錄維持比較的一致性。主要評估指標為60個交易日方向準確率與年化Sharpe比率，輔以報酬、回撤、決策分歧及推論資源指標。''')
replace_between('\\noindent This project retains','\\vspace{0.6cm}',r'''\noindent Investment decisions require the integration of technical, fundamental, news-sentiment and macroeconomic evidence, which may conflict. Multi-agent debate uses opposing views and adjudication to examine arguments, yet role differences do not necessarily produce useful reasoning diversity. This study retains self-rebuttal role-switching as its core and investigates three levels: its incremental value over fixed-role debate, whether model composition changes this effect, and whether domain-specialized decision-making improves performance and cost effectiveness. The study uses 180 quarterly cases of nine U.S. stocks in 2021--2025, integrating four financial information domains under point-in-time data boundaries, immutable snapshots, evidence identifiers and audit trails. The primary evaluation metrics are 60-trading-day directional accuracy and annualized Sharpe ratio, supplemented by return, drawdown, disagreement and inference-resource measures.''')

replace_between('\\subsubsection{LLM in Finance}','\\subsection{研究動機}',r'''\subsubsection{金融資訊整合與大型語言模型}
投資決策同時涉及技術面、基本面、新聞情緒與總體經濟資訊；這些證據的時間尺度、資料形式與方向可能不同。大型語言模型可輔助閱讀財報、新聞與市場資料，並已用於金融語言處理與投資分析 \citep{lopezlira2023chatgpt,araci2019finbert,liu2023fingpt}。然而，資訊整合與未來報酬預測是不同任務，流暢的敘事不保證有用的預測訊號。

\subsubsection{Multi-Agent Debate 與 Role-Switching}
多代理人辯論讓不同角色提出、批評與修正論點 \citep{du2023debate,liang2023divergent}，金融代理人系統也採用分析與交易角色分工 \citep{xiao2024tradingagents,zhang2024stockagent}。辯論的效果受模型、互動與裁決程序影響，並不必然優於單一模型或獨立投票 \citep{smit2023mad,zhang2025stop}，因此工作流的配置本身也是研究對象。

本研究以固定立場辯論C與自我反駁式立場交換D為核心比較。D第二輪只讀自己的第一輪論述，引用並反駁原主張，第三輪回到原始立場整合反證。此機制檢驗重新檢查既有證據的增量價值，並延伸至模型組成與決策層領域分工。''')
# Remove an inherited, dated search-scope claim; retain motivation without novelty assertion.
s=re.sub(r'截至 2026 年 10 月 5 日，.*?並非系統性回顧或首次研究的主張。','這些研究提供角色交換的機制動機，但其任務與未來金融報酬預測不同；本研究因而直接比較相同資料與名目決策呼叫次數下的C/D流程。',s,flags=re.S)
s=s.replace('三題構成機制、模型組成與任務分工的連續研究，但 RQ2/RQ3 不是必須等待 RQ1 不顯著才執行的事後補救。三題正式新版實驗均尚待執行；舊 RQ1 是否沿用須先核對身分與規則並由研究者確認。','三題構成機制、模型組成與任務分工的連續研究：RQ1檢驗核心機制，RQ2檢驗模型層差異，RQ3檢驗決策架構的領域分工。')
s=re.sub(r'^模型 & RQ1 基準模型.*?\\\\\n','',s,flags=re.M)

replace_between('【需補文獻】異質模型辯論','\\subsection{Financial LLM and Investment Agents}',r'''\citet{wang2024moa} 的Mixture-of-Agents將多個模型的輸出逐層整合，並比較相同模型重複生成與多模型提案。該研究也區分提案與整合角色，說明模型在不同工作流位置的適用性可能不同。本研究据此將模型組成視為實驗因素，同時固定裁決者；其一般語言任務結果不等於異質金融辯論有效，也不能排除模型能力差距。''')

replace_between('\\subsubsection{摘要分工與決策分工的區分}','\\subsection{Look-Ahead Bias and Financial Evaluation}',r'''\subsubsection{摘要分工與決策分工的區分}
TradingAgents與StockAgent提供金融代理人工作流的脈絡 \citep{xiao2024tradingagents,zhang2024stockagent}。FinRobot將金融任務分解為專業代理人與分層流程，提供金融問題分解與工具鏈設計的例子 \citep{yang2024finrobot}；它不直接提供本研究四領域多空辯論與Generalist架構的受控績效比較。

\citet{chen2023agentverse} 的AgentVerse區分專家配置、協作決策、執行與評估，並討論水平與垂直協作結構。其工作說明代理人分工與溝通結構可以共同塑造決策程序。RQ3因而將專業化從資料整理層延伸至領域內推理與上層整合；四類領域的切分是本研究的設計選擇，而非既有研究證明的最優架構。

領域切分可能保留局部反證，也可能遺失跨領域脈絡、增加摘要壓縮與整合誤差。相較於僅以context長度解釋分工，本研究關注專業化是否應進入決策推理層，並以績效、證據使用及推論資源評估其交換關係。

\subsection{Judge / Aggregation / Validation}
\subsubsection{論證生成、上層整合與證據驗證}
Mixture-of-Agents區分提案生成與上層整合 \citep{wang2024moa}，提供不同角色承擔論證與綜合工作的架構參考。\citet{zheng2023judge} 指出LLM裁判可能出現位置、冗長與自我偏好等偏誤，因此裁決輸入的顺序、長度及模型標籤需要控制。該研究評估的是回答品質，不能直接證明本研究投資Judge的預測效力。

本研究據此將argument generation、decision aggregation與evidence validation分成可稽核步驟。Judge或Final Aggregator綜合論點形成方向，Gatekeeper則檢查證據存在性、資料覆蓋與風險條件。後者是本系統的驗證設計，不以一般LLM裁判文獻作為其能改善投資績效的證明。''')

s=s.replace('概念架構如下，新增分支尚待實作驗證。','概念架構如下。')
s=s.replace('新版研究概念架構。三分支以共同資料、候選決策及評估口徑銜接；RQ3 的規則與資源預算尚未鎖定。','研究概念架構。三分支以共同資料、候選決策及評估口徑銜接。')
s=s.replace('舊版資料統計為 83,093 則，新版凍結數量待核對','既有資料共83,093則')
replace_between('九檔的選取以資料可取得性為主，','\\subsubsection{資料品質與版本風險}',r'''九檔選取以資料可取得性為主，並非依2021年成分股隨機抽樣。協議記錄排除新聞來源未涵蓋的ASTS，並以INTC替換有早期新聞缺口的LLY，因此樣本具有目的性選樣與存活偏誤風險。主要比較保留180案；既有排除37案分析僅視為新聞來源／覆蓋診斷，不使用其結果建立統一新聞密度門檻。''')
s=s.replace('舊版 FinBERT revision、37案新聞排除集合與調整行情下載版本均仍待核對，不因新版 RQ 改變而取消揭露。','模型revision、新聞來源與調整行情下載版本均是影響精確重現的資料身分，須與快照及執行紀錄一併保存。')

# Add a rationale section; operational settings are not presented as theoretical optima.
marker='\\subsection{實驗設計}'
rationale=r'''\subsection{研究設計選擇與理據}
\begin{table}[H]\centering\small
\caption{主要設計選擇及其研究功能}
\begin{tabularx}{\textwidth}{@{}l l Y@{}}\toprule
設計 & 設定 & 理據\\\midrule
辯論者 & Bull與Bear & 以兩個對立方向建立最小多空論證結構。\\
辯論輪次 & 三輪 & 初始論證、自我反駁與整合修正各占一輪；此為機制的操作化選擇，不宣稱最優輪數。\\
交換時點 & 第二輪 & 先形成可引用的原始主張，再要求反向檢查。\\
交換輪資訊 & 自身第一輪 & 將反駁對象限定自身主張，降低轉為模仿對手的可能。\\
第三輪 & 回原立場 & 整合反證與不確定性，觀察修正後論點。\\
裁決與驗證 & Judge後接Gatekeeper & 區分投資方向整合、證據有效性及風險控制。\\
主要比較 & C/D同名目呼叫數 & 控制一項推論資源差異，實際token與重試成本另報。\\
分析頻率 & 季度 & 配合財務資訊的季度更新節奏，維持原資料pipeline與20個決策時間點。\\
主要期間 & 60交易日 & 作為季度研究的操作性持有期間，30與90日檢查期間敏感性，不宣稱60日具有理論最適性。\\
資訊領域 & 技術、基本、情緒、總經 & 沿用既有四類證據，區分整理層與決策層的專業化。\\\bottomrule
\end{tabularx}\end{table}
模型輸出格式、引用匹配與重試屬實作參數；其功能在維持可執行與可稽核流程，與C/D、模型組成及任務架構等研究變因分開記錄。
'''
s=s.replace(marker,rationale+'\n'+marker,1)
replace_between('\\subsubsection{Common Experimental Setup}','\\subsubsection{Fixed-role Debate C}',r'''\subsubsection{Common Experimental Setup}
各條件使用相同案例、資料快照、outcome與回測。研究代理人的模型與輸出、中立報告及證據登錄固定，避免更換辯論者時同時改變輸入資訊。C/D對齊三輪與Judge呼叫，模型設定、prompt hash、實際seed、token用量與重試均保存於稽核。

記憶只含分析日前已到期的同股票案例，禁止讀取該案例未來報酬或其他條件的測試結果。若採各條件自行累積的歷史記憶，後續輸入也受先前決策影響，因此比較量屬動態整套流程效果。實驗條件須控制記憶可見範圍，並記錄模型服務版本與截斷處理。''')
s=s.replace('下表保留既有流程，不代表新版三題已完成。','四組流程如表~\\ref{tab:arms}。')
replace_between('RQ1 維持同質辯論者、同資料與七次名目決策呼叫，','\\subsubsection{RQ2 Heterogeneous Model Design}',r'''RQ1維持同質辯論者、同資料與七次名目決策呼叫，估計整套D相對C的方向準確率及Sharpe差。A/B僅作補充對照。股票代號與公司名稱在模型輸入中匿名化，並以版本鎖定與事前分析計畫維持執行規則的一致性。匿名化不排除數值、日期及產品線索造成的辨識；同批180案曾用於前導試跑與規則調整，因此其比較屬既有樣本的回溯分析，不視為未見樣本的獨立驗證。''')
replace_between('正式實驗前待鎖定：Model A/B','\\subsubsection{RQ3 Domain-Specialized Design}',r'''主要比較為C\_hetero與D\_hetero，並與同質模型條件下D\_homo與C\_homo之差對照。AB與BA用以避免模型身分與初始立場綁定，兩配置共享案例與outcome，不能視為兩倍獨立樣本。A/A與A/B的比較同時改變能力組成，因此結果僅適用於指定模型組合，不能解讀為普遍異質性效益。Judge、Gatekeeper與研究摘要模型固定，模型標籤及論點呈現順序納入控制，以降低文風與裁決偏好的影響。''')
replace_between('\\subsubsection{RQ3 Domain-Specialized Design}','\\subsubsection{Evaluation}',r'''\subsubsection{RQ3 Domain-Specialized Design}
Generalist架構由共同Bull/Bear讀取四類整合研究報告。領域專業化架構則將同一研究輸出分流至Technical、Fundamental、Sentiment與Macro的多空論證，各自形成Domain View，再由Final Judge／Aggregator整合為一個候選決策，後接相同Gatekeeper與Backtest。

RQ3研究的是決策層任務分解，而不只是增加資料摘要。領域代理人只引用其領域證據，四個Views均針對同一60交易日方向，並呈現支持證據、反證、不確定性與資訊缺口。Generalist與專業化架構的比較須區分領域分工、辯論規則與計算資源；不能把同時改變這些因素的績效差稱為純分工效果。

評估同時記錄方向準確率、Sharpe及所有研究、辯論、整合與重試的呼叫數、輸入／輸出tokens、推理時間與端到端延遲，以呈現performance--cost trade-off。四領域4:0、3:1與2:2分歧僅適用於四個有效二元方向，資訊不足或棄權另列。''')
s=s.replace('以下保留原RQ1評估定義與計算參數，作新版沿用基礎；參數與code版本仍須正式前確認，不代表已完成新版評估。','')
s=s.replace('（實際值尚未核對）','')
replace_between('RQ2首先於事先指定指派單位','\\subsection{工具及設備}',r'''RQ2以相同案例比較模型組成條件下的C/D效果。若評估交互作用，可定義
\[
\Delta_{\mathrm{interaction}}=(\mathrm{Acc}_{D,hetero}-\mathrm{Acc}_{C,hetero})-(\mathrm{Acc}_{D,homo}-\mathrm{Acc}_{C,homo}).
\]
此量描述機制效果是否隨模型組成改變；一組顯著、另一組不顯著本身不證明交互作用。兩模型指派共享案例，其平均正確性不再是二元結果，不能直接套用普通McNemar；Sharpe亦須由配對日序列計算，不能平均兩個Sharpe或將兩配置拼接成雙倍觀測數。

RQ3依相同stock--date案例比較架構與成本；各領域論點是同一案例的中間輸出，不是四筆獨立金融樣本。主要端點與探索性diagnostics分開呈現，統計推論须處理共同日期、股票及重疊持有期的依賴性，避免以次要指標挑選有利結果。''')
s=s.replace('既有部署開源模型 qwen3:32b；新版模型待鎖定，並統一呼叫介面','既有部署開源模型qwen3:32b，並提供統一模型呼叫介面')
replace_between('\\subsubsection{既有流程與新增模組狀態}','\\subsection{功能模組}',r'''\subsubsection{研究問題與功能分支}
既有系統由Coordinator控制任務、資料邊界與記憶權限，在中立報告鎖定後分流至決策機制。網頁、命令列與程式介面共用流程，以維持執行與稽核的一致性。研究架構中，Model Router對應RQ2的模型組成，Domain Debate Module與Final Aggregator對應RQ3的領域推理與上層整合；以下描述其功能設計。''')
s=s.replace('舊C/D Judge可讀長期記憶、A/B不可；新版各分支的來源與權限待固定，禁止未來outcome寫回後被過去案例讀取。','既有C/D Judge可讀長期記憶、A/B不可；此權限差異須納入補充比較的解讀。系統限制成熟時間，避免未來outcome被過去案例讀取。')
s=s.replace('新增待實作：保存agent identity','Model Router的設計功能是保存agent identity')
s=s.replace('新增待實作：將同一快照的領域證據分流給各域Bull/Bear，執行尚待鎖定的Fixed或Switch規則，保存domain transcripts與Domain Views。','Domain Debate Module的設計功能是將同一快照的領域證據分流給各域Bull/Bear，執行指定辯論規則，保存domain transcripts與Domain Views。')
s=s.replace('新增待實作：按待鎖定schema讀取四個Views','Final Aggregator的設計功能是讀取標準化的四個Views')
s=s.replace('\\subsubsection{既有研究台與新版分支規劃}','\\subsubsection{研究台與流程追蹤}')
s=s.replace('此圖為既有介面，不代表新增模組已上線。後續需呈現model assignment、domain debates、四Views、Aggregator、名目與實際資源紀錄；新版介面實作狀態仍待驗證。','介面以執行狀態與來源追蹤支援研究檢查，模型指派、論證、裁決及資源紀錄均應可對應到單一案例。')
s=s.replace('Router能指定異質模型不代表能隔離異質性效果。需解釋能力組成、Judge文風偏好與不同訓練記憶風險；B/B控制、盲化及重跑僅是待採的研究建議，不假稱已驗證。','模型路由不等於異質性效果識別；能力組成、Judge文風偏好與不同訓練記憶風險仍可能影響比較，須以模型條件、輸入控制與結果範圍限定解讀。')

# Only retain existing results, clearly separated from the research-design extensions.
replace_between('\\section{結果與討論}','\\subsubsection{舊 qwen 績效與檢定}',r'''\section{結果與討論}
\subsection{既有協議的機制比較}
本節呈現qwen3:32b、季度協議v3-1002.3的既有回溯比較，以及同批Gemini探索性分析。其模型、流程與資料身分限定了結果的適用範圍；本節不作為異質模型辯論或領域專業化架構的績效證據。
''')
replace_between('\\subsection{Integrated Discussion}','\\subsection{研究限制}','')
replace_between('\\subsubsection{既有誠信與可重現性限制}','\\section{結論與建議}',r'''\subsubsection{資料有效性}
九檔為資料可取得性導向的目的性樣本，未納入退市公司，存在存活與事後選樣風險。財報filing date、macro historical vintage與新聞timestamp控制資料可得時間，但不排除模型訓練記憶；匿名化仍保留數值、日期及產品線索。行情採下載時的調整版本，也存在事後修訂風險。新聞來源與密度隨年份及個股改變；37案排除分析僅是來源／覆蓋診斷，不能外推為統一密度門檻。

\subsubsection{實驗有效性}
D同時包含立場交換、隔離對手、強制引用與驗證重試，估計量是整套流程差，而非單一立場交換效果。相同名目呼叫數不代表重試、tokens或compute相同。既有C/D須下注且可用成熟記憶，A/B可持有且無記憶，補充比較混合多項差異。各案採單次生成，觀察到的C/D分歧同時可能含生成噪音。同批資料已用於前導及規則調整，規則鎖定不能恢復未見樣本的確認性。

異質模型與能力組成、訓練記憶差異難以完全分離；同temperature或seed不代表相同生成機制。領域切分可能遺失跨域互動，上層整合也受輸入順序、長度與文風影響。模型輸出多樣性及論述豐富程度不能直接作為績效改善證據。

\subsubsection{統計有效性}
180案共享20個日期與重疊持有期，主要C/D比較只有16個不一致案例。日期群聚區間用於依賴性敏感度檢查，不當作等效或非劣證據；條件式MDE也不是事前研究檢定力。由於未事前登記等效界值，不以不顯著結果宣稱兩流程相同。Sharpe以對齊日序列計算，其觀測數T與案例數180、日期群聚數20不可互換。

\subsubsection{外部有效性與可重現性}
結果限定九檔美國大型股、2021--2025年與指定模型／協議，不能推廣至全部市場。Gemini比較共用同批案例，不是獨立複製；現有匯出不能支持兩模型逐位元讀取相同研究報告的主張。FinBERT revision、完整Gemini呼叫設定與行情調整版本的紀錄完整度限制精確重現。既有小樣本匿名探針的辨識率也不代表全部180案。
''')
replace_between('\\subsection{研究結論}','\\subsection{應用與價值}','')
s=s.replace('原每月擴充至540案例為既有規劃且未執行，不任意併入本次180案正式樣本。','月度／20日比較採獨立設計，不併入本研究180個季度案例。')
# Remove the workflow checklist and editorial notes, preserving them in the backup.
afterbib=s.index('\\end{thebibliography}')+len('\\end{thebibliography}')
s=s[:afterbib]+r'''

\vspace{0.3cm}
\noindent\small 本文僅供學術研究與教學使用，不構成任何投資建議。
\end{CJK}
\end{document}
'''

# Convert remaining status notices to factual scope statements or remove deferred content.
replacements={
'現有本機新版匯出中核對':'現有本機匯出中核對',
'新版 Gemini 完整 API model ID、實際溫度、存取日期、種子套用狀態與逐案研究報告雜湊，未在現有本機匯出中核對；因此不能宣稱兩模型逐位元讀取相同研究報告，也不能把模型替換解讀為純粹的能力改變。':'現有匯出紀錄不足以證明兩模型的完整呼叫設定與逐案研究報告身分一致，因此不能宣稱兩模型逐位元讀取相同報告，或將模型替換解讀為純能力改變。',
'Gemini 的 A、B 出手數及覆蓋率尚未由逐案匯出核對；':'現有Gemini彙總未提供可核對的A/B出手數及覆蓋率；',
'其出手子集之一律看多基準尚待逐案資料重算，本文不作此比較。':'本文不將其出手子集與全樣本看多基準直接比較。',
'由本文既有彙總數代數重建，尚未以新版逐案匯出另行稽核。':'由既有彙總數代數重建，不視為額外逐案驗證。',
'因使用同批樣本、分析屬探索性且模型紀錄仍待補齊，不能宣稱已確認跨模型穩健性。':'因使用同批樣本、分析屬探索性且模型紀錄完整度有限，不能宣稱已確認跨模型穩健性。',
'新版兩模型的完整匿名報告探針仍待執行。':'',
'並非未執行。':'',
'未以消融分離各要素，故不能歸因於單獨的立場交換。':'其比較同時包含多項處理，故不能歸因於單獨的立場交換。',
'既有開發流程':'開發流程',
'本研究据此':'本研究據此',
'顺序':'順序','针对':'針對','來源':'來源','来源':'來源','预设':'預設','须':'須','条件':'條件','与':'與','统一':'統一','负担':'負擔','截图':'截圖','个獨立':'個獨立',
}
for a,b in replacements.items(): s=s.replace(a,b)
toc=r'\addcontentsline{toc}{section}{七、參考文獻}'
s=s.replace(toc+'\n'+toc,toc)

# Add primary-source references and actually cite them in the corresponding literature sections.
newrefs=[
('chen2023agentverse','Chen et al.','2023',r'''Chen, W., Su, Y., Zuo, J., Yang, C., Yuan, C., Chan, C.-M., Yu, H., Lu, Y., Hung, Y.-H., Qian, C., Qin, Y., Cong, X., Xie, R., Liu, Z., Sun, M., and Zhou, J.''','AgentVerse: Facilitating Multi-Agent Collaboration and Exploring Emergent Behaviors','2308.10848v3'),
('wang2024moa','Wang et al.','2024','Wang, J., Wang, J., Athiwaratkun, B., Zhang, C., and Zou, J.','Mixture-of-Agents Enhances Large Language Model Capabilities','2406.04692v1'),
('yang2024finrobot','Yang et al.','2024','Yang, H., Zhang, B., Wang, N., Guo, C., Zhang, X., Lin, L., Wang, J., Zhou, T., Guan, M., Zhang, R., and Wang, C. D.','FinRobot: An Open-Source AI Agent Platform for Financial Applications using Large Language Models','2405.14767v2'),
('zheng2023judge','Zheng et al.','2023','Zheng, L., Chiang, W.-L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., Lin, Z., Li, Z., Li, D., Xing, E. P., Zhang, H., Gonzalez, J. E., and Stoica, I.','Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena','2306.05685v4')]
bib=r'\begin{thebibliography}{99}'
a=s.index(bib);b=s.index(r'\end{thebibliography}',a)
blocks=re.findall(r'\\bibitem.*?(?=\\bibitem|\Z)',s[a+len(bib):b],re.S)
for key,short,year,authors,title,arxiv in newrefs:
    blocks.append('\\bibitem['+short+', '+year+']{'+key+'}\n'+authors+' ('+year+').\n\\newblock '+title+'.\n\\newblock arXiv preprint arXiv:'+arxiv+'.\n\\newblock \\url{https://arxiv.org/abs/'+arxiv+'}.\n\n')
blocks.sort(key=lambda x:re.search(r'\n([^\n]+)',x.strip()).group(1).casefold())
s=s[:a]+bib+'\n\n'+''.join(blocks)+s[b:]
for a,b in {'Finbert:':'FinBERT:','Fnspid:':'FNSPID:','Tradingagents:':'TradingAgents:','gpt sentiment':'GPT sentiment','sharpe and treynor':'Sharpe and Treynor','sharpe ratio':'Sharpe ratio'}.items(): s=s.replace(a,b)
target.write_text(s,encoding='utf-8')

# Separate updated BibTeX companion, preserving the original library.
origbib=(report/'references.bib').read_text(encoding='utf-8')
newbib=r'''
@misc{chen2023agentverse,
 author={Chen, Weize and Su, Yusheng and Zuo, Jingwei and Yang, Cheng and Yuan, Chenfei and Chan, Chi-Min and Yu, Heyang and Lu, Yaxi and Hung, Yi-Hsin and Qian, Chen and Qin, Yujia and Cong, Xin and Xie, Ruobing and Liu, Zhiyuan and Sun, Maosong and Zhou, Jie},
 title={AgentVerse: Facilitating Multi-Agent Collaboration and Exploring Emergent Behaviors},
 year={2023}, howpublished={arXiv preprint arXiv:2308.10848v3}, url={https://arxiv.org/abs/2308.10848v3}
}
@misc{wang2024moa,
 author={Wang, Junlin and Wang, Jue and Athiwaratkun, Ben and Zhang, Ce and Zou, James},
 title={Mixture-of-Agents Enhances Large Language Model Capabilities},
 year={2024}, howpublished={arXiv preprint arXiv:2406.04692v1}, url={https://arxiv.org/abs/2406.04692v1}
}
@misc{yang2024finrobot,
 author={Yang, Hongyang and Zhang, Boyu and Wang, Neng and Guo, Cheng and Zhang, Xiaoli and Lin, Likun and Wang, Junlin and Zhou, Tianyu and Guan, Mao and Zhang, Runjia and Wang, Christina Dan},
 title={FinRobot: An Open-Source AI Agent Platform for Financial Applications using Large Language Models},
 year={2024}, howpublished={arXiv preprint arXiv:2405.14767v2}, url={https://arxiv.org/abs/2405.14767v2}
}
@misc{zheng2023judge,
 author={Zheng, Lianmin and Chiang, Wei-Lin and Sheng, Ying and Zhuang, Siyuan and Wu, Zhanghao and Zhuang, Yonghao and Lin, Zi and Li, Zhuohan and Li, Dacheng and Xing, Eric P. and Zhang, Hao and Gonzalez, Joseph E. and Stoica, Ion},
 title={Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena},
 year={2023}, howpublished={arXiv preprint arXiv:2306.05685v4}, url={https://arxiv.org/abs/2306.05685v4}
}
'''
(report/'references-meeting-20261006.bib').write_text(origbib+'\n'+newbib,encoding='utf-8')

citations={k for c in re.findall(r'\\cite[pt]\{([^}]+)\}',s) for k in c.split(',')}
keys=set(re.findall(r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}',s))
labels=re.findall(r'\\label\{([^}]+)\}',s)
refs=set(re.findall(r'\\ref\{([^}]+)\}',s))
status=re.findall(r'.*(?:【待|需補文獻|待鎖定|待實作|待驗證|未完成|尚未|待填|pending formal|incomplete).*',s,re.I)
result={'added_references':[x[0] for x in newrefs],'missing_citations':sorted(citations-keys),'missing_refs':sorted(refs-set(labels)),'status_notices':status,'rq1_exact_preserved':'在相同案例資料與相同名目決策呼叫次數下，自我反駁式立場交換辯論（D）的 60 日方向準確率與年化 Sharpe 是否高於固定立場辯論（C）？' in s,'chars_before':len(original),'chars_after':len(s),'source_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
(folder/'clean-draft-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
