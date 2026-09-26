// Step 1 · data preparation: case readiness, collecting a dataset snapshot,
// importing one, and the upstream half of the flow map.
import { $, escape, formatStamp, notify, datasetCut, COLLECTION_DOMAINS, sleep } from './ui.js';
import { state, on, selectedDataset } from './store.js';
import { api, task } from './api.js';
import { flow } from './flow.js';
import { setTab } from './nav.js';
import { resetTerminal, terminalLine } from './terminal.js';
import { refreshDatasets, selectDataset } from './experiment-panel.js';

const DOMAIN_SUBS = {technical: '技術資料', fundamental: '基本面資料', sentiment: '情緒資料', macro: '總經資料'};

function domainReady(dataset, domain) {
  const count = dataset?.coverage?.domains?.[domain] || 0;
  return {count, ok: domain === 'technical' ? count >= 61 : count > 0};
}

// Upstream half of the map: sources, data agents and the snapshot node.
function renderCollectionFlow(dataset, phase) {
  const update = {};
  for (const domain of COLLECTION_DOMAINS) {
    const {count, ok} = domainReady(dataset, domain);
    update[`da-${domain}`] = phase === 'running' ? {status: 'active', sub: '蒐集中…'}
      : dataset ? {status: ok ? 'done' : 'warn', sub: ok ? `${count} 筆` : '資料缺口'}
      : {status: 'idle', sub: DOMAIN_SUBS[domain]};
    if (phase === 'running') update[`src-${domain}`] = 'active';
    else if (flow.get(`src-${domain}`) === 'active') update[`src-${domain}`] = 'ready';
  }
  update.snapshot = phase === 'running' ? {status: 'active', sub: '等待四域寫入'}
    : dataset ? {status: 'done', sub: `${dataset.ticker} v${dataset.version} · ${dataset.evidence_count} 筆`}
    : state.selectedJob ? undefined : {status: 'idle', sub: '不可變 dataset'};
  flow.setMany(update);
  flow.metric('evidence', dataset ? dataset.evidence_count : '—');
  if (phase === 'running') flow.caption('資料 Agent 正在從四個來源並行蒐集證據，寫入不可變快照…');
  else if (state.selectedJob) return;
  else if (dataset) flow.caption(`快照 ${dataset.ticker} v${dataset.version}（研究日 ${datasetCut(dataset) || '未記錄'}）已就緒，可流向 A/B/C/D 實驗。`);
  else flow.caption('選擇股票與研究分析日，啟動資料 Agent 讓資料開始流動。');
}

export function renderCollectionAgents(dataset = null, phase = 'idle') {
  renderCollectionFlow(dataset, phase);
  let complete = 0, gaps = 0;
  for (const domain of COLLECTION_DOMAINS) {
    const {ok} = domainReady(dataset, domain);
    if (ok) complete++; else if (dataset) gaps++;
  }
  const readiness = $('data-readiness');
  if (phase === 'running') readiness.textContent = '四個資料 Agent 已啟動；技術、基本面與總經來源正在並行處理，情緒 Agent 同時檢查可用摘要。';
  else if (!dataset) readiness.textContent = '選擇股票與研究分析日後，讓四個 Agent 開始蒐集與驗證資料。';
  else if (gaps === 0) {
    const quality = dataset.coverage?.sentiment_quality || {}, pending = [];
    if (!dataset.coverage?.fundamental_quality?.passes_quality_gate) pending.push('SEC 基本面缺少可比較期間');
    if (quality.items > 0 && !quality.passes_quality_gate) pending.push('新聞目標相關性未通過');
    if (quality.items > 0 && !quality.finbert_complete) pending.push(`FinBERT ${quality.finbert_scored || 0}/${quality.items}`);
    if (!dataset.coverage?.backtest_ready) pending.push('60 日後續行情不足');
    readiness.textContent = pending.length
      ? `四域證據完整；正式主實驗前仍需處理：${pending.join('、')}。`
      : '四域證據、新聞品質、FinBERT 與 60 日回測行情均已驗證，可啟動 A/B/C/D 四組實驗。';
  } else readiness.textContent = `資料結構與行情已驗證；${complete}/4 個領域就緒、${gaps} 個領域有缺口。可直接作為缺資料對照，系統會保留缺口標記並依你選的策略處理決策。`;
}

