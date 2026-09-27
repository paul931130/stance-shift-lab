// Step 4 · statistics for the selected run's protocol.
import { $, escape, percentage, number, formatStamp, copyablePre } from './ui.js';
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
  const insufficient = report.status === 'insufficient_cases' ? `<p class="protocol-warning">目前只有 ${report.unique_cases || 0} 個完成的案例，至少要 ${report.required_cases || 30} 個才會計算統計檢定。</p>` : '';
  const prereg = report.preregistration;
  const preregBlock = prereg
    ? `<p class="${prereg.post_freeze_dataset_ids.length ? 'protocol-warning' : 'hint'}">研究樣本已於 ${escape(formatStamp(prereg.frozen_at))} 鎖定（事前登記），共 ${prereg.dataset_ids.length} 個資料集。${prereg.post_freeze_dataset_ids.length ? `⚠️ 鎖定後又追加了 ${prereg.post_freeze_dataset_ids.length} 個資料集的實驗；這些是看過結果後才加入的，不應算進正式結論。` : '目前所有案例都在鎖定的樣本內。'}</p>`
    : `<p class="hint">尚未鎖定研究樣本（事前登記）。正式實驗開始、還沒看統計結果之前按一次：會記下目前要分析的資料集清單，之後才加入的案例都會被標記，證明樣本不是看了結果才挑的。測試階段不需要按，而且按了不能撤銷。</p><button class="quiet" type="button" data-freeze="${escape(protocol)}">鎖定目前的研究樣本</button>`;
  element.innerHTML = `<section class="stats-substep"><div class="section-label">4.1 / 回測摘要</div><h2>同協議研究比較</h2><p class="hint">只比較用同一套研究規則（同協議版本）跑出的結果。以下為 60 個交易日、扣除估計交易成本（Corwin–Schultz）、各案例等權重的結果，共 ${report.unique_cases || 0} 個完成的案例；同一案例重跑的紀錄會保留但不重複計算。</p>${insufficient}${preregBlock}
    <div class="chart-pair">${comparisonBars(primary, 'selective_accuracy', '有下注時的方向準確率', percentage)}${comparisonBars(primary, 'sharpe', 'Sharpe', number)}</div>
    <div class="table-wrap"><table><thead><tr><th>方法</th><th>下注比例</th><th>有下注時準確率</th><th>Hold 比例</th><th>Sharpe</th><th>總報酬</th></tr></thead><tbody>${primary.map(r => `<tr><td>${escape(r.group)}</td><td>${percentage(r.coverage)}</td><td>${percentage(r.selective_accuracy)}</td><td>${percentage(r.hold_rate)}</td><td>${number(r.sharpe)}</td><td>${percentage(r.total_return)}</td></tr>`).join('')}</tbody></table></div></section>
    <section class="stats-substep"><div class="section-label">4.2 / 品質與匯出</div><p class="hint">試跑檢查（pilot）：${pilot.verdict === 'proceed' ? '通過，可以開始正式批次' : pilot.verdict === 'blocked' ? '尚未通過' : '—'}。這是正式批次前的健檢，用來確認各組結果沒有異常（例如全部都 Hold）。「Hold 門檻」的敏感度分析是用既有預測重算，不會重新呼叫模型。</p>${pilotReasons(pilot.blocking_reasons)}<div class="actions"><a href="/api/studies/${protocol}/summary.csv">下載摘要表（summary.csv）</a><a href="/api/studies/${protocol}" download="statistics.json">下載完整統計（statistics.json）</a></div></section>
    <section class="stats-substep"><div class="section-label">4.3 / 詳細稽核</div><details><summary>試跑檢查、Hold 門檻與資料完整性（原始數據）</summary>${copyablePre(JSON.stringify({pilot, hold_band: band, completeness: report.completeness}, null, 2))}</details><details><summary>統計檢定結果與計算方式（原始數據）</summary>${copyablePre(JSON.stringify({comparisons: report.comparisons, conventions: report.conventions}, null, 2))}</details></section>`;
  requestAnimationFrame(() => { for (const bar of element.querySelectorAll('.bar-track i')) bar.style.width = `${bar.dataset.width}%`; });
}

// Pilot blocking codes come from reporting.pilot_diagnostics; the codes stay in
// exports, the page shows what each one means.
const PILOT_REASONS = {
  no_completed_cases: () => '還沒有完成的案例',
  hold_rate_too_high: g => `${g} 組 Hold 比例超過 40%，模型太常不表態`,
  insufficient_D_vs_A_disagreement: () => 'D 組與 A 組的決策太常相同（不同的比例低於 20%），看不出立場交換的效果',
  arms_not_identifiable: () => '超過 60% 的案例四組決策完全相同，各組差異無法區分',
  self_consistency_arm_degenerate: () => 'B 組多次投票幾乎總是一致（超過 95%），投票沒有發揮作用',
  forecast_variance_collapsed: g => `${g} 組預測報酬幾乎都一樣（標準差低於 0.5 個百分點）`,
  directional_calls_worse_than_chance: g => `${g} 組明確看多／看空時，方向準確率低於 45%`,
  narrative_forecast_mismatch: g => `${g} 組超過 30% 的決策與自己預測的報酬方向不一致`,
};
function pilotReasons(reasons) {
  if (!reasons?.length) return '';
  const items = reasons.map(code => {
    const [key, group] = code.split(':');
    const text = PILOT_REASONS[key] ? PILOT_REASONS[key](group) : code;
    return `<li>${escape(text)}</li>`;
  });
  const note = reasons.includes('no_completed_cases') ? '' : '<p class="hint">這些條件用來判斷樣本是否足以區分四組；展示模式或案例很少時通常不會通過。</p>';
  return `<ul class="pilot-reasons">${items.join('')}</ul>${note}`;
}

// Opening the statistics step loads the selected run's protocol automatically.
on('tab:changed', tab => {
  if (tab === 'stats' && state.selectedProtocol && loadedFor !== state.selectedProtocol) task(null, showStatistics);
});

document.addEventListener('click', e => {
  const b = e.target.closest('button[data-freeze]');
  if (!b) return;
  task(b, async () => {
    if (!window.confirm('鎖定目前的研究樣本？\n\n會記下這個協議版本目前已分析的資料集清單。之後新加入的案例會被標記為「鎖定後追加」，不算進正式結論。\n\n此動作不能撤銷；測試階段請不要按。')) return;
    await api(`/api/studies/${b.dataset.freeze}/freeze`, {});
    await showStatistics();
  });
});
