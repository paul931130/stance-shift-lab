// Step 2 · experiment setup: pick a dataset snapshot and model, check the
// readiness guard, and queue an A/B/C/D comparison job.
import { $, escape, percentage, number, formatStamp, notify, datasetCut, datasetLabel, modelOptions, sleep } from './ui.js';
import { state, on, emit, selectedDataset } from './store.js';
import { api, task } from './api.js';
import { flow } from './flow.js';
import { setTab } from './nav.js';
import { refreshJobs } from './runs-panel.js';

const OVERRIDE_FOR = {sentiment_quality: 'override-sentiment', fundamental_quality: 'override-fundamental', model_too_small: 'override-model'};
const PREFLIGHT_DEBOUNCE_MS = 250;
let preflightTimer = null, preflightSeq = 0;

// The form fields as the job API expects them; shared by preflight and submit.
function jobPayload() {
  return {
    dataset_id: $('dataset').value, analysis_date: $('analysis-date').value,
    model: $('cloud-model').value.trim() || $('model').value,
    study: $('study').value, voting_samples: Number($('voting').value),
    missing_data_policy: $('missing-policy').value, anonymize_ticker: $('anonymize').checked,
    allow_point_fundamental: $('allow-point-fundamental').checked,
    allow_small_model: $('allow-small-model').checked,
    allow_low_quality_sentiment: $('allow-low-quality-sentiment').checked,
  };
}

function showGuard(ready, reason, message) {
  $('run-button').disabled = !ready || state.submitting;
  const guard = $('experiment-guard');
  guard.classList.toggle('ready', ready);
  guard.classList.toggle('checking', reason === 'checking');
  guard.textContent = message;
  for (const el of document.querySelectorAll('.check-wrap.needs-override')) el.classList.remove('needs-override');
  const neededId = OVERRIDE_FOR[reason];
  if (neededId) { $('quality-overrides').open = true; $(neededId).classList.add('needs-override'); }
}

// The server's preflight runs the exact validation used when a job is
// created, so the readiness rules live in one place. Requests are debounced
// and sequenced so a slow reply never overwrites a newer form state.
export function syncExperimentGuard() {
  clearTimeout(preflightTimer);
  const seq = ++preflightSeq;
  if (!$('dataset').value) { showGuard(false, 'no_dataset', '尚未選擇資料集，因此不能啟動實驗。'); return; }
  showGuard(false, 'checking', '正在向伺服器確認資料集、分析日與模型…');
  preflightTimer = setTimeout(async () => {
    let result;
    try { result = await api('/api/jobs/preflight', jobPayload()); }
    catch (error) { result = {ready: false, reason: 'error', message: `無法確認實驗條件：${error.message}`}; }
    if (seq !== preflightSeq) return;
    showGuard(result.ready, result.reason, result.ready
      ? '資料集、研究分析日、模型與新聞品質均已驗證；設定會一起鎖定於新實驗。'
      : result.message);
  }, PREFLIGHT_DEBOUNCE_MS);
}

function renderDatasetOptions(preserveValue) {
  let value = preserveValue !== undefined ? preserveValue : $('dataset').value;
  const search = ($('dataset-picker-search').value || '').trim().toLowerCase();
  const matching = state.datasetRows.filter(d => !search || d.ticker.toLowerCase().includes(search) || d.id === value);
  const currentTicker = $('ticker').value || '', currentDate = $('download-date').value || '';
  const currentCase = matching.filter(d => d.ticker === currentTicker && datasetCut(d) === currentDate);
  // Start from the exact case selected in step 1; the full store is still
  // reachable through an intentional ticker search.
  const filtered = search || value ? matching
    : currentCase.length ? [...currentCase].sort((a, b) => Number(b.version || 0) - Number(a.version || 0)).slice(0, 3)
    : [...matching].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || ''))).slice(0, 12);
  const autoSelected = !value && !search && currentCase.length > 0;
  if (autoSelected) value = filtered[0]?.id || '';
  $('dataset').innerHTML = '<option value="">請選擇資料集</option>' + filtered.map(d => `<option value="${escape(d.id)}">${escape(datasetLabel(d))}</option>`).join('');
  if (filtered.some(d => d.id === value)) $('dataset').value = value;
  $('dataset-picker-help').textContent = search
    ? `已列出 ${matching.length} 筆 ${search.toUpperCase()} 資料集；請選擇研究分析日。`
    : autoSelected ? `已自動選擇第 1 步目前案例的最新資料版本（${currentTicker}／${currentDate}）。`
    : value ? '已保留目前選定的資料集；要更換股票時，輸入股票代號即可篩選。'
    : `先列出最近建立的 12 筆資料集（共 ${state.datasetRows.length} 筆）；輸入股票代號可查看完整版本。`;
}

