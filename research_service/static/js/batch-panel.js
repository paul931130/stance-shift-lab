// Many cases at once: batch dataset collection (step 1) and planning,
// preregistering and queueing a whole study (step 2) without a JSON file.
import { $, escape, notify, formatStamp } from './ui.js';
import { api, task, BATCH_TIMEOUT } from './api.js';
import { mountCasePicker } from './case-picker.js';

let collectPicker, planPicker, lastPlan = null, collectTimer = null;

const REASONS = {
  no_dataset: '沒有完整資料集', sentiment_quality: '新聞品質未通過', fundamental_quality: '基本面只有點時資料',
  date_mismatch: '分析日不符', model_not_installed: '模型不可用', news_capped: '舊版截斷新聞', design_mismatch: '設計不符',
};

function switchMode(attr, panelAttr, mode) {
  for (const b of document.querySelectorAll(`[${attr}]`)) {
    const on = b.getAttribute(attr) === mode;
    b.setAttribute('aria-selected', String(on));
    b.tabIndex = on ? 0 : -1;
  }
  for (const p of document.querySelectorAll(`[${panelAttr}]`)) p.hidden = p.getAttribute(panelAttr) !== mode;
}

function planSettings() {
  return {
    tickers: planPicker.tickers(), dates: planPicker.dates(),
    model: ($('plan-cloud-model').value || '').trim() || $('plan-model').value,
    voting_samples: Number($('plan-voting').value), missing_data_policy: $('plan-missing').value,
    anonymize_ticker: $('plan-anonymize').checked, design: 'quarterly', study: 'study1',
  };
}

function renderPlan(plan) {
  const box = $('plan-result');
  const blocked = plan.cases.filter(c => !c.ready);
  const byReason = {};
  for (const c of blocked) (byReason[c.reason] ||= []).push(c);
  const blockedList = Object.entries(byReason).map(([reason, rows]) =>
    `<li><b>${escape(REASONS[reason] || reason)}</b>（${rows.length} 案）：${rows.slice(0, 12).map(r => `${escape(r.ticker)} ${escape(r.analysis_date)}`).join('、')}${rows.length > 12 ? ' …' : ''}</li>`).join('');
  const registered = plan.already_preregistered;
  box.innerHTML = `<div class="plan-summary ${plan.ready ? '' : 'blocked'}">
      <p><b>${plan.ready}</b> / ${plan.total} 案可以執行${plan.protocol_hash ? ` · 協議 ${escape(plan.protocol_hash.slice(0, 8))}` : ''}</p>
      ${registered ? `<p class="hint">這個設定已於 ${escape(formatStamp(plan.frozen_at))} 事前登記。排入時只會加入登記樣本內、尚未建立的案例。</p>` : ''}
      ${blocked.length ? `<details><summary>${blocked.length} 案不能執行</summary><ul>${blockedList}</ul><p class="hint">缺資料集的案例可到「資料準備 → 多筆」補齊後再預覽。</p></details>` : ''}
      <div class="study-actions">
        ${plan.ready && !registered ? `<button type="button" data-plan-action="register">事前登記並排入 ${plan.ready} 案（正式）</button>` : ''}
        ${plan.ready && registered ? `<button type="button" data-plan-action="enqueue">排入已登記的研究</button>` : ''}
        ${plan.ready && !registered ? `<button type="button" class="quiet" data-plan-action="explore">只排入，不登記（探索性）</button>` : ''}
      </div>
    </div>`;
}

async function planAction(action) {
  const plan = lastPlan;
  const payload = {cases: plan.ready_cases};
  if (action === 'register') {
    const ok = window.confirm(`事前登記 ${plan.ready} 個案例並排入佇列？\n\n登記會鎖定這個協議的研究樣本，之後不能增減；只有登記後建立的實驗算正式結果。\n\n請先確認模型已連線（GPU 已開機且模型載入完成）。`);
    if (!ok) return;
    const registered = await api('/api/studies/preregister', payload, 'POST', BATCH_TIMEOUT);
    const result = await api(`/api/studies/${encodeURIComponent(registered.protocol_hash)}/enqueue`, undefined, 'POST', BATCH_TIMEOUT);
    notify(`已事前登記並排入 ${result.created} 案。進度在頁面最上方「正式實驗」。`);
  } else if (action === 'enqueue') {
    const url = `/api/studies/${encodeURIComponent(plan.protocol_hash)}/enqueue`;
    // Prefer the case list saved at registration; older registrations need this plan's list.
    let result;
    try { result = await api(url, undefined, 'POST', BATCH_TIMEOUT); }
    catch (error) {
      // Only a registration without a saved case list falls back to this plan's list; show anything else.
      if (!String(error.message).includes('沒有保存案例清單')) throw error;
      result = await api(url, payload, 'POST', BATCH_TIMEOUT);
    }
    notify(`已排入 ${result.created} 案${result.skipped_existing ? `，略過已建立的 ${result.skipped_existing} 案` : ''}。`);
  } else {
    if (!window.confirm(`排入 ${plan.ready} 個案例但不事前登記？這批結果只算探索性分析。`)) return;
    const ids = await api('/api/batches', payload, 'POST', BATCH_TIMEOUT);
    notify(`已排入 ${ids.length} 案（探索性，未登記）。`);
  }
  lastPlan = null;
  $('plan-result').innerHTML = '';
  window.scrollTo({top: 0, behavior: 'smooth'});
}

