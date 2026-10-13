// Step 3 · agent execution: the research queue, background polling, the
// selected run's detail and the downstream half of the flow map.
import { $, escape, percentage, number, notify, statuses, friendlyJobError, missingPolicyLabel, protocolLabel, traceMessage, terminalStamp, copyablePre, COLLECTION_DOMAINS, DOMAIN_LABELS } from './ui.js';
import { state } from './store.js';
import { api, task } from './api.js';
import { flow } from './flow.js';
import { setTab, syncUrl } from './nav.js';
import { showStatistics } from './stats-panel.js';
import { refreshStudies } from './study-panel.js';
import { designOf, designLabel, stripOllama, setResearchQuestion } from './design-panel.js';
import { rq2RunPanel, rq3RunPanel } from './rq-run.js';

const ACTIVE_POLL_MS = 3000, IDLE_POLL_MS = 30000, MAX_POLL_MS = 60000;
const GROUP_LABELS = {A: '單次判斷', B: '獨立投票', C: '固定立場辯論', D: '立場交換辯論'};
let pollTimer = null, pollFailures = 0;
let lastStatuses = null, recordFilter = '';
const BASE_TITLE = document.title;

// Tell the user when a background job finishes or stops, even if they are
// looking at another step, and mirror live progress in the browser tab title.
function announceTransitions(jobs) {
  const previous = lastStatuses;
  lastStatuses = new Map(jobs.map(job => [job.id, job.status]));
  if (previous) for (const job of jobs) {
    const before = previous.get(job.id);
    if (!before || before === job.status) continue;
    const name = `${job.config.ticker} · ${job.config.analysis_date}`;
    if (job.status === 'complete') notify(`${name} 已完成，可到「統計結果」查看。`);
    else if (job.status === 'paused' && job.error) notify(`${name} 已暫停：${friendlyJobError(job.error)}`, true);
    else if (job.status === 'cancelled') notify(`${name} 已取消。`);
  }
  const running = jobs.filter(job => job.status === 'running');
  document.title = running.length
    ? `(${running.map(job => `${job.steps}/${generalistTotal(job.config.protocol)}`).join(', ')}) ${BASE_TITLE}`
    : BASE_TITLE;
}

// RQ2 runs C and D once per model assignment; RQ3 keeps the four generalist arms (domain arms are counted apart).
const assignmentCount = protocol => (protocol.debate_assignments || ['AA']).length;
const groupTotals = protocol => ({A: 1, B: protocol.voting_samples, C: 7 * assignmentCount(protocol), D: 7 * assignmentCount(protocol)});
const generalistTotal = protocol => 15 + protocol.voting_samples + 14 * (assignmentCount(protocol) - 1);
// RQ3 adds 29 nominal calls per domain arm (4 domains x (6 turns + 1 view) + 1 aggregator).
const domainArms = config => config.domain_debate ? (config.domain_debate.rule === 'both' ? 2 : 1) : 0;
const jobTotal = config => generalistTotal(config.protocol) + 29 * domainArms(config);
// Domains without usable evidence get a recorded InsufficientInfo view and skip their calls.
const domainCalls = s => (s.domain_records || []).filter(record => !record.audit?.deterministic).length;
const outputsDone = s => (s.records || []).length + domainCalls(s);
function outputText(job, s, total) {
  const done = outputsDone(s), skipped = job.status === 'complete' ? total - done : 0;
  return skipped > 0 ? `${done} 次模型輸出（名義 ${total} 次，資訊不足的領域略過 ${skipped} 次）` : `${done}/${total} 模型輸出`;
}

// What the pipeline map needs to know about a job's research design.
function mapDesign(config) {
  const kind = designOf(config), protocol = config.protocol;
  if (kind === 'rq2') return {kind, assignments: protocol.debate_assignments || [], models: {A: stripOllama(protocol.debate_model_a), B: stripOllama(protocol.debate_model_b)}};
  if (kind === 'rq3') return {kind, rule: config.domain_debate.rule};
  return {kind};
}

