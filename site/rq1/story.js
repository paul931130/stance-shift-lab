'use strict';
const $$ = (q) => [...document.querySelectorAll(q)];
$$('[data-guess]').forEach(button => button.addEventListener('click', () => {
  $$('[data-guess]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  document.querySelector('#guess-note').textContent = `你選了 ${button.dataset.guess}。保留這個直覺；接下來一起看研究如何比較，不替這個選擇評分。`;
}));
document.querySelector('#reveal').addEventListener('click', event => {
  const open = event.currentTarget.getAttribute('aria-expanded') === 'true';
  event.currentTarget.setAttribute('aria-expanded', String(!open));
  document.querySelector('#research-question').hidden = open;
  event.currentTarget.textContent = open ? '揭開研究問題' : '收起研究問題';
});
document.querySelector('#reveal-results').addEventListener('click',event=>{document.querySelector('#results-body').hidden=false;event.currentTarget.setAttribute('aria-expanded','true');event.currentTarget.textContent='結果已揭曉 ↓';document.querySelector('#results-body').scrollIntoView({block:'start'});});
const rounds = [
  ['第 1 輪：建立原始立場', '看多與看空代理人各自提出論點、引用證據。此時先把正反兩邊的理由說清楚。'],
  ['第 2 輪：換邊，只反駁自己', '原本看多的改看空，原本看空的改看多。這一輪看不到對手，只能看自己的第一輪；必須引用自己的原文，再提出反駁。另有引用驗證與重試流程。'],
  ['第 3 輪：回到原立場，整合', '雙方換回原立場，整理前兩輪的主張與反駁，說明仍不確定的地方。模型本身沒有在中途更換。'],
  ['最後：裁決者核對證據', '裁決者讀取完整辯論與報告，逐項核對證據，選擇買進或賣出。三輪各兩次，加上裁決一次，共 7 次預定決策呼叫。']
];
let round = 0;
function renderRound(index) {
  round = index;
  $$('[data-round]').forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.round) === index)));
  const container = document.querySelector('#round-content');
  container.replaceChildren();
  const title = document.createElement('h4'); title.textContent = rounds[index][0];
  const text = document.createElement('p'); text.textContent = rounds[index][1];
  container.append(title, text);
  document.querySelector('#round-next').textContent = index === 3 ? '再看一次第 1 輪 ↺' : '下一步 →';
}
$$('[data-round]').forEach(button => button.addEventListener('click', () => renderRound(Number(button.dataset.round))));
document.querySelector('#round-next').addEventListener('click', () => renderRound((round + 1) % 4));
renderRound(0);
const metrics = {
  accuracy: {title:'方向準確率 · 180 個季度案例', values:[58.3,55.0,62.2], labels:['C 固定立場','D 立場交換','一律看多'], max:100, unit:'%', note:'C／D 主要比較：Holm 校正後 p = 0.42。D−C = −3.3 個百分點。條紋列為事後探索性基準，不屬主要比較。準確率橫軸從 0% 到 100%。'},
  sharpe: {title:'年化 Sharpe · 180 案形成的 1,219 個交易日日序列', values:[0.59,0.54,1.01], labels:['C 固定立場','D 立場交換','買進持有'], max:1.2, unit:'', note:'C／D 主要比較：Holm 校正後 p = 0.80。D−C = −0.05。條紋列為同配置買進持有參照，報告未檢定其 Sharpe 差異。圖軸從 0 到 1.2。'}
};
function renderMetric(key) {
  const metric = metrics[key];
  $$('[data-metric]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.metric === key)));
  document.querySelector('#chart-title').textContent = metric.title;
  document.querySelector('#test-note').textContent = metric.note;
  const chart = document.querySelector('#chart'); chart.replaceChildren();
  metric.values.forEach((value,index) => {
    const row = document.createElement('div'); row.className = 'bar-row';
    const label = document.createElement('span'); label.textContent = metric.labels[index];
    const track = document.createElement('div'); track.className = 'track'; track.setAttribute('aria-hidden','true');
    const bar = document.createElement('div'); bar.className = `bar ${['c','d','ref'][index]}`; bar.style.width = `${value / metric.max * 100}%`; track.append(bar);
    const number = document.createElement('b'); number.textContent = `${value.toFixed(key === 'accuracy' ? 1 : 2)}${metric.unit}`;
    row.append(label,track,number); chart.append(row);
  });
}
$$('[data-metric]').forEach(button => button.addEventListener('click', () => renderMetric(button.dataset.metric)));
renderMetric('accuracy');
const cases = {
  INTC:{date:'2024-03-31',scene:'新聞情緒偏正面，近 20 日報酬為正；營收、淨利與營業現金流卻比去年同期大幅衰退。',c:'看多方持續強調正面情緒與短期動能，看空方反覆指出財報衰退。裁決採納短期動能，決定買進。',d:'交換輪引用並反駁自己原本的看多理由，強調基本面衰退抵銷短期情緒。裁決認為基本面惡化更重要，決定賣出。',result:'標的 60 個交易日價格變動 −30.5%（非策略報酬）：C 方向錯誤，D 方向正確。'},
  AAPL:{date:'2023-03-31',scene:'近 20 日上漲 11.3%，技術動能強；營收與淨利卻比去年下降。',c:'採納技術動能的判斷，決定買進。',d:'交換輪再次強調基本面衰退，裁決者因此判斷賣出。',result:'標的 60 個交易日價格變動 +15.3%（非策略報酬）：C 方向正確，D 方向錯誤。'}
};
function paragraph(text) {const element=document.createElement('p');element.textContent=text;return element;}
function renderCase(key) {
  $$('[data-case]').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.case===key)));
  const data=cases[key];const container=document.querySelector('#case-content');container.replaceChildren();
  const header=document.createElement('div');header.className='case-header';const heading=document.createElement('h3');heading.textContent=`${key} · ${data.date}`;const badge=document.createElement('span');badge.className='badge subtle';badge.textContent='事後挑選的說明案例';header.append(heading,badge);
  const comparison=document.createElement('div');comparison.className='case-arguments';
  [['C · 固定立場',data.c],['D · 立場交換',data.d]].forEach(([label,text])=>{const column=document.createElement('div');const title=document.createElement('h4');title.textContent=label;column.append(title,paragraph(text));comparison.append(column);});
  const outcome=paragraph(data.result);outcome.className='outcome';
  container.append(header,paragraph(data.scene),comparison,outcome,paragraph('這裡只描述兩組做了什麼，以及後來發生什麼；不能據此認定立場交換造成結果。未列出的逐輪細節：報告未提供。'));
}
$$('[data-case]').forEach(button=>button.addEventListener('click',()=>renderCase(button.dataset.case)));
renderCase('INTC');
const progressLinks=$$('nav a');
if ('IntersectionObserver' in window) {
  const observer=new IntersectionObserver(entries=>{entries.forEach(entry=>{if(entry.isIntersecting){progressLinks.forEach(link=>{if(link.hash===`#${entry.target.id}`)link.setAttribute('aria-current','step');else link.removeAttribute('aria-current');});}});},{rootMargin:'-15% 0px -60% 0px',threshold:0});
  $$('main > section').forEach(section=>observer.observe(section));
}
// Optional same-site frozen export. Failure keeps the two report examples available.
fetch('./story-cases.json').then(response=>{if(!response.ok)throw new Error('No frozen export');return response.json();}).then(payload=>{
  const rows=Array.isArray(payload)?payload:payload.cases;
  if(!Array.isArray(rows)||!rows.length)return;
  const valid=rows.filter(row=>typeof row.ticker==='string'&&typeof row.date==='string'&&typeof row.cCorrect==='boolean'&&typeof row.dCorrect==='boolean'&&row.cCorrect!==row.dCorrect).map(row=>({...row,winner:row.cCorrect?'C':'D',c_decision:row.c==='Buy'?'買進':row.c==='Sell'?'賣出':'報告未提供',d_decision:row.d==='Buy'?'買進':row.d==='Sell'?'賣出':'報告未提供',return_label:Number.isFinite(row.realizedMovePct)?`${row.realizedMovePct>=0?'+':''}${row.realizedMovePct.toFixed(1)}%`:'報告未提供'}));
  if(!valid.length)return;
  const stock=document.querySelector('#stock-filter');
  [...new Set(valid.map(row=>row.ticker))].sort().forEach(ticker=>{const option=document.createElement('option');option.value=ticker;option.textContent=ticker;stock.append(option);});
  const winner=document.querySelector('#winner-filter');
  function filter(){const filtered=valid.filter(row=>(stock.value==='all'||row.ticker===stock.value)&&(winner.value==='all'||row.winner===winner.value));const list=document.querySelector('#case-list');list.replaceChildren();document.querySelector('#case-count').textContent=`顯示 ${filtered.length} / ${valid.length} 個凍結分歧案例`;filtered.forEach(row=>{const card=document.createElement('article');card.className='case-item';const title=document.createElement('h4');title.textContent=`${row.ticker} · ${row.date}`;card.append(title,paragraph(`方向正確：${row.winner}`),paragraph(`C：${row.c_decision??'報告未提供'}；D：${row.d_decision??'報告未提供'}`),paragraph(`60 日標的價格變動（非策略報酬）：${row.return_label??'報告未提供'}`),paragraph(cases[row.ticker]?.date===row.date?'論點摘要見上方說明案例。':'論點摘要：報告未提供。'));list.append(card);});}
  stock.addEventListener('change',filter);winner.addEventListener('change',filter);
  document.querySelector('#frozen-source').textContent='資料來源：專案凍結逐案資料的靜態匯出。正誤沿用凍結 correct 欄位；價格變動不是策略淨報酬。只呈現 C／D 方向分歧，篩選結果不能作因果推論。';
  document.querySelector('#frozen-explorer').hidden=false;filter();
}).catch(()=>{});