function renderDatasetDetail(alignDate = false) {
  const d = selectedDataset(), detail = $('dataset-detail');
  if (!d) {
    detail.hidden = true; detail.innerHTML = '';
    $('analysis-date').disabled = false;
    $('score-finbert-button').disabled = true;
    $('analysis-date-help').textContent = '分析日只使用 2021–2025 的季末切點；資料集的行情終點只供分析日後回測。';
    return;
  }
  const cut = datasetCut(d), uses = (d.used_analysis_dates || []).join('、') || '尚未建立實驗';
  const quality = d.coverage?.sentiment_quality, fundamental = d.coverage?.fundamental_quality || {};
  const qualityText = quality
    ? `新聞目標相關率 ${percentage(quality.target_relevance_rate ?? quality.ticker_mention_rate)}（標題直接提及 ${percentage(quality.ticker_mention_rate)}） · ${quality.passes_quality_gate ? '通過相關性' : '未通過相關性'} · FinBERT ${quality.finbert_scored || 0}/${quality.items || 0}${quality.median_relevance == null ? '' : ` · 中位相關性 ${number(quality.median_relevance)}`}`
    : '新聞相關性尚未計算';
  detail.hidden = false;
  detail.innerHTML = `<span class="version">v${d.version}</span><strong>${escape(d.ticker)} · ${d.kind === 'synthetic' ? '合成測試' : '歷史資料'}</strong><br>研究前行情起點 ${escape(d.price_start)} · ${d.price_count} 個交易日 · ${d.evidence_count} 筆證據<br><b>${cut ? `研究分析日：${escape(cut)}` : '研究分析日：舊資料集未記錄'}</b> · 已用切點 ${escape(uses)}<br><b>未來行情終點：${escape(d.price_end)}（只供 30／60／90 日回測，不能選為分析日）</b><br><small>SEC 可比較指標 ${fundamental.comparative_items || 0}/${fundamental.items || 0} · ${escape(qualityText)}</small><br>建立 ${escape(formatStamp(d.created_at))} · ${escape(d.source)}<br><code title="完整資料集 ID">ID ${escape(d.id)}</code>`;
  if (alignDate && cut && [...$('analysis-date').options].some(option => option.value === cut)) $('analysis-date').value = cut;
  $('analysis-date').disabled = Boolean(cut && d.kind === 'historical');
  $('score-finbert-button').disabled = state.scoring || !state.finbertReady || !(d.evidence_by_domain?.sentiment > 0);
  const isLiveCase = cut && cut === new Date().toISOString().slice(0, 10);
  $('analysis-date-help').textContent = isLiveCase
    ? `這筆資料集的研究分析日是今天（${cut}）：屬於當下單次分析，未來交易日尚未發生，30／60／90 日回測會顯示「pending」，不計入正式研究統計。`
    : cut ? `這筆資料集的研究分析日是 ${cut}；${d.price_end} 是未來行情終點，只拿來計算分析日後 30／60／90 個交易日的回測。`
    : `這筆舊版或匯入資料未記錄研究分析日；請選計劃書的季末切點。${d.price_end} 是未來行情終點，不能當分析日。`;
}

