from pathlib import Path
import re,json,hashlib
p=Path(__file__).resolve().parent
r=p.parents[1]
src=r/'application-meeting-20261006.tex'
s=src.read_text(encoding='utf-8')
for a,b in {'任务':'任務','预设':'預設','预先':'預先','归屬':'歸屬','自动':'自動','信息':'資訊','视为':'視為','样本':'樣本','独立':'獨立','比较':'比較','统计':'統計','冻結':'凍結','后續':'後續','报告':'報告','对照':'對照','效益':'效益','负担':'負擔','恢复':'恢復','确認':'確認','处理':'處理','日志':'紀錄','模型组':'模型組','另有':'另有','目前不採定':'目前尚未選定','说明':'說明','二元方向':'二元方向','20日期':'20個日期','估计':'估計'}.items(): s=s.replace(a,b)
if '\\addcontentsline{toc}{section}{七、參考文獻}' not in s:
    s=s.replace('\\renewcommand{\\refname}{七、參考文獻}','\\renewcommand{\\refname}{七、參考文獻}\n\\addcontentsline{toc}{section}{七、參考文獻}')
src.write_text(s,encoding='utf-8')
bibkeys=set(re.findall(r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}',s))
citations=set(k.strip() for c in re.findall(r'\\cite[pt]\{([^}]+)\}',s) for k in c.split(','))
labels=set(re.findall(r'\\label\{([^}]+)\}',s))
refs=set(re.findall(r'\\ref\{([^}]+)\}',s))
checks={'citation_count':len(citations),'bibliography_count':len(bibkeys),'missing_citations':sorted(citations-bibkeys),'missing_refs':sorted(refs-labels),'formal_pending_marker_count':s.count('【待實驗結果】'),'original_sources_unchanged':{},'compile_status':'built-in compiler failed: Unable to find standard directories for platform; no verified PDF'}
manifest=json.loads((p/'revision-manifest.json').read_text(encoding='utf-8'))
for fn,digest in manifest['sources'].items(): checks['original_sources_unchanged'][fn]=hashlib.sha256((r/fn).read_bytes()).hexdigest()==digest
manifest['output']=hashlib.sha256(src.read_bytes()).hexdigest()
(p/'revision-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

authors={}
for m in re.finditer(r'\\bibitem\[([^\]]+)\]\{([^}]+)\}',s):
    name=m.group(1).replace('~',' ').replace('\\protect','')
    chicago=re.search(r'\\citeauthoryear\{[^}]*\}\{([^}]*)\}\{([^}]*)\}',name)
    if chicago: name=chicago.group(1)+', '+chicago.group(2)
    authors[m.group(2)]=re.sub(r'\s+',' ',name)

def clean(t):
    t=re.sub(r'\\cite[pt]\{([^}]+)\}',lambda m:'（'+'；'.join(authors.get(k,k) for k in m.group(1).split(','))+'）',t)
    t=re.sub(r'\\(?:grp|textbf|texttt|textsf|emph|em)\{([^{}]*)\}',r'\1',t)
    t=re.sub(r'\\(?:label)\{[^}]*\}','',t)
    t=re.sub(r'\\ref\{([^}]+)\}',lambda m:'〔'+m.group(1)+'〕',t)
    t=re.sub(r'\\url\{([^}]+)\}',r'<\1>',t)
    t=t.replace('\\%','%').replace('\\_','_').replace('\\&','＆').replace('\\times','×').replace('\\ldots','…').replace('\\sqrt','√')
    t=re.sub(r'\\(?:noindent|footnotesize|small|normalsize|raggedright|centering|allowbreak|newblock|toprule|midrule|bottomrule)\b','',t)
    t=re.sub(r'\\(?:vspace|setstretch|enlargethispage)\*?\{[^}]*\}','',t)
    t=t.replace('\\par','').replace('~',' ')
    t=t.replace('\\quad',' ').replace('\\smallskip','').replace('\\baselineskip','').replace('\\noindent','')
    t=re.sub(r'\\em\b','',t).replace('\\/','').replace('pp.\\ ','pp. ').replace('\\ ',' ')
    return t.strip()

def table(m):
    block=re.sub(r'\\(?:grp|textbf|textsf|emph)\{([^{}]*)\}',r'\1',m.group(0))
    cap=re.search(r'\\caption\{([^}]+)\}',block)
    start=re.search(r'\\toprule',block)
    end=re.search(r'\\bottomrule',block)
    if not start or not end: return '\n```latex\n'+block+'\n```\n'
    segment=block[start.end():end.start()]
    rows=[]
    for line in segment.split('\\\\'):
        line=re.sub(r'\\(?:midrule|toprule)','',line).strip()
        if not line: continue
        line=re.sub(r'\\multicolumn\{\d+\}\{[^}]*\}\{([^}]*)\}',r'\1',line)
        cells=[clean(x).replace('\n',' ').replace('|','／') for x in re.split(r'(?<!\\)&',line)]
        rows.append(cells)
    if not rows: return block
    n=max(len(x) for x in rows)
    rows=[x+['']*(n-len(x)) for x in rows]
    txt='\n'+('**'+clean(cap.group(1))+'**\n\n' if cap else '')
    txt+='| '+' | '.join(rows[0])+' |\n| '+' | '.join(['---']*n)+' |\n'
    txt+=''.join('| '+' | '.join(row)+' |\n' for row in rows[1:])
    note=block[block.index('\\end{tabular'):] if '\\end{tabular' in block else ''
    note=re.sub(r'\\end\{(?:tabularx|tabular|table)\}','',note).replace('\\par\\smallskip','')
    note=clean(note)
    if note: txt+='\n'+note+'\n'
    return txt

start=s.index('本專題延續')
m=s[start:]
m=re.sub(r'\\begin\{table\}.*?\\end\{table\}',table,m,flags=re.S)
def figure(match):
    block=match.group(0)
    cap=re.search(r'\\caption\{([^}]+)\}',block)
    if 'tikzpicture' in block:
        return '\n```mermaid\nflowchart TD\n D[Data與Immutable Snapshot] --> R[四類Research Agents與證據登錄]\n R --> Q1[RQ1 Homogeneous C/D]\n R --> Q2[RQ2 Heterogeneous C/D AB/BA]\n R --> Q3[RQ3 Generalist 或四Domain Debates]\n Q1 --> J[固定Judge]\n Q2 --> J\n Q3 --> A[Final Judge / Aggregator]\n J --> G[既有Gatekeeper]\n A --> G\n G --> B[Backtest與統計]\n```\n\n'+(clean(cap.group(1)) if cap else '')+'\n'
    image=r/'figures'/'ui-pipeline.png'
    return '\n![既有研究台]('+image.as_posix()+')\n\n'+(clean(cap.group(1)) if cap else '')+'\n'
m=re.sub(r'\\begin\{figure\}.*?\\end\{figure\}',figure,m,flags=re.S)
# Convert bibliography separately and preserve every original entry.
bb=re.search(r'\\begin\{thebibliography\}.*?\\end\{thebibliography\}',m,re.S)
if bb:
    refs_md=[]
    for entry in re.split(r'\\bibitem(?:\[[^\]]*\])?\{[^}]+\}',bb.group(0))[1:]:
        entry=entry.replace('\\end{thebibliography}','')
        refs_md.append('- '+re.sub(r'\s+',' ',clean(entry)).replace('{','').replace('}',''))
    m=m[:bb.start()]+'\n# 七、參考文獻\n\n'+'\n\n'.join(refs_md)+'\n'+m[bb.end():]
m=re.sub(r'\\section\*?\{([^{}]*)\}',r'\n# \1\n',m)
m=re.sub(r'\\subsection\*?\{([^{}]*)\}',r'\n## \1\n',m)
m=re.sub(r'\\subsubsection\*?\{([^{}]*)\}',r'\n### \1\n',m)
m=re.sub(r'\\paragraph\{([^{}]*)\}',r'\n**\1** ',m)
m=re.sub(r'\\begin\{center\}.*?\\end\{center\}','\n# Abstract\n',m,flags=re.S)
m=re.sub(r'\\(?:addcontentsline|renewcommand)\{[^}]*\}\{[^}]*\}(?:\{[^}]*\})?','',m)
m=re.sub(r'\\setcounter\{[^}]*\}\{[^}]*\}','',m)
m=re.sub(r'\\begin\{(?:itemize|enumerate)\}(?:\[[^\]]*\])?','',m)
m=m.replace('\\end{itemize}','').replace('\\end{enumerate}','')
m=m.replace('\\item ','\n- ')
m=m.replace('\\begin{quote}','\n> ').replace('\\end{quote}','\n')
m=m.replace('\\clearpage','').replace('\\tableofcontents','')
m=re.sub(r'\\pagenumbering\{[^}]*\}','',m)
m=m.replace('\\end{CJK}','').replace('\\end{document}','')
m=clean(m)
m=re.sub(r'\$[^$\n]*\$',lambda x:x.group(0).replace('%',r'\%'),m)
m=re.sub(r'\n{3,}','\n\n',m)
front='# Part D 完整修改稿\n\n多代理人立場交換辯論機制應用於投資決策：模型異質性與領域專業化之延伸\n\n本稿以原報告逐章保留與修訂，三題新版正式結果均待實驗；舊protocol數字僅列prior result。排版母稿為 application-meeting-20261006.tex。\n\n# 中文摘要\n\n'
(p/'Part-D-完整修改稿.md').write_text(front+m+'\n',encoding='utf-8')
(p/'validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False,indent=2))
