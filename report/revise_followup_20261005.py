"""Apply the bounded follow-up review; preserve the previous deliverables."""
from pathlib import Path
from math import comb
import json
import re
import shutil

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'revisions' / '2026-10-05-followup'
BEFORE = OUT / 'before'
BEFORE.mkdir(parents=True, exist_ok=True)
for name in ('stance-shift-ssrn.tex', 'application.tex', 'references.bib',
             'stance-shift-ssrn.pdf', 'application.pdf'):
    destination = BEFORE / name
    if destination.exists():
        if destination.read_bytes() != (ROOT / name).read_bytes():
            raise RuntimeError(f'Backup differs from current source: {destination}')
    else:
        shutil.copy2(ROOT / name, destination)

def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected exactly one match: {old[:100]!r}')
    return text.replace(old, new)

main = (ROOT / 'stance-shift-ssrn.tex').read_text(encoding='utf-8')
app = (ROOT / 'application.tex').read_text(encoding='utf-8')
main = replace(main, r'\paragraph{立場交換被提出以對抗固守立場，但尚未在投資情境檢驗。}',
               r'\paragraph{立場交換的投資績效證據仍須限定搜尋範圍。}')
gap = '截至 2026 年 10 月 5 日，在本章所列文獻及本次核對的 arXiv、OpenReview 與 ACL Anthology 資料範圍內，未見同時以相同案例資訊、對齊名目決策呼叫次數及可稽核時間邊界，直接檢驗自我反駁式立場交換之投資績效的研究。此為本研究搜尋範圍與日期內的觀察，並非系統性回顧或首次研究的主張。'
main = replace(main, '這些研究皆屬問答、事實查核或偏誤緩解，並非投資決策，這些結果尚不足以說明，',
               '上述角色交換研究屬問答、事實查核或偏誤緩解。' + gap + '這些結果尚不足以說明，')
main = replace(main, '此處的一致只指差異方向，不代表效果相等或獨立複製。',
               r'令 $\Delta_{\mathrm{acc}}^{(m)}=\mathrm{Acc}_{D}^{(m)}-\mathrm{Acc}_{C}^{(m)}$，一致定義為兩模型之差異同號；零差異另列為無方向。此判準不要求最佳組別相同，亦不代表效果相等、模型與機制無交互作用或獨立複製。')
main = replace(main, r'\noindent \grp{D} 同時包含立場互換、隔離對手與強制引用自身原主張，故比較對象為整套自我反駁流程。尚未以消融區分個別要素，亦未排除驗證重試及隨機生成對決策的影響。',
               r'\noindent 本研究的比較量為複合流程之效果差（composite-protocol estimand）：在鎖定案例、模型與執行規則下，估計 $(\mathrm{Acc}_D-\mathrm{Acc}_C, SR_D-SR_C)$。\grp{D} 同時包含立場互換、交換輪隔離對手與強制引用自身原主張，亦承擔相應驗證與重試；故此比較量描述整套流程差異。尚未以消融區分個別要素，亦未排除隨機生成影響，不能將差異歸因於單獨的立場交換。')
main = replace(main, r' r_{g,t}=\frac{1}{180}\sum_{i=1}^{180}r_{i,g,t},\qquad',
               r' r_{g,t}=\frac{1}{n_{\mathrm{case}}}\sum_{i=1}^{n_{\mathrm{case}}}r_{i,g,t},\qquad')
main = replace(main, '日期集合為全部案例持有期間內有價格紀錄之交易日聯集；持有期可重疊。',
               r'案例數為 $n_{\mathrm{case}}=180$，分析日群聚數為 20；$T$ 則為上述對齊日報酬面板的交易日筆數，三者不能互換。日期集合為全部案例持有期間內有價格紀錄之交易日聯集；持有期可重疊。本文尚未以新版日面板核對 $T$ 的實際值，不將 180 案視為 Sharpe 的 180 筆日觀測。')
main = replace(main, 'Sharpe 差以同日期的日序列配對。',
               r'Sharpe 差以同日期的日序列配對，原面板長度為 $T$，程式每次重抽樣長度為 $T^*=20\lfloor T/20\rfloor$；$T$ 與 $T^*$ 的實際值均尚未核對。')