function announceSelection() {
  emit('dataset:selected', selectedDataset());
  syncExperimentGuard();
}

export function selectDataset(id, analysisDate) {
  renderDatasetOptions(id);
  $('dataset').value = id;
  if (analysisDate) $('analysis-date').value = analysisDate;
  renderDatasetDetail(!analysisDate);
  announceSelection();
}

export async function refreshDatasets() {
  const previous = $('dataset').value;
  state.datasetRows = await api('/api/datasets');
  flow.metric('datasets', state.datasetRows.length);
  renderDatasetOptions(previous);
  renderDatasetDetail(true);
  emit('datasets:loaded');
  announceSelection();
}

async function scoreSelectedDataset(id) {
  state.scoring = true;
  renderDatasetDetail();
  try {
    await api(`/api/datasets/${encodeURIComponent(id)}/finbert/start`, {});
    while (true) {
      const s = await api(`/api/datasets/${encodeURIComponent(id)}/finbert`);
      $('finbert-progress').textContent = `${s.completed || 0}/${s.total || '?'} 則 · ${s.message || s.stage}`;
      if (s.stage === 'complete' && s.result) {
        await refreshDatasets();
        emit('readiness:stale');
        selectDataset(s.result.id);
        notify(`FinBERT 已建立新版本，${s.result.items} 則標題全部完成。`);
        break;
      }
      if (['failed', 'idle'].includes(s.stage)) throw new Error(s.message || 'FinBERT 未完成；可重試');
      await sleep(1500);
    }
  } finally { state.scoring = false; renderDatasetDetail(); }
}

async function submitJob() {
  const payload = jobPayload();
  const job = await api('/api/jobs', payload);
  state.selectedJob = job.id;
  notify(`研究已加入背景佇列，模型為 ${payload.model}。候選決策、風控決策與品質覆寫會一起鎖定於協議。`);
  setTab('runs');
  await refreshJobs();
}

export function initExperimentPanel(config, models) {
  const todayIso = new Date().toISOString().slice(0, 10);
  $('analysis-date').innerHTML = config.dates.map(v => `<option value="${escape(v)}">${escape(v)} · 季末研究日</option>`).join('')
    + `<option value="${escape(todayIso)}">${escape(todayIso)} · 今天（當下分析，非正式研究）</option>`;
  $('analysis-date').value = '2024-12-31';
  const cloudLabels = {openrouter: 'OpenRouter', openai: 'OpenAI', gemini: 'Gemini'};
  const readyCloud = Object.entries(config.cloud_models || {}).filter(([, value]) => value).map(([key]) => cloudLabels[key] || key);
  $('cloud-model-state').textContent = readyCloud.length
    ? `可用雲端憑證：${readyCloud.join('、')}。輸入 LiteLLM 模型名稱即可切換。`
    : '尚未設定常用雲端模型金鑰；可先使用 Ollama，或在資料步驟的設定表單填入金鑰。';
}