function renderCollect(t) {
  const el = $('batch-collect-progress');
  if (!t || t.stage === 'idle') { el.textContent = ''; return false; }
  const failed = t.failed?.length ? `；${t.failed.length} 案失敗：${t.failed.slice(0, 5).map(f => `${f.ticker} ${f.analysis_date}（${f.message}）`).join('、')}${t.failed.length > 5 ? ' …' : ''}` : '';
  el.textContent = t.stage === 'running'
    ? `進行中 ${t.done}/${t.total}（重用 ${t.reused}、新建 ${t.created}）· 目前 ${t.current || '—'}${failed}`
    : `完成 ${t.done}/${t.total}：重用 ${t.reused}、新建 ${t.created}${failed || '，全部成功'}`;
  return t.stage === 'running';
}

async function pollCollect(onDone) {
  clearTimeout(collectTimer);
  const running = renderCollect(await api('/api/collections/batch'));
  $('batch-collect-button').disabled = running;
  if (running) collectTimer = setTimeout(() => task(null, () => pollCollect(onDone)), 3000);
  else await onDone();
}

export function initBatchPanel(config, onDatasetsChanged, onQueued) {
  // The configured model is usable right away; the Ollama probe may take a while (e.g. GPU off).
  $('plan-model').innerHTML = `<option value="${escape(config.model)}">${escape(config.model)}</option>`;
  collectPicker = mountCasePicker($('collect-picker'), config, {name: 'collect'});
  planPicker = mountCasePicker($('plan-picker'), config, {name: 'plan'});
  document.addEventListener('click', e => {
    const exp = e.target.closest('[data-exp-mode]');
    if (exp) switchMode('data-exp-mode', 'data-mode-panel', exp.dataset.expMode);
    const data = e.target.closest('[data-data-mode]');
    if (data) switchMode('data-data-mode', 'data-data-panel', data.dataset.dataMode);
    const action = e.target.closest('[data-plan-action]');
    if (action && lastPlan) task(action, async () => { await planAction(action.dataset.planAction); await onQueued(); });
  });
  $('plan-picker').addEventListener('picker:change', () => { lastPlan = null; $('plan-result').innerHTML = ''; });
  $('plan-form').addEventListener('submit', e => {
    e.preventDefault();
    task(e.submitter, async () => {
      const settings = planSettings();
      if (!settings.tickers.length || !settings.dates.length) throw new Error('請至少選一檔股票與一個分析日');
      if (!settings.model) throw new Error('請選擇模型');
      $('plan-result').innerHTML = `<p class="hint">正在檢查 ${settings.tickers.length * settings.dates.length} 個案例的資料集…（180 案約 5–30 秒）</p>`;
      try { lastPlan = await api('/api/studies/plan', settings, 'POST', BATCH_TIMEOUT); }
      catch (error) { $('plan-result').innerHTML = ''; throw error; }
      renderPlan(lastPlan);
    });
  });
  $('batch-collect-form').addEventListener('submit', e => {
    e.preventDefault();
    const tickers = collectPicker.tickers(), dates = collectPicker.dates();
    if (!tickers.length || !dates.length) { notify('請至少選一檔股票與一個分析日', true); return; }
    if ($('batch-collect-refresh').checked && !window.confirm(`強制重新下載 ${tickers.length * dates.length} 個案例？這會消耗資料來源的 API 額度（Alpha Vantage 免費版每天 25 次）。`)) return;
    task(e.submitter, async () => {
      const started = await api('/api/collections/batch', {tickers, dates, use_finbert: $('batch-collect-finbert').checked,
        refresh: $('batch-collect-refresh').checked, design: 'quarterly'});
      if (started.joined) notify('已有一批資料集正在建立；這次的選擇沒有啟動，請等目前這批完成後再按一次。', true);
      await pollCollect(onDatasetsChanged);
    });
  });
  task(null, () => pollCollect(async () => {}));  // resume the progress line after a page reload
  // The demo has one synthetic case, so it starts on the single-case forms.
  if (config.demo_mode) showSingleCase();
}

// Picking one dataset (e.g. after collecting it) means the single-case flow.
export function showSingleCase() {
  switchMode('data-exp-mode', 'data-mode-panel', 'single');
  switchMode('data-data-mode', 'data-data-panel', 'single');
}

// Keep the batch model picker in step with the single-case one (filled from /api/models).
export function syncPlanModels() {
  const chosen = $('plan-model').value;
  $('plan-model').innerHTML = $('model').innerHTML;
  // Keep the user's choice if it is still offered; otherwise follow the single-case picker.
  $('plan-model').value = [...$('plan-model').options].some(o => o.value === chosen) ? chosen : $('model').value;
}