equivalence = r'\paragraph{等效與非劣性界線。} 未達優越性判準不等於等效或非劣。這兩類主張須事先界定有實務意義的界值 $\delta_{\mathrm{acc}}$（百分點）與 $\delta_{SR}$，再以適當信賴區間／檢定評估差異是否落在等效範圍，或是否排除超過界值的劣勢。本研究未登記這些界值，故僅報告既有 95\% 區間，不事後選擇界值宣稱等效或非劣；例如準確率區間 $[-7.2,+0.6]$ 百分點不能排除 7.2 百分點的劣勢，Sharpe 區間 $[-0.47,+0.36]$ 亦仍寬。'
main = replace(main, r'\paragraph{決策分布與文字品質。}', equivalence + '\n\n' + r'\paragraph{決策分布與文字品質。}')
main = replace(main, r'此僅為離散拒絕門檻診斷，不是具 80\% 檢定力的 MDE；日期依賴與雙端點門檻使規劃更複雜。',
               r'此為離散拒絕門檻，並非 80\% 檢定力的最小可偵測效果（MDE）。另作條件式敏感度診斷：固定不一致數 $K=16$、假設案例獨立，令其中 \grp{D} 單獨正確的機率為 $q>0.5$，則 $X\sim\mathrm{Binomial}(16,q)$，雙尾 $\alpha=0.05$ 的檢定力為 $\Pr_q(X\leq3)+\Pr_q(X\geq13)$。達 80\% 檢定力需 $q\approx0.853$，對應期望準確率差 $(16/180)(2q-1)\approx6.3$ 百分點。這是依觀察到的分歧數設定之條件式 MDE，僅適用單一準確率端點、未納入日期依賴及 Holm／Sharpe 聯合門檻，不是事前或整體研究的 MDE。')
# Find the original architecture caption rather than assuming its previous wording.
captions = re.findall(r'\\caption\{研究流程[^\n]*', main)
assert len(captions) == 1, captions
main = replace(main, captions[0], r'\caption{研究架構。四組讀取同一份鎖定研究報告；決策流程、可見歷史與溫度設定亦不同。\grp{C}、\grp{D} 可用已到期案例記憶，\grp{D} 交換輪只見自身第一輪論述；\grp{A}、\grp{B} 無此記憶。qwen 的 \grp{B} 溫度為 0.8，其餘為 0.2；\grp{B}、\grp{C}、\grp{D} 各有七次名目決策呼叫。}')

app = replace(app, '但尚未在投資決策中檢驗。', '。' + gap)
app = replace(app, r'\caption{研究架構。四組決策機制讀取同一份鎖定之研究報告，差異僅在決策方式。}',
              r'\caption{研究架構。四組讀取同一份鎖定報告，但可見歷史、記憶與溫度亦不同：\grp{C}、\grp{D} 可用已到期案例記憶，\grp{D} 交換輪只見自身原論述，\grp{A}、\grp{B} 無此記憶；qwen 的 \grp{B} 溫度 0.8，其餘 0.2。}')
app = replace(app, r'\paragraph{立場交換辯論。}',
              r'\paragraph{比較量。} 本專題估計整套 \grp{D} 對 \grp{C} 的複合流程效果差（composite-protocol estimand），包含立場交換、交換輪隔離對手、強制引用與相應驗證／重試。未以消融分離各要素，故不能歸因於單獨的立場交換。' + '\n\n' + r'\paragraph{立場交換辯論。}')
app = replace(app, '標準差採 $T-1$ 分母，',
              r'其中案例数 $n_{\mathrm{case}}=180$，分析日群聚數為 20，$T$ 為對齊日面板的交易日筆數（实际值尚未核對），不可互換；標準差採 $T-1$ 分母，'.replace('数', '數').replace('实际', '實際'))
app = replace(app, '區塊長度 20 日、重抽樣 1,999 次、種子 905；',
              r'區塊長度 20 日、每次重抽樣長度 $20\lfloor T/20\rfloor$、重抽樣 1,999 次、種子 905；')