export async function refreshJobs() {
  let dashboard;
  try {
    dashboard = await api('/api/dashboard' + (state.selectedJob ? `?selected=${encodeURIComponent(state.selectedJob)}` : ''));
  } catch (error) {
    if (!state.selectedJob) throw error;
    // A bookmarked URL may point at a job that no longer exists; fall back to
    // the unfiltered dashboard instead of leaving the workspace on an error.
    state.selectedJob = null;
    syncUrl();
    dashboard = await api('/api/dashboard');
  }
  state.allJobs = dashboard.jobs;
  announceTransitions(state.allJobs);
  state.hasActiveJobs = state.allJobs.some(job => job.status === 'queued' || job.status === 'running');
  flow.metric('cases', state.allJobs.filter(job => job.status === 'complete').length);
  renderJobList();
  const completed = state.allJobs.find(job => job.status === 'complete');
  if (completed && state.autoStatsJob !== completed.id) {
    state.autoStatsJob = completed.id;
    if (state.currentTab === 'runs' && state.selectedJob === completed.id) setTab('stats');
  }
  if (dashboard.selected) await showJob(state.selectedJob, dashboard.selected);
  // The studies card rides on the same poll; its failure must not break the queue view.
  try { await refreshStudies(); } catch (error) { console.warn('studies refresh failed', error); }
  schedulePoll();
}

function renderJobList() {
  const search = ($('job-search').value || '').trim().toLowerCase();
  const status = $('job-status-filter').value || '';
  const jobs = state.allJobs.filter(j => (!status || j.status === status)
    && (!search || `${j.config.ticker} ${j.config.analysis_date}`.toLowerCase().includes(search)));
  const list = $('jobs');
  list.className = jobs.length ? 'job-list' : 'empty';
  $('job-count').textContent = state.allJobs.length ? `${state.allJobs.length}` : '';
  if (!state.allJobs.length) { list.textContent = '尚無實驗。先準備資料，再建立第一筆研究。'; return; }
  if (!jobs.length) { list.textContent = `沒有符合條件的實驗（共 ${state.allJobs.length} 筆）。`; return; }
  list.innerHTML = jobs.map(j => {
    const total = generalistTotal(j.config.protocol), ratio = Math.min(100, Math.round((j.steps / total) * 100));
    return `<button type="button" class="job${j.id === state.selectedJob ? ' selected' : ''}" data-open="${escape(j.id)}" aria-pressed="${j.id === state.selectedJob}">
      <span class="job-head"><strong>${escape(j.config.ticker)} · ${escape(j.config.analysis_date)}</strong><span class="status ${escape(j.status)}">${escape(statuses[j.status])}</span></span>
      <small>${escape(j.config.protocol.model)} · ${j.steps}/${total} 模型輸出${j.wants_run === 0 && j.status === 'running' ? ' · 將在本波次後暫停' : ''}</small>
      <small>${designOf(j.config) === 'rq1' ? '' : `<b class="design-tag">${escape(designLabel(j.config))}</b> · `}${escape(protocolLabel(j.config.protocol))} · ${escape(missingPolicyLabel(j.config.protocol))} · ${escape(j.config.protocol.study)} · ${j.id.slice(0, 8)}</small>
      <span class="job-meter ${escape(j.status)}"><i data-ratio="${ratio}"></i></span>
    </button>`;
  }).join('');
  for (const bar of list.querySelectorAll('.job-meter i')) bar.style.width = `${bar.dataset.ratio}%`;
}

export function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
  if ($('workspace').hidden || document.hidden) return;
  const delay = Math.min(MAX_POLL_MS, (state.hasActiveJobs ? ACTIVE_POLL_MS : IDLE_POLL_MS) * (2 ** Math.min(pollFailures, 2)));
  pollTimer = setTimeout(async () => {
    if (document.hidden || $('workspace').hidden) return;
    if (state.busy) { schedulePoll(); return; }
    state.busy = true;
    try { await refreshJobs(); pollFailures = 0; }
    catch (error) { pollFailures = Math.min(pollFailures + 1, 2); notify(`無法更新狀態：${error.message}`, true); }
    finally { state.busy = false; schedulePoll(); }
  }, delay);
}

// ---------- Run detail blocks ----------
function researchAgentPanel(s, jobStatus) {
  const cards = COLLECTION_DOMAINS.map(domain => {
    const item = (s.research || {})[domain];
    const status = item?.status === 'complete' ? 'complete' : item?.status === 'degraded' ? 'degraded' : item?.status === 'missing' ? 'missing' : s.inputs && jobStatus === 'running' ? 'running' : 'idle';
    const label = {complete: '分析完成', degraded: '改用原始摘錄', missing: '資料缺口', running: '分析中', idle: '等待資料'}[status];
    return `<article class="agent-card ${status}"><b>${DOMAIN_LABELS[domain]}研究代理人</b><small>${escape(domain)}</small><span>${label}</span><p>${escape(item?.summary || '等待協調者分派資料快照')}</p></article>`;
  }).join('');
  return `<section class="execution-block"><div class="subheading"><h3>四個研究代理人</h3><small>共用同一份資料快照 · 並行數 ${state.parallelWorkers}</small></div><div class="agent-grid">${cards}</div></section>`;
}