// Apply the Ollama probe result: populate the local model picker and the
// model status chip in the top bar.
export function applyModels(config, m) {
  const installed = new Set(m.models || []);
  const formalIds = new Set(m.formal_models || []);
  const formal = (m.details || []).filter(item => formalIds.has(item.id) || (!formalIds.size && Number.parseFloat(item.parameter_size) >= 14));
  const chip = $('model-state');
  chip.dataset.state = state.demoMode ? 'demo' : m.ready ? (formal.length ? 'ok' : 'warn') : 'error';
  chip.textContent = state.demoMode ? 'DEMO · 內建合成 provider · 不代表正式模型資格'
    : m.ready ? (formal.length
      ? `Ollama 已連線 · ${m.models.length} 個本機模型 · ${formal.length} 個符合研究模型門檻`
      : `Ollama 已連線 · ${m.models.length} 個模型 · 無符合研究模型門檻的模型`)
    : m.http_status === 403 ? 'MODEL 403 · GPUtw Ollama 權限被拒'
    : m.http_status ? `MODEL HTTP ${m.http_status} · 無法連線` : 'MODEL OFFLINE · 尚未連線';
  const models = [...new Set([config.model, ...m.models])];
  $('model').innerHTML = modelOptions(models, m.details);
  const largest = [...(m.details || [])].sort((a, b) => (Number.parseFloat(b.parameter_size) || 0) - (Number.parseFloat(a.parameter_size) || 0))[0]?.id;
  $('model').value = installed.has(config.model) ? config.model : (formal[0]?.id || largest || config.model);
  if (!m.default_available && largest) chip.textContent += `；設定的預設模型 ${config.model} 尚未安裝，畫面已先選 ${$('model').value}`;
  syncExperimentGuard();
}

on('task:settled', syncExperimentGuard);

$('dataset').addEventListener('change', () => { renderDatasetDetail(true); announceSelection(); });
$('dataset-picker-search').addEventListener('input', () => renderDatasetOptions());
for (const id of ['analysis-date', 'allow-low-quality-sentiment', 'allow-point-fundamental', 'model', 'allow-small-model']) $(id).addEventListener('change', syncExperimentGuard);
$('cloud-model').addEventListener('input', syncExperimentGuard);
$('score-finbert-button').addEventListener('click', e => task(e.currentTarget, () => scoreSelectedDataset($('dataset').value)));
$('news-view').addEventListener('click', e => task(e.currentTarget, async () => {
  const id = $('dataset').value;
  if (!id) throw new Error('請先選擇資料集');
  const dataset = await api(`/api/datasets/${encodeURIComponent(id)}`);
  $('news-scores').innerHTML = dataset.evidence.filter(row => row.domain === 'sentiment').map(row => `<article><b>${escape(row.headline || row.claim)}</b><p>${escape(row.available_at)} · ${escape(row.sentiment_label || '尚未評分')} · 分數 ${number(row.sentiment_score)}</p>${row.sentiment_scores ? `<small>正向 ${percentage(row.sentiment_scores.positive)} · 中性 ${percentage(row.sentiment_scores.neutral)} · 負向 ${percentage(row.sentiment_scores.negative)}</small>` : ''}<p class="hint">${escape(row.sentiment_method || row.source_type || '原始證據')} · ${escape(row.source)}</p></article>`).join('') || '此版本沒有新聞證據';
}));
$('batch-file').addEventListener('change', e => task(null, async () => {
  const file = e.target.files[0];
  if (!file) return;
  const payload = JSON.parse(await file.text());
  const cases = Array.isArray(payload.cases) ? payload.cases : [];
  const dates = [...new Set(cases.map(c => c.analysis_date))].filter(Boolean).sort();
  const datasets = new Set(cases.map(c => c.dataset_id));
  const models = [...new Set(cases.map(c => c.model).filter(Boolean))];
  const summary = `即將建立 ${cases.length} 筆研究案例\n分析日：${dates.join('、') || '（未指定）'}\n涉及資料集：${datasets.size} 種\n模型：${models.join('、') || '使用各筆預設值'}\n\n確定要送出並排入佇列嗎？`;
  if (!cases.length || !window.confirm(summary)) { e.target.value = ''; return; }
  const ids = await api('/api/batches', payload);
  notify(`已加入 ${ids.length} 個研究案例。`);
  await refreshJobs();
  e.target.value = '';
}));
$('job-form').addEventListener('submit', e => {
  e.preventDefault();
  if (state.submitting) return;
  if (!$('dataset').value) { notify('請先選擇一筆資料集，才能開始研究實驗。', true); syncExperimentGuard(); return; }
  state.submitting = true;
  task(e.submitter, async () => { try { await submitJob(); } finally { state.submitting = false; } });
});