app = replace(app, r'以日期為群聚之準確率差 95\% 信賴區間為 $[-7.2, +0.6]$ 個百分點；',
              r'以日期為群聚之準確率差 95\% 信賴區間為 $[-7.2, +0.6]$ 個百分點，Sharpe 差區間為 $[-0.47,+0.36]$；')
app = replace(app, r'\paragraph{決策分布。}',
              r'\paragraph{檢定力與等效界線。} 未事前訂定等效／非劣性界值，故不能由未顯著宣稱兩組相同或非劣。若固定觀察到的 16 個不一致案例、暫假設案例獨立，以單一準確率端點之雙尾 $\alpha=0.05$ 精確檢定估算，80\% 檢定力所需之期望差約為 6.3 百分點；此條件式 MDE 未納入日期依賴及 Holm／Sharpe 聯合門檻，也不是事前檢定力規劃。' + '\n\n' + r'\paragraph{決策分布。}')
app = replace(app, '兩項設計，本研究未區分兩者各自的貢獻。', '及強制引用、驗證／重試等設計，本研究未區分各要素的貢獻。')
# Make the abbreviated report's question order explicit as well.
app = replace(app, r'\noindent 並以單次判斷與獨立投票作為對照，檢驗辯論的優勢是否僅來自「多想幾次」。',
              r'\noindent 上述為 RQ1，单次判斷與獨立投票作補充對照。RQ2 為同批 Gemini 3 Flash 的探索性跨模型比較：一致定義為 $\Delta_{\mathrm{acc}}^{(m)}=\mathrm{Acc}_D^{(m)}-\mathrm{Acc}_C^{(m)}$ 在兩模型同號；零差另列，不要求最佳組相同，亦未檢定模型與機制交互作用。RQ3 為月度設計，尚未執行，列為後續研究。'.replace('单', '單'))

bib = (ROOT / 'references.bib').read_text(encoding='utf-8')
count = 0
def fix_preprint(match):
    global count
    entry = match.group(0)
    arxiv = re.search(r'journal\s*=\s*\{arXiv preprint arXiv:([0-9.]+)\}', entry)
    if not arxiv:
        return entry
    count += 1
    aid = arxiv.group(1)
    entry = entry.replace('@article{', '@misc{', 1)
    entry = re.sub(r'journal\s*=\s*\{arXiv preprint arXiv:[0-9.]+\}',
                   lambda _: 'howpublished = {arXiv preprint arXiv:' + aid + '}', entry)
    version = 'v1' if aid in ('2305.19118', '2603.28488', '2602.14233') else ''
    entry = entry.rstrip()[:-1].rstrip()
    entry += ',\n  doi = {10.48550/arXiv.' + aid + '},\n'
    entry += '  url = {https://arxiv.org/abs/' + aid + version + '},\n'
    entry += '  note = {\\url{https://doi.org/10.48550/arXiv.' + aid + '}}\n}'
    return entry
bib = re.sub(r'@article\{.*?\n\}', fix_preprint, bib, flags=re.S)
assert count == 13, count

for name, text in (('stance-shift-ssrn.tex', main), ('application.tex', app), ('references.bib', bib)):
    (ROOT / name).write_text(text, encoding='utf-8', newline='\n')

def power(q):
    return sum(comb(16, j) * q**j * (1-q)**(16-j) for j in (*range(4), *range(13, 17)))
low, high = 0.5, 1.0
for _ in range(100):
    mid = (low + high) / 2
    if power(mid) < 0.8:
        low = mid
    else:
        high = mid
q = (low + high) / 2
diagnosis = {'K': 16, 'n_case': 180, 'alpha': .05, 'target_power': .8,
             'q': q, 'achieved_power': power(q), 'expected_difference_pp': 100*(16/180)*(2*q-1),
             'reject_X': list(range(4)) + list(range(13, 17)),
             'assumptions': 'Fixed observed K, independent cases, single accuracy endpoint; excludes clustering and joint/Holm rule.',
             'preregistered_design_power': False}
(OUT / 'conditional-mde.json').write_text(json.dumps(diagnosis, indent=2), encoding='utf-8')
print(json.dumps({'edited': 3, 'preprints_fixed': count, 'conditional_mde_pp': diagnosis['expected_difference_pp']}))
