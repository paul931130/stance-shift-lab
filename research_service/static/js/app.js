// Entry point: boot the workspace, then hand off to the step modules.
//
//   store.js ─ shared state + event bus      flow.js ─ live pipeline map
//   nav.js   ─ step tabs / URL               terminal.js ─ coordinator shell
//   data-panel → experiment-panel → runs-panel → stats-panel (one per step)
import { $, notify } from './ui.js';
import { state } from './store.js';
import { api, task } from './api.js';
import { flow } from './flow.js';
import { setTab } from './nav.js';
import { resetTerminal, terminalLine } from './terminal.js';
import { initDataPanel, refreshReadiness } from './data-panel.js';
import { initExperimentPanel, applyModels, refreshDatasets } from './experiment-panel.js';
import { refreshJobs, schedulePoll } from './runs-panel.js';
import { refreshSettings, applySourceState } from './settings-panel.js';

function chooseInitialTab(requestedTab) {
  if (requestedTab) return;
  const selected = state.allJobs.find(job => job.id === state.selectedJob);
  const active = state.allJobs.some(job => ['queued', 'running', 'paused'].includes(job.status));
  if (selected?.status === 'complete') setTab('stats');
  else if (selected || active) setTab('runs');
  else if (state.datasetRows.length) setTab('experiment');
  else setTab('data');
}

async function initialize() {
  const config = await api('/api/config');
  state.demoMode = Boolean(config.demo_mode);
  state.parallelWorkers = config.parallel_workers || 1;
  state.currentProtocolVersion = config.default_protocol?.version || '';
  state.finbertReady = Boolean(config.sources?.finbert_local);
  if (state.demoMode) {
    const banner = $('demo-banner');
    banner.hidden = false;
    banner.textContent = '展示模式：使用內建合成資料與確定性回應，不需要 API key，不會呼叫外部模型，也不會產生正式研究結論。';
  }
  if (state.currentProtocolVersion) $('protocol-tag').textContent = `${state.currentProtocolVersion} 研究協議`;
  $('login').hidden = true;
  $('workspace').hidden = false;
  flow.mount($('flow-canvas'));

  resetTerminal();
  terminalLine('SYSTEM', `Agent Shell ready · protocol ${state.currentProtocolVersion}`, 'ok');
  terminalLine('COORD', `等待四域資料任務 · worker=${state.parallelWorkers}`);
  const readySources = Object.entries(config.sources).filter(([, ready]) => ready).map(([name]) => name.toUpperCase());
  terminalLine('SOURCE', readySources.join(' · ') || '尚未設定外部來源', readySources.length ? 'ok' : 'warn');

  try { $('first-time-guide').hidden = localStorage.getItem('firstTimeGuideDismissed') === '1'; }
  catch { $('first-time-guide').hidden = false; }
  initDataPanel(config);
  initExperimentPanel(config);
  applySourceState(config);

  const params = new URLSearchParams(location.search);
  const requestedTab = params.get('tab');
  state.selectedJob = params.get('selected') || null;
  setTab(requestedTab || (state.selectedJob ? 'runs' : 'data'), {skipUrl: true, force: true});

  // These reads are independent; loading them together keeps a slow
  // readiness scan or Ollama probe from blocking the rest of the workspace.
  const results = await Promise.allSettled([refreshSettings(), refreshDatasets(), refreshReadiness(), refreshJobs(), api('/api/models')]);
  const labels = ['設定', '資料集', '資料完整度', '實驗佇列', '模型'];
  const failures = results.map((r, i) => r.status === 'rejected' ? `${labels[i]}：${r.reason?.message || '讀取失敗'}` : '').filter(Boolean);
  if (failures.length) notify(`部分頁面資料暫時無法載入；可稍後按更新狀態重試。${failures.join('、')}`, true);
  applyModels(config, results[4].status === 'fulfilled'
    ? results[4].value
    : {ready: false, models: [], details: [], message: 'Ollama 暫時無法連線；可稍後重試或改用雲端模型。'});
  chooseInitialTab(requestedTab);
  schedulePoll();
}

$('login-form').addEventListener('submit', e => {
  e.preventDefault();
  task(e.submitter, async () => {
    await api('/api/login', {key: $('access-key').value});
    $('access-key').value = '';
    await initialize();
  });
});
$('refresh').addEventListener('click', e => task(e.currentTarget, async () => {
  // Independent reads: run together so one slow scan does not delay the rest.
  const results = await Promise.allSettled([refreshDatasets(), refreshReadiness(), refreshJobs()]);
  const failed = results.find(r => r.status === 'rejected');
  if (failed) throw failed.reason;
  notify('狀態已更新');
}));
$('dismiss-first-time-guide').addEventListener('click', () => {
  $('first-time-guide').hidden = true;
  try { localStorage.setItem('firstTimeGuideDismissed', '1'); } catch { /* private mode: guide just reappears */ }
});

task(null, initialize);