export async function refreshReadiness() {
  const r = await api('/api/readiness');
  const done = r.evidence_complete_cases ?? r.complete_cases, formal = r.formal_experiment_ready_cases ?? 0, total = r.target_cases;
  const ratio = total ? Math.round((formal / total) * 100) : 0;
  $('study-readiness').innerHTML = `<div class="readiness-meter"><strong>目前可執行 ${formal}/${total} 個正式案例</strong><span>四域完整 ${done} · 60 日行情完整 ${r.backtest_ready_cases}</span></div><div class="meter" role="img" aria-label="正式案例完成度 ${ratio}%"><i></i></div>`;
  const bar = $('study-readiness').querySelector('.meter i');
  requestAnimationFrame(() => { bar.style.width = `${ratio}%`; });
  const gaps = await api('/api/readiness/gaps');
  const rows = (gaps.gap_cases || []).map(row => `<tr><td>${escape(row.ticker)}</td><td>${escape(row.analysis_date)}</td><td>${escape(row.status)}</td><td>${escape((row.deficits || []).join('、'))}</td><td><code>${escape(row.collect_command)}</code></td></tr>`).join('');
  $('gap-inventory-body').innerHTML = rows
    ? `<p class="hint">共 ${gaps.gap_count} 個缺口。先補「dataset」案例，再處理新聞品質或 SEC 可比較性。</p><div class="table-wrap gap-table"><table><thead><tr><th>股票</th><th>分析日</th><th>狀態</th><th>缺少項目</th><th>終端補資料指令</th></tr></thead><tbody>${rows}</tbody></table></div>`
    : '<p class="hint">全部研究案例均已達正式主實驗門檻。</p>';
}

function renderDatasetPreviewList() {
  const search = ($('dataset-search')?.value || '').trim().toLowerCase();
  const rows = state.datasetRows, filtered = rows.filter(d => !search || d.ticker.toLowerCase().includes(search));
  if (!rows.length) { $('datasets').innerHTML = ''; return; }
  $('datasets').innerHTML = filtered.length
    ? filtered.slice(0, 5).map(d => `<div><span class="version">v${d.version}</span><strong>${escape(d.ticker)} · ${d.kind === 'synthetic' ? '合成測試' : '歷史資料'}</strong><br>研究分析日 ${escape(datasetCut(d) || '未記錄')}<br>未來行情終點 ${escape(d.price_end)}（只供回測）<br>${d.price_count} 個交易日 · ${d.evidence_count} 筆證據 · 建立 ${escape(formatStamp(d.created_at))}<br><code title="完整資料集 ID">ID ${escape(d.id)}</code><br>${escape(d.source)}</div>`).join('')
    : `<p class="hint">沒有符合條件的資料集（共 ${rows.length} 筆）。</p>`;
}

const AGENT_CODES = {technical: 'TECH', fundamental: 'FUND', sentiment: 'SENT', macro: 'MACRO'};
const agentLine = (domain, item) => terminalLine(AGENT_CODES[domain], `${item.status.toUpperCase()} · ${item.records} records · ${item.message}`, item.status === 'complete' ? 'ok' : 'warn');

// Light up each data agent on the map the moment the server reports it.
function showAgentProgress(agents) {
  const update = {};
  for (const [domain, item] of Object.entries(agents)) {
    const ok = item.status === 'complete';
    update[`da-${domain}`] = {status: ok ? 'done' : 'warn', sub: ok ? `${item.records} 筆` : '資料缺口'};
    update[`src-${domain}`] = ok ? 'ready' : 'warn';
  }
  flow.setMany(update);
}

// Collection can take minutes (SEC, news, FinBERT), so it runs as a server
// task and the page polls it rather than holding one long request open.
async function runCollectionTask(payload) {
  let task = await api('/api/collections', payload);
  const reported = new Set();
  let finbertAnnounced = false;
  while (true) {
    for (const [domain, item] of Object.entries(task.agents || {})) {
      if (reported.has(domain)) continue;
      reported.add(domain);
      agentLine(domain, item);
    }
    showAgentProgress(task.agents || {});
    if (task.stage === 'finbert' && !finbertAnnounced) {
      finbertAnnounced = true;
      terminalLine('SENT', '本機 FinBERT 正在評分新聞標題…', 'active');
      flow.set('da-sentiment', {status: 'active', sub: 'FinBERT 評分中…'});
    }
    if (task.stage === 'complete') return {result: task.result, reported};
    if (task.stage === 'failed') throw new Error(task.message || '資料蒐集未完成，可重試');
    await sleep(1000);
    task = await api(`/api/collections/${encodeURIComponent(task.id)}`);
  }
}