function traceTerminal(job, s) {
  const lines = (s.trace || []).map(item => `<div class="terminal-line ok"><time>${escape(terminalStamp(new Date(item.at)))}</time><b>[TRACE]</b><span>${escape(traceMessage(item.node))}</span></div>`).join('');
  const waiting = !['complete', 'cancelled', 'paused'].includes(job.status) ? '<div class="terminal-line active"><time>NOW</time><b>[WORKER]</b><span>等待下一個進度存檔點…</span></div>' : '';
  return `<section class="execution-block"><div class="subheading"><h3>研究代理人終端</h3><small>實際執行紀錄 · 執行中每 3 秒、閒置時每 30 秒更新；分頁在背景時暫停更新</small></div><div class="terminal-screen run-terminal"><div class="terminal-line command"><time>CASE</time><b>[SESSION]</b><span>${escape(job.id.slice(0, 8))} · ${escape(job.config.protocol.model)} · ${escape(job.config.protocol.version)}</span></div>${lines || '<div class="terminal-line"><time>--:--:--</time><b>[QUEUE]</b><span>等待協調者領取工作…</span></div>'}${waiting}</div></section>`;
}

function groupPhase(group, count, total) {
  if (count >= total) return '已完成';
  if (total > 7 && (group === 'C' || group === 'D')) return `各指派辯論中 ${count}/${total}`;
  if (group === 'A') return '單次決策';
  if (group === 'B') return `獨立投票 ${count}/${total}`;
  if (count < 2) return '第 1 輪';
  if (count < 4) return '第 2 輪';
  if (count < 6) return '第 3 輪';
  return '裁決中';
}

function groupProgressPanel(s, protocol, jobStatus) {
  const totals = groupTotals(protocol);
  const executionNote = String(protocol.model || '').startsWith('ollama/')
    ? '本機 Ollama 決策依序排程，避免模型佇列互相卡住'
    : `並行數 ${state.parallelWorkers} · 依輪次先後同時執行`;
  const cards = Object.keys(GROUP_LABELS).map(group => {
    const count = (s.records || []).filter(record => record.group === group).length, total = totals[group];
    const status = count >= total ? 'complete' : s.report && jobStatus === 'running' ? 'running' : jobStatus === 'paused' && count ? 'paused' : 'idle';
    const decision = s.decisions?.[group];
    return `<article class="group-card ${status}"><b>${group} · ${GROUP_LABELS[group]}</b><span>${groupPhase(group, count, total)}</span><progress max="${total}" value="${count}" aria-label="${group} 組進度"></progress><small>${count}/${total} 次模型輸出${decision ? ` · ${escape(decision.action)}` : ''}</small></article>`;
  }).join('');
  return `<section class="execution-block"><div class="subheading"><h3>A/B/C/D 實驗執行</h3><small>${escape(executionNote)} · ${escape(missingPolicyLabel(protocol))} · 同輪不互看</small></div><div class="group-grid">${cards}</div></section>`;
}

function backtestComparison(s) {
  if (!s.cases?.length) return '<p class="hint">四組決策鎖定後，系統會自動產生 30／60／90 交易日回測。</p>';
  const rows = s.cases.filter(row => row.cost_model === 'corwin_schultz' && (row.decision_layer || 'gated') === 'candidate');
  const cell = (group, horizon) => {
    const row = rows.find(item => item.group === group && item.horizon === horizon);
    return !row || row.status === 'pending' ? '<span class="pending">待成熟</span>' : row.status !== 'complete' ? escape(row.status) : percentage(row.net_return);
  };
  const benchmark = rows.find(row => row.horizon === 60 && row.status === 'complete');
  return `<section class="execution-block"><div class="subheading"><h3>四組結果與回測比較</h3><small>Corwin–Schultz 成本後淨報酬</small></div><div class="table-wrap"><table><thead><tr><th>組別</th><th>最終決策</th><th>30 日</th><th>60 日（主要）</th><th>90 日</th></tr></thead><tbody>${'ABCD'.split('').map(group => `<tr><td><b>${group}</b></td><td>${escape(s.decisions?.[group]?.action || '—')}</td><td>${cell(group, 30)}</td><td>${cell(group, 60)}</td><td>${cell(group, 90)}</td></tr>`).join('')}</tbody></table></div><p class="hint">同期間 60 日 Buy-and-Hold：${benchmark ? percentage(benchmark.benchmark_return) : '待成熟'}。完整逐日報酬、零成本版本與統計檢定可由 ZIP 下載。</p></section>`;
}

