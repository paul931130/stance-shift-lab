// Step 4 · statistics for the selected run's protocol.
import { $, escape, percentage, number, formatStamp } from './ui.js';
import { state, on } from './store.js';
import { api, task } from './api.js';
import { flow } from './flow.js';
import { setTab } from './nav.js';

const GROUP_TONES = {A: 'a', B: 'b', C: 'c', D: 'd'};
let loadedFor = null;

// Horizontal bars make the A/B/C/D comparison readable at a glance; the
// table below keeps the exact values.
function comparisonBars(rows, key, label, format) {
  const values = rows.map(r => r[key]).filter(v => typeof v === 'number' && Number.isFinite(v));
  if (!values.length) return '';
  const max = Math.max(...values.map(Math.abs)) || 1;
  return `<figure class="bar-chart"><figcaption>${label}</figcaption>${rows.map(r => {
    const value = r[key], width = typeof value === 'number' ? Math.round((Math.abs(value) / max) * 100) : 0;
    return `<div class="bar-row"><span class="bar-key tone-${GROUP_TONES[r.group] || 'a'}">${escape(r.group)}</span><span class="bar-track"><i class="tone-${GROUP_TONES[r.group] || 'a'}${value < 0 ? ' negative' : ''}" data-width="${width}"></i></span><span class="bar-value">${format(value)}</span></div>`;
  }).join('')}</figure>`;
}

export async function showStatistics() {
  if (!state.selectedProtocol) return;
  loadedFor = state.selectedProtocol;
  setTab('stats');
  const protocol = state.selectedProtocol;
  const [report, pilot, band] = await Promise.all([
    api(`/api/studies/${protocol}`), api(`/api/studies/${protocol}/pilot`), api(`/api/studies/${protocol}/hold-band`),
  ]);
  const element = $('statistics');
  const primary = report.summary.filter(r => r.horizon === 60 && r.cost_model === 'corwin_schultz' && r.decision_layer === 'candidate' && r.portfolio_basis === 'all');
  flow.set('stats', {status: report.status === 'insufficient_cases' ? 'warn' : 'done', sub: `${report.unique_cases || 0} 個案例`});
  const insufficient = report.status === 'insufficient_cases' ? `<p class="protocol-warning">樣本數 ${report.unique_cases || 0} / ${report.required_cases || 30} 不足，尚未產出任何統計檢定。</p>` : '';
  const prereg = report.preregistration;
  const preregBlock = prereg
    ? `<p class="${prereg.post_freeze_dataset_ids.length ? 'protocol-warning' : 'hint'}">Preregistration 已於 ${escape(formatStamp(prereg.frozen_at))} 凍結，涵蓋 ${prereg.dataset_ids.length} 個資料集。${prereg.post_freeze_dataset_ids.length ? `⚠️ 凍結後又新增了 ${prereg.post_freeze_dataset_ids.length} 個資料集的實驗，這些案例不應計入凍結後的正式分析結論。` : '目前所有案例都在凍結範圍內。'}</p>`
    : `<p class="hint">尚未凍結 preregistration。凍結後會鎖住目前已分析的資料集清單，之後新增的案例會被標記，避免看完結果後偷偷擴大樣本。</p><button class="quiet" type="button" data-freeze="${escape(protocol)}">凍結目前的 preregistration</button>`;
  element.innerHTML = `<section class="stats-substep"><div class="section-label">4.1 / 回測摘要</div><h2>同協議研究比較</h2><p class="hint">候選決策、60 日、Corwin–Schultz、固定權重投組。${report.unique_cases || 0} 個已完成案例；後續重跑保留供稽核。</p>${insufficient}${preregBlock}
    <div class="chart-pair">${comparisonBars(primary, 'selective_accuracy', '條件準確率', percentage)}${comparisonBars(primary, 'sharpe', 'Sharpe', number)}</div>
    <div class="table-wrap"><table><thead><tr><th>方法</th><th>覆蓋率</th><th>條件準確率</th><th>Hold</th><th>Sharpe</th><th>總報酬</th></tr></thead><tbody>${primary.map(r => `<tr><td>${escape(r.group)}</td><td>${percentage(r.coverage)}</td><td>${percentage(r.selective_accuracy)}</td><td>${percentage(r.hold_rate)}</td><td>${number(r.sharpe)}</td><td>${percentage(r.total_return)}</td></tr>`).join('')}</tbody></table></div></section>
    <section class="stats-substep"><div class="section-label">4.2 / 品質與匯出</div><p class="hint">Pilot：${escape(pilot.verdict || '—')} · ${escape((pilot.blocking_reasons || []).join(' / ') || '無阻擋原因')}。中性帶敏感性已用既有預測重算，不重新呼叫模型。</p><div class="actions"><a href="/api/studies/${protocol}/summary.csv">下載 summary.csv</a><a href="/api/studies/${protocol}" download="statistics.json">下載 statistics.json</a></div></section>
    <section class="stats-substep"><div class="section-label">4.3 / 詳細稽核</div><details><summary>Pilot、hold band 與完整性診斷</summary><pre>${escape(JSON.stringify({pilot, hold_band: band, completeness: report.completeness}, null, 2))}</pre></details><details><summary>統計檢定與口徑</summary><pre>${escape(JSON.stringify({comparisons: report.comparisons, conventions: report.conventions}, null, 2))}</pre></details></section>`;
  requestAnimationFrame(() => { for (const bar of element.querySelectorAll('.bar-track i')) bar.style.width = `${bar.dataset.width}%`; });
}

// Opening the statistics step loads the selected run's protocol automatically.
on('tab:changed', tab => {
  if (tab === 'stats' && state.selectedProtocol && loadedFor !== state.selectedProtocol) task(null, showStatistics);
});

document.addEventListener('click', e => {
  const b = e.target.closest('button[data-freeze]');
  if (!b) return;
  task(b, async () => {
    if (!window.confirm('凍結此協議目前分析的資料集清單？凍結後不可撤銷，之後新增的案例會被標記為凍結後追加。')) return;
    await api(`/api/studies/${b.dataset.freeze}/freeze`, {});
    await showStatistics();
  });
});
