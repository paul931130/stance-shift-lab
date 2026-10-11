from pathlib import Path
root = Path(__file__).resolve().parent
p = root / 'application.tex'
t = p.read_text(encoding='utf-8')
t = t.replace('進行事前登記之實驗', '進行規則鎖定後之回溯比較')
t = t.replace('In a preregistered experiment with', 'In a retrospective comparison under registered, locked rules with')
t = t.replace('Case analysis shows that self-rebuttal made the model weigh neglected counter-evidence, but in a mostly rising market this did not lead to more accurate decisions.', 'Selected cases describe different emphasis on counter-evidence, without establishing a causal mechanism. The sample had been used in prior runs; anonymization is incomplete and repeated-run variability was not measured. The results do not establish equivalence.')
t = t.replace('案例中可觀察到交換輪較強調反面證據、最終決策較常轉為看空，但整體而言未帶來更準確的決策。', '所選案例呈現不同的反面證據權衡，僅供描述。同批樣本曾用於前導試跑，匿名化不完全且未量測同案重跑變異；未達優越性判準不等於兩組等效。')
t = t.replace('四組的差異僅在決策方式。', '四組於研究報告鎖定後分流，下注限制與記憶權限亦依組別不同。')
t = t.replace('呼叫次數相同不代表 token 或運算量相同，', '此為名目呼叫數，D 的引用自身原文驗證可能另觸發重試；呼叫次數相同不代表實際重試次數、token 或運算量相同，')
t = t.replace('兩者皆顯著為正才判定', '沿用雙尾檢定，僅當兩端點差異皆為正且各自校正後 $p<0.05$ 才判定')
marker = r'\paragraph{評估方法。}'
pos = t.index(marker)
end = t.index('\n\n', pos)
t = t[:end] + r'''

日報酬先依每案進場開盤、每日收盤與出場開盤之部位權益計算，扣除進出場價差；同日期各案固定權重 1/180，持有與非交易期間為零。年化 Sharpe 為 $\sqrt{252}\bar r/s(r)$，標準差採 $T-1$ 分母，無風險基準明設為零。累積報酬為 $\prod_t(1+r_t)-1$，非平均 60 日案例報酬；最大回撤亦由此日序列計算，此低曝險配置僅供組間比較。方向正確依未扣成本的開盤價格漲跌判定，與淨報酬正負不同。Ledoit--Wolf 區塊長度 20 日、重抽樣 1,999 次、種子 905；qwen 基礎推理種子 905、溫度 0.2（投票 0.8），各呼叫實際種子另保存於稽核。
''' + t[end:]
t = t.replace('方向準確率 & 總報酬', '條件準確率 & 累積報酬')
t = t.replace('排除 37 個低新聞量案例', '排除 37 個新聞來源／覆蓋診斷案例')
t = t.replace('四組皆未勝過同期買進持有', '四組之 Sharpe 點估計均低於相同配置之買進持有參照（未作對基準之優越性檢定）')
t = t.replace('整体', '整體')
t = t.replace('整體正確 5 案、錯誤 11 案。', '就全部 16 案而言，D 正確 5 案、C 正確 11 案。')
t = t.replace('換言之，立場交換改變了辯論內容與部分決策，但未帶來更準確的結果。', '兩組的部分文字與決策不同，但未支持 D 較佳；不能將差異全歸因於交換立場。')
t = t.replace('在 16 個方向不同的案例中，\\grp{D} 有 12 案判斷賣出，', '在 16 個方向不同的案例中，\\grp{D} 有 12 案判斷賣出；')
t = t.replace('本研究以單一模型執行，結論是否適用於其他模型尚待檢驗。', '主要比較以 qwen3:32b 執行；Gemini 3 Flash 的同批探索性準確率比較亦未觀察到 D 改善，但不是獨立樣本複製。第六，九檔為資料可取得性導向之目的性樣本，不能排除存活與事後選樣偏誤。第七，主要比較僅有 16 個不一致案例，未做事前檢定力或同案不同種子重跑，故不能證明等效。第八，舊協議前導匿名辨識為 6/18，不能當作新版 180 案辨識率；新版模型汙染檢驗與消融仍待執行。')
t = t.replace('並於 180 個事前登記之季度案例中檢驗', '並於規則鎖定後的 180 個季度回溯案例中檢驗')
t = t.replace('結果顯示，自我反駁式立場交換未優於固定立場辯論', '結果未達優越性判準，不支持自我反駁式立場交換較佳，亦不證明其與固定立場辯論等效')
needle = r'\subsection{實驗設計}'
t = t.replace(needle, '九檔的選取以資料可取得性為主，非 2021 年成分股抽樣；協議記錄排除缺乏新聞覆蓋的 ASTS，並以 INTC 替換有早期新聞缺口的 LLY。原分析的 37 案新聞診斷集合包含 36 案僅有 API 標題與另列的 MCD 2023-12-31 案，不是统一則數門檻；逐案來源分類仍待新版快照核對。\n\n' .replace('统一', '統一') + needle)
p.write_text(t, encoding='utf-8')

p = root / 'stance-shift-ssrn.tex'
t = p.read_text(encoding='utf-8')
t = t.replace(r'\centering\small' + '\n' + r'\caption{主要 RQ1 主要結果', r'\centering\footnotesize' + '\n' + r'\caption{主要 RQ1 主要結果')
t = t.replace('迫使代理人檢驗自身論點之弱點，避免僅改寫對方說法', '要求代理人檢查自身論點；是否改善決策另以結果評估')
t = t.replace('四組等權重。', '每組各案例等權重。')
old = r'\grp{D}\ 立場交換辯論 & 100\% & 55.0\% & -- & 2.11\% & $-2.01\%$ & 0.54 \\'
t = t.replace(old, old + '\n' + r'一律看多（方向參照） & 100\% & 62.2\% & -- & -- & -- & -- \\')
old = '此案技術面強勁（近 20 日上漲 11.3\\%），但營收與淨利年減。\\grp{C} 之裁決者採納技術動能判斷買進；\\grp{D} 交換輪中原看多者改為看空，強調基本面衰退與 83.6\\% 之負債比，裁決者隨之判斷賣出。60 日後股價上漲 15.3\\%，\\grp{D} 錯誤。'
new = r'''此案技術面強勁（近 20 日上漲 11.3\%），但營收與淨利年減；兩組裁決摘要如表~\ref{tab:case2}。60 日後股價上漲 15.3\%，\grp{D} 錯誤。

\begin{table}[H]
\centering\small
\caption{案例二：AAPL 2023-03-31 的文字與裁決描述}
\label{tab:case2}
\begin{tabularx}{\textwidth}{@{}l l Y@{}}
\toprule
組別／輪次 & 立場或裁決 & 論點摘要 \\
\midrule
\grp{C} 裁決 & 買進 & 採納技術動能訊號。 \\
\grp{D} 第 2 輪 & 原看多者改看空 & 強調營收與淨利衰退及 83.6\% 的負債比。 \\
\grp{D} 裁決 & 賣出 & 論點偏重基本面衰退；實際 60 日股價上漲。 \\
\bottomrule
\end{tabularx}
\par\smallskip
\raggedright\footnotesize 與案例一同為事後選取之描述，不據此辨識因果機制；只呈現現有案例摘要，不補推未核對之輪次或預期報酬。
\end{table}'''
assert old in t
t = t.replace(old, new)
p.write_text(t, encoding='utf-8')
print('Synced application report and tightened main report tables.')