function estimateRemaining(s, total, jobStatus) {
  if (['complete', 'cancelled'].includes(jobStatus)) return null;
  const done = outputsDone(s), remaining = total - done;
  if (remaining <= 0) return null;
  const elapsed = (s.records || []).map(r => r.audit?.usage?.client_elapsed_seconds).filter(v => typeof v === 'number' && Number.isFinite(v) && v > 0);
  if (elapsed.length < 2) return null;
  const seconds = (elapsed.reduce((a, b) => a + b, 0) / elapsed.length) * remaining;
  if (seconds < 60) return '不到 1 分鐘';
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `約 ${minutes} 分鐘` : `約 ${(minutes / 60).toFixed(1)} 小時`;
}

function decisionCards(s) {
  if (!s.decisions) return '<p class="hint">四組完成後由守門員同步鎖定決策。</p>';
  return `<div class="decisions">${Object.entries(s.decisions).map(([g, d]) => `<div><small>${g} 組 · 信心 ${percentage(d.confidence)} · 預測 ${number(d.expected_return_pct)}%</small><strong>${escape(d.action)}</strong><small>模型：${escape(d.model_action || d.candidate_action)} · 推導：${escape(d.derived_action || d.candidate_action)} · 候選：${escape(d.candidate_action)}<br>Hold 門檻 ±${number(d.hold_band_pct)}%（預測報酬在此範圍內視為 Hold） · 資料覆蓋 ${percentage(d.gate.domain_coverage)}<br>${d.gate.missing_data_control ? '缺資料對照：未覆寫模型決策<br>' : ''}${escape(d.gate.reasons.join(' / ') || '通過門檻')}</small></div>`).join('')}</div>`;
}

// Downstream half of the map: research agents → report → A/B/C/D →
// Gatekeeper → backtest, all derived from the persisted job state.
function renderJobFlow(job, s, total) {
  const kind = designOf(job.config);
  flow.setDesign(mapDesign(job.config));
  setResearchQuestion(kind);
  const live = ['running', 'queued'].includes(job.status), paused = job.status === 'paused';
  const moving = live ? 'active' : paused ? 'warn' : 'idle';
  const update = {snapshot: {status: 'done'}};
  let researchDone = 0;
  for (const domain of COLLECTION_DOMAINS) {
    const item = (s.research || {})[domain];
    const status = item?.status === 'complete' ? 'done' : item?.status === 'degraded' || item?.status === 'missing' ? 'warn' : s.inputs && live ? 'active' : 'idle';
    if (item) researchDone++;
    update[`ra-${domain}`] = {status, sub: item?.status === 'complete' ? '分析完成' : item?.status === 'missing' ? '資料缺口' : item?.status === 'degraded' ? '改用原始摘錄' : status === 'active' ? '分析中…' : '等待分析'};
  }
  update.report = s.report ? {status: 'done', sub: '已鎖定'} : {status: researchDone === 4 ? moving : 'idle', sub: '鎖定後分派'};
  const totals = groupTotals(job.config.protocol);
  let groupsDone = 0;
  for (const group of Object.keys(totals)) {
    const count = (s.records || []).filter(record => record.group === group).length, groupTotal = totals[group];
    const decision = s.decisions?.[group];
    if (count >= groupTotal) groupsDone++;
    const status = count >= groupTotal ? 'done' : s.report && live ? 'active' : paused && count ? 'warn' : 'idle';
    update[`g-${group}`] = {status, count, total: groupTotal, sub: decision ? `${count}/${groupTotal} · ${decision.action}` : `${count}/${groupTotal}`};
  }
  let aggregated = true;
  if (kind === 'rq3') {
    const rule = job.config.domain_debate.rule;
    const arms = ['C_domain', 'D_domain'].filter(arm => rule === 'both' || (rule === 'fixed') === (arm === 'C_domain'));
    const records = s.domain_records || [];
    let domainsDone = 0;
    for (const domain of COLLECTION_DOMAINS) {
      const mine = records.filter(record => record.domain === domain), views = mine.filter(record => record.kind === 'view');
      const done = views.length >= arms.length, domainTotal = 7 * arms.length;
      if (done) domainsDone++;
      update[`dd-${domain}`] = {status: done ? 'done' : s.report && live ? 'active' : paused && mine.length ? 'warn' : 'idle',
        count: done ? domainTotal : mine.length, total: domainTotal,
        sub: done ? [...new Set(views.map(view => view.output.direction))].join('／') : `${mine.length}/${domainTotal}`};
    }
    aggregated = arms.every(arm => s.decisions?.[arm]);
    update.agg = aggregated ? {status: 'done', sub: arms.map(arm => `${arm[0]} ${s.decisions[arm].action}`).join('・')}
      : {status: domainsDone === 4 ? moving : 'idle', sub: domainsDone === 4 ? '整合領域觀點' : 'Final Aggregator'};
  }
  update.gate = s.decisions && aggregated ? {status: 'done', sub: '決策已鎖定'}
    : {status: groupsDone === 4 && aggregated ? moving : 'idle', sub: '引用與門檻'};
  const cases = s.cases || [], matured = cases.some(row => row.status === 'complete');
  update.backtest = cases.length ? {status: matured ? 'done' : 'warn', sub: matured ? '已計算報酬' : '待成熟'} : {status: s.decisions ? moving : 'idle', sub: '30／60／90 日'};
  if (flow.get('stats') !== 'done') update.stats = {status: job.status === 'complete' ? 'ready' : 'idle'};
  if (job.error) for (const value of Object.values(update)) if (value.status === 'active') value.status = 'error';
  flow.setMany(update);
  flow.metric('outputs', outputsDone(s));
  const last = s.trace?.at(-1)?.node;
  const tag = kind === 'rq1' ? '' : `${designLabel(job.config)} · `;
  flow.caption(job.error ? `${job.config.ticker} · 執行中斷：${friendlyJobError(job.error)}`
    : `${tag}${job.config.ticker} · ${job.config.analysis_date} · ${statuses[job.status]} — ${last ? traceMessage(last) : '等待協調者領取工作'} · ${outputText(job, s, total)}`);
}