async function collect() {
  const ticker = $('ticker').value, analysisDate = $('download-date').value;
  const refresh = $('refresh-data').checked, useFinbert = $('download-finbert').checked;
  resetTerminal();
  terminalLine('YOU', `collect --ticker ${ticker} --as-of ${analysisDate} --domains all${refresh ? ' --refresh' : ''}${useFinbert ? ' --finbert' : ''}`, 'command');
  terminalLine('COORD', refresh ? `強制建立 ${analysisDate} 新快照，派發 4 個資料 Agent` : `先搜尋 ${ticker}／${analysisDate} 可重用的四域完整快照`);
  notify('資料 Agent 正在檢查快照與來源…');
  renderCollectionAgents(null, 'running');
  let r, reported;
  try { ({result: r, reported} = await runCollectionTask({ticker, analysis_date: analysisDate, refresh, use_finbert: useFinbert})); }
  catch (error) { terminalLine('ERROR', error.message, 'error'); renderCollectionAgents(selectedDataset()); throw error; }
  if (r.reused) terminalLine('CACHE', `HIT dataset v${r.version} · ${r.id.slice(0, 12)}… · 未呼叫外部 API`, 'ok');
  else terminalLine('COORD', '已完成四域來源派工：Yahoo／SEC／Alpha+FNSPID／ALFRED');
  // A reused snapshot reports no live progress; list its recorded agents once.
  for (const [domain, item] of Object.entries(r.agents)) if (!reported.has(domain)) agentLine(domain, item);
  for (const limitation of r.limitations) terminalLine('AUDIT', limitation, 'warn');
  if (!r.reused) terminalLine('STORE', `SAVED dataset ${r.id.slice(0, 12)}… · immutable snapshot`, 'ok');
  await refreshDatasets();
  await refreshReadiness();
  selectDataset(r.id, r.analysis_date);
  setTab('experiment');
  notify(r.reused ? '已重用符合條件的既有資料快照；未重新呼叫來源 API。' : '資料 Agent 已完成本輪工作，資料集已保存。\n' + r.limitations.join('\n'));
}

async function pollAlphaVantageArchive() {
  while (true) {
    const s = await api('/api/sources/alpha-vantage-archive');
    $('av-archive-progress').textContent = s.stage === 'idle' ? '' : `${s.completed ?? 0}/${s.total ?? '?'} · ${s.current ? s.current + ' · ' : ''}${s.message || s.stage}`;
    if (s.stage !== 'running') return s;
    await sleep(2000);
  }
}

export function initDataPanel(config) {
  const todayIso = new Date().toISOString().slice(0, 10);
  $('ticker').innerHTML = config.tickers.map(v => `<option value="${escape(v)}">${escape(v)}</option>`).join('');
  $('ticker').value = 'NVDA';
  $('download-date').innerHTML = config.dates.map(v => `<option value="${escape(v)}">${escape(v)} · 季末研究日</option>`).join('')
    + `<option value="${escape(todayIso)}">${escape(todayIso)} · 今天（當下分析，非正式研究）</option>`;
  $('download-date').value = '2024-12-31';
  $('download-finbert').checked = state.finbertReady;
  const sourceReady = value => value ? 'ready' : 'warn';
  flow.setMany({
    'src-technical': 'ready',
    'src-fundamental': sourceReady(config.sources?.sec),
    'src-sentiment': sourceReady(config.sources?.alpha_vantage || config.sources?.fnspid),
    'src-macro': sourceReady(config.sources?.alfred),
  });
  api('/api/sources/alpha-vantage-archive').then(s => { if (s.stage === 'running') pollAlphaVantageArchive(); }).catch(() => {});
}

on('dataset:selected', dataset => renderCollectionAgents(dataset));
on('datasets:loaded', renderDatasetPreviewList);
on('readiness:stale', () => task(null, refreshReadiness));

$('download-form').addEventListener('submit', e => { e.preventDefault(); task(e.submitter, collect); });
$('source-check-button').addEventListener('click', e => task(e.currentTarget, async () => {
  const result = await api('/api/sources/check', {ticker: $('ticker').value, analysis_date: $('download-date').value});
  const label = {alpha_vantage: 'Alpha Vantage', alpha_vantage_cache: 'Alpha Vantage 快取', fnspid: 'FNSPID'};
  notify(Object.entries(result).map(([key, value]) => `${label[key] || key}：${value.message}（${value.records} 筆）`).join('\n'));
}));
$('av-archive-button').addEventListener('click', e => task(e.currentTarget, async () => {
  await api('/api/sources/alpha-vantage-archive/start', {});
  const s = await pollAlphaVantageArchive();
  if (s.stage === 'complete') notify(`Alpha Vantage 新聞快取已更新，本輪新增 ${s.added_rows ?? 0} 筆。`);
  else if (s.stage === 'rate_limited') notify(`今日額度已用完；${s.message || ''}`, true);
  else if (s.stage === 'failed') notify(s.message || '更新失敗', true);
}));
$('import-file').addEventListener('change', e => task(null, async () => {
  const file = e.target.files[0];
  if (!file) return;
  const r = await api(`/api/datasets/import?use_finbert=${$('use-finbert').checked}`, JSON.parse(await file.text()));
  await refreshDatasets();
  await refreshReadiness();
  selectDataset(r.id);
  notify(r.finbert_applied ? '資料集已驗證，新聞標題已由 FinBERT 分類並保存。' : '資料集已驗證並保存。');
}));
$('dataset-search').addEventListener('input', renderDatasetPreviewList);
