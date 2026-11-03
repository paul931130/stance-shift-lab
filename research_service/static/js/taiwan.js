const $ = id => document.getElementById(id);
let currentTicker = '', quote = null, selectedReport = null, activeId = null, timer = null, alive = true, quoteVersion = 0, submittingReport = false;
const show = (message, error = false) => { $('notice').textContent = message; $('notice').className = error ? 'error' : ''; $('notice').hidden = false; };
const text = value => value == null ? '—' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
const number = value => value == null ? '—' : Number(value).toLocaleString('zh-TW', {maximumFractionDigits: 2});
const date = value => { if (!value) return '—'; if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value; const d = new Date(value); return Number.isNaN(d.valueOf()) ? String(value) : d.toLocaleString('zh-TW', {timeZone:'Asia/Taipei'}); };
async function api(path, body) {
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers: body === undefined ? {} : {'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal});
    const data = await response.json();
    if (response.status === 401) { $('login').hidden = false; $('workspace').hidden = true; stopPoll(); }
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
    return data;
  } catch (error) { throw new Error(error.name === 'AbortError' ? '請求逾時，請重試讀取。建立報告或保存決策逾時時，請先重新整理紀錄確認狀態。' : error.message); }
  finally { clearTimeout(timeout); }
}
function node(tag, content, className) { const el = document.createElement(tag); el.textContent = text(content); if (className) el.className = className; return el; }
function stopPoll() { clearTimeout(timer); timer = null; }
function resetReport() {
  stopPoll(); activeId = null; selectedReport = null; $('report').replaceChildren(); $('report-status').textContent = '尚未建立'; $('decision-fields').disabled = true; $('retry').hidden = true;
  $('decision-context').textContent = '完成並選取報告後才能保存。數量以股計，僅記錄判斷，不代表委託、成交或持倉。';
}
function renderQuote(q) {
  $('quote-symbol').textContent = q.ticker; $('quote-name').textContent = q.name || q.ticker;
  $('price').textContent = `${number(q.price)} ${q.currency || 'TWD'}`;
  $('change').textContent = `較前收 ${number(q.change)}（${number(q.change_pct)}%）`;
  $('quote-meta').replaceChildren();
  for (const [label, value] of [['資料來源', q.source], ['行情時間', date(q.as_of)], ['擷取時間', date(q.fetched_at)], ['前收', number(q.previous_close)]]) {
    const row = document.createElement('div'); row.append(node('dt', label), node('dd', value)); $('quote-meta').append(row);
  }
  $('delay').textContent = [q.delay_notice, ...(q.limitations || [])].filter(Boolean).join('；') || '日線資料可能延遲，不代表即時可成交價格。';
  $('history').replaceChildren();
  for (const item of (q.history || []).slice(-7)) { const el = document.createElement('div'); el.append(node('span', item.date), node('strong', number(item.close))); $('history').append(el); }
  if (!q.history?.length) $('history').textContent = '無近期歷史資料';
}
async function loadQuote() {
  const ticker = $('ticker').value.trim().toUpperCase(); $('ticker').value = ticker;
  if (!/^\d{4,6}\.(TW|TWO)$/.test(ticker)) throw new Error('請輸入台股代碼，例如 2330.TW 或 6488.TWO。');
  const version = ++quoteVersion; resetReport(); currentTicker = ticker; quote = null; $('generate').disabled = true; $('load').disabled = true;
  $('price').textContent = '載入中…'; $('quote-symbol').textContent = ticker; $('quote-name').textContent = '—'; $('change').textContent = '—'; $('quote-meta').replaceChildren(); $('history').replaceChildren(); $('delay').textContent = '正在讀取日線資料';
  try { const q = await api(`/api/taiwan/quote?ticker=${encodeURIComponent(ticker)}`); if (version !== quoteVersion || !alive) return; if (q.ticker !== ticker) throw new Error('行情代碼不一致，請重新讀取。'); quote = q; renderQuote(q); }
  catch (error) { if (version === quoteVersion) { $('price').textContent = '無法載入'; $('delay').textContent = error.message; } throw error; }
  finally { if (version === quoteVersion) { $('load').disabled = false; $('generate').disabled = !quote || !$('model').value; } }
}
function renderReport(r) {
  $('report-status').textContent = ({queued:'排隊中',running:'研究中',complete:'已完成',failed:'失敗'})[r.status] || r.status;
  $('progress').textContent = r.error || `報告 ${r.id} · ${r.ticker} · ${date(r.created_at)} · ${r.model || ''}`;
  $('report').replaceChildren(); selectedReport = null; $('decision-fields').disabled = true;
  if (r.status !== 'complete') return;
  if (r.ticker !== currentTicker || (r.quote?.ticker && r.quote.ticker !== r.ticker)) throw new Error('報告與目前股票不一致，請重新選擇報告。');
  selectedReport = r;
  if (r.quote) { quote = r.quote; renderQuote(r.quote); }
  for (const [key, title] of [['bull','多方代理'],['bear','空方代理'],['judge','裁判結論']]) {
    const result = r.report?.[key] || {};
    const section = document.createElement('section'); section.className = 'agent';
    section.append(node('h3', title), node('strong', ({Buy:'買進假說',Hold:'觀望',Sell:'賣出假說',NoTrade:'不交易'})[result.action] || '未提供判斷'), node('p', result.rationale || '未提供理由'));
    section.append(node('h4', '風險與反證'));
    const risks = document.createElement('ul');
    for (const risk of result.risks || []) risks.append(node('li', risk));
    if (!result.risks?.length) risks.append(node('li', '未提供風險說明'));
    section.append(risks);
    if (result.strongest_counterpoint) section.append(node('p', `最強反證：${result.strongest_counterpoint}`));
    section.append(node('p', `引用證據：${(result.evidence_ids || []).join('、') || '未提供'}`, 'muted'));
    $('report').append(section);
  }
  $('decision-fields').disabled = false;
  $('decision-context').textContent = `依報告 ${r.id}（${r.ticker}）記錄；沿用報告行情快照 ${date(r.quote?.as_of)}，參考價 ${number(r.quote?.price)}，僅供模擬參考，不代表成交。報告完成超過 24 小時須重新研究。`;
}
async function poll(id) {
  if (!alive || activeId !== id) return;
  try { const r = await api(`/api/taiwan/reports/${encodeURIComponent(id)}`); if (!alive || activeId !== id) return; renderReport(r); $('retry').hidden = true;
    if (['queued','running','pending'].includes(r.status)) timer = setTimeout(() => poll(id), 2500);
    else { $('generate').disabled = !quote || !$('model').value; await loadReports(); }
  } catch (error) { if (alive && activeId === id) { show(error.message, true); $('retry').hidden = false; $('generate').disabled = !quote || !$('model').value; } }
}
async function loadReports() {
  const data = await api('/api/taiwan/reports'); $('reports-list').replaceChildren();
  for (const r of data.items || []) {
    const el = node('div', '', 'record'); el.append(node('strong', `${r.ticker} · ${r.status}`), node('p', `${date(r.created_at)} · ${r.model || ''}`));
    const button = node('button', '查看報告', 'secondary'); button.type = 'button'; button.addEventListener('click', () => {
      ++quoteVersion; resetReport(); currentTicker = r.ticker; $('ticker').value = r.ticker; quote = null; $('generate').disabled = true; $('load').disabled = false;
      $('price').textContent = '等待報告快照'; $('quote-symbol').textContent = r.ticker; $('quote-name').textContent = '—'; $('change').textContent = '—'; $('quote-meta').replaceChildren(); $('history').replaceChildren(); $('delay').textContent = '報告使用建立時快照'; activeId = r.id; poll(r.id);
    }); el.append(button); $('reports-list').append(el);
  }
  if (!data.items?.length) $('reports-list').textContent = '尚無研究報告';
}
async function loadDecisions() {
  const data = await api('/api/taiwan/decisions'); $('decisions-list').replaceChildren();
  for (const d of data.items || []) { const el = node('div', '', 'record'); el.append(node('strong', `${d.ticker} · ${d.action} · ${number(d.quantity)} 股`), node('p', `${date(d.created_at)} · 參考價 ${number(d.reference_price)} · 報告 ${d.report_id}`), node('p', d.note || '無備註')); $('decisions-list').append(el); }
  if (!data.items?.length) $('decisions-list').textContent = '尚無模擬決策';
}
async function attempt(fn) { try { await fn(); } catch (error) { show(error.message, true); } }
$('selection').addEventListener('submit', e => { e.preventDefault(); attempt(loadQuote); });
$('preset').addEventListener('change', () => { $('ticker').value = $('preset').value; attempt(loadQuote); });
$('ticker').addEventListener('input', () => { ++quoteVersion; resetReport(); quote = null; currentTicker = ''; $('generate').disabled = true; $('load').disabled = false; $('quote-symbol').textContent = '需更新行情'; $('price').textContent = '—'; $('quote-name').textContent = '—'; $('change').textContent = '—'; $('quote-meta').replaceChildren(); $('history').replaceChildren(); $('delay').textContent = '代碼已變更，請更新行情。'; });
$('model').addEventListener('change', () => { $('generate').disabled = submittingReport || !quote || !$('model').value || ['排隊中','研究中'].includes($('report-status').textContent); });
$('generate').addEventListener('click', () => attempt(async () => {
  if (submittingReport || !quote || quote.ticker !== currentTicker || activeId && ['排隊中','研究中'].includes($('report-status').textContent)) return;
  const ticker = currentTicker, version = quoteVersion; submittingReport = true; resetReport(); $('generate').disabled = true; $('progress').textContent = '正在建立研究工作…';
  try { const job = await api('/api/taiwan/reports', {ticker, model:$('model').value}); await loadReports(); if (version !== quoteVersion || ticker !== currentTicker) return; activeId = job.id; await poll(job.id); }
  finally { submittingReport = false; if (!activeId) $('generate').disabled = !quote || !$('model').value; }
}));
$('retry').addEventListener('click', () => { if (activeId) poll(activeId); });
$('decision-form').addEventListener('submit', e => { e.preventDefault(); attempt(async () => {
  const r = selectedReport; if (!r || r.ticker !== currentTicker) throw new Error('請先選擇目前股票的完整報告。');
  const quantity = Number($('quantity').value), action = $('action').value;
  if (!Number.isSafeInteger(quantity) || quantity < 0 || (action !== 'Hold' && quantity === 0)) throw new Error('買進與賣出股數須為正整數；觀望可填 0 股。');
  $('save').disabled = true;
  try { await api('/api/taiwan/decisions', {report_id:r.id, action, quantity, note:$('note').value}); show('已保存模擬決策；這不是委託或成交。'); await loadDecisions(); }
  finally { $('save').disabled = false; }
}); });
$('refresh-reports').addEventListener('click', () => attempt(loadReports)); $('refresh-decisions').addEventListener('click', () => attempt(loadDecisions));
$('login-form').addEventListener('submit', e => { e.preventDefault(); attempt(async () => { await api('/api/login', {key:$('access-key').value}); $('access-key').value = ''; $('login').hidden = true; $('workspace').hidden = false; await initialize(); }); });
async function initialize() {
  const config = await api('/api/taiwan/config'); $('model').replaceChildren();
  if (config.enabled === false) {
    show('台股探索目前未啟用。請在研究服務中啟用模型與非示範模式後重新載入本頁。', true);
    for (const el of document.querySelectorAll('#workspace button, #workspace input, #workspace select')) el.disabled = true;
    $('reports-list').textContent = '服務尚未啟用'; $('decisions-list').textContent = '服務尚未啟用'; return;
  }
  for (const m of config.models || []) { const value = typeof m === 'string' ? m : m.id || m.name; const option = node('option', value); option.value = value; $('model').append(option); }
  if (config.default_model) $('model').value = config.default_model;
  if (config.demo_mode) show('目前為示範模式，台股探索需要啟用研究服務與模型。', true);
  const results = await Promise.allSettled([loadQuote(), loadReports(), loadDecisions()]);
  const failures = results.filter(r => r.status === 'rejected'); if (failures.length) show(failures.map(r => r.reason.message).join('；'), true);
}
window.addEventListener('pagehide', () => { alive = false; stopPoll(); });
window.addEventListener('pageshow', event => { if (event.persisted) { alive = true; if (activeId) poll(activeId); } });
attempt(initialize);