function designBlocks(job, s) {
  const kind = designOf(job.config);
  return kind === 'rq2' ? rq2RunPanel(job, s) : kind === 'rq3' ? rq3RunPanel(job, s) : '';
}

export async function showJob(id, loadedJob = null) {
  state.selectedJob = id;
  syncUrl();
  const job = loadedJob || await api(`/api/jobs/${id}?detail=true`), s = job.state, total = jobTotal(job.config);
  state.selectedProtocol = job.config.protocol_hash;
  const isFinal = ['complete', 'cancelled'].includes(job.status);
  const trace = s.trace.at(-1)?.node || '等待協調者';
  const oldProtocol = state.currentProtocolVersion && job.config.protocol.version !== state.currentProtocolVersion;
  const protocolNotice = oldProtocol
    ? `這是協議 ${job.config.protocol.version || '未記錄'} 的既有結果；決策規則修正只會套用於 ${state.currentProtocolVersion} 新建立的實驗。`
    : `${protocolLabel(job.config.protocol)} · 使用目前的 Buy／Hold／Sell 候選決策規則。`;
  const eta = estimateRemaining(s, total, job.status);
  const pendingMemory = s.memory_audit?.pending_earlier_cases || [];
  const memoryNotice = pendingMemory.length
    ? `<p class="protocol-warning">記憶鎖定時，同股票較早的 ${pendingMemory.length} 個案例尚未完成（${escape(pendingMemory.map(c => c.analysis_date).join('、'))}）；此案例的記憶可能不完整，正式統計前建議重跑。</p>`
    : '';
  renderJobFlow(job, s, total);
  $('run-empty').hidden = true;
  const output = $('run-detail');
  output.hidden = false;
  // Keep the open/closed state of the audit <details> across poll refreshes.
  const openDetails = [...output.querySelectorAll('details')].map(d => d.open);
  output.innerHTML = `<div class="run-head"><div><div class="section-label">CASE / ${escape(id.slice(0, 8))}</div><h2>${escape(job.config.ticker)} · ${escape(job.config.analysis_date)} <span class="status ${escape(job.status)}">${escape(statuses[job.status])}</span></h2></div><div class="run-progress"><strong>${outputsDone(s)}<small>/${total}</small></strong><span>${job.config.domain_debate ? '模型輸出（含領域辯論）' : '決策輸出'}</span></div></div>
    <p class="${oldProtocol ? 'protocol-warning' : 'hint'}">${escape(protocolNotice)}</p>${memoryNotice}
    <p class="hint">目前：${escape(trace)} · 已存檔 ${s.attempts.length} 次${eta ? ` · 依目前平均耗時預估剩餘 ${escape(eta)}` : ''}</p>
    <progress class="progress" max="${total}" value="${s.records.length}" aria-label="決策推論進度"></progress>
    ${job.error ? `<p class="error-text">${escape(friendlyJobError(job.error))}</p>` : ''}
    <div class="actions">${oldProtocol ? `<button class="quiet" type="button" data-clone="${escape(id)}">複製至新版重新執行</button>` : ''}${!isFinal && !oldProtocol ? `<button class="quiet" type="button" data-control="${job.wants_run ? 'pause' : 'resume'}">${job.wants_run ? '暫停' : '繼續執行'}</button><button class="quiet" type="button" data-control="cancel">取消實驗</button>` : ''}<a href="/api/jobs/${id}/export">下載研究產物 ZIP</a>${job.status === 'complete' ? '<button type="button" data-statistics="true">檢視同協議統計 →</button>' : ''}</div>
    ${groupProgressPanel(s, job.config.protocol, job.status)}${decisionCards(s)}${designBlocks(job, s)}${backtestComparison(s)}${researchAgentPanel(s, job.status)}${traceTerminal(job, s)}
    <details><summary>中立研究報告與來源</summary>${copyablePre(JSON.stringify(s.report || s.research, null, 2))}</details>
    <details><summary>逐步論證與三輪立場交換（${s.records.length}）</summary><div class="record-filter" role="group" aria-label="依組別篩選">${['', ...Object.keys(GROUP_LABELS)].map(g => `<button type="button" class="quiet" data-record-filter="${g}" aria-pressed="${recordFilter === g}">${g ? `${g} · ${GROUP_LABELS[g]}` : '全部'}</button>`).join('')}</div>${s.records.map(r => `<article class="trace" data-group="${escape(r.group)}"${recordFilter && r.group !== recordFilter ? ' hidden' : ''}><strong>${escape(r.group)}${r.assignment ? `@${escape(r.assignment)}` : ''} · ${escape(r.key)} · ${escape(r.stance)}</strong><p>${escape(r.output.rationale)}</p><small>引用：${escape(r.output.evidence_ids.join(', '))}<br>提示雜湊：${escape(r.audit.prompt_hash)}</small></article>`).join('')}</details>
    <details><summary>回測、門檻與流程紀錄</summary>${copyablePre(JSON.stringify({decisions: s.decisions, cases: s.cases, compute_usage: s.compute_usage, completeness_diagnostic: s.completeness_diagnostic, trace: s.trace}, null, 2))}</details>`;
  output.querySelectorAll('details').forEach((d, i) => { if (openDetails[i]) d.open = true; });
  renderJobList();
}

document.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.recordFilter !== undefined) {
    // Filter in place so a poll refresh (which re-renders) keeps the same choice.
    recordFilter = b.dataset.recordFilter;
    const details = b.closest('details');
    for (const button of details.querySelectorAll('[data-record-filter]')) button.setAttribute('aria-pressed', String(button === b));
    for (const article of details.querySelectorAll('article.trace')) article.hidden = Boolean(recordFilter) && article.dataset.group !== recordFilter;
    return;
  }
  if (b.dataset.open) task(b, async () => { await showJob(b.dataset.open); setTab('runs', {reveal: window.matchMedia('(max-width: 1080px)').matches}); });
  if (b.dataset.control) task(b, async () => {
    if (b.dataset.control === 'cancel' && !window.confirm('取消此實驗？已完成紀錄會保留，取消後無法續跑。')) return;
    await api(`/api/jobs/${state.selectedJob}/${b.dataset.control}`, {});
    await refreshJobs();
  });
  if (b.dataset.clone) task(b, async () => { const j = await api(`/api/jobs/${b.dataset.clone}/clone`, {}); state.selectedJob = j.id; await refreshJobs(); });
  if (b.dataset.statistics) task(b, showStatistics);
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { if (pollTimer) clearTimeout(pollTimer); pollTimer = null; return; }
  task(null, refreshJobs);
});
$('job-search').addEventListener('input', renderJobList);
$('job-status-filter').addEventListener('change', renderJobList);
