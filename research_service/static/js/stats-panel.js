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

// Pre-registered companion analysis: results before, across and after the
// model's knowledge cutoff, so memory-driven accuracy is visible.
const SEGMENT_LABELS = {before_cutoff: '截止日前（可能記得結果）', straddles_cutoff: '跨越截止日', after_cutoff: '截止日後（樣本外）'};
function knowledgeCutoffBlock(k) {
  if (!k) return '';
  if (k.status !== 'cutoff_recorded') return `<section class="stats-substep"><div class="section-label">4.1b / 模型知識截止日</div><p class="hint">這個模型沒有登記知識截止日，無法分辨哪些案例模型可能已經知道結果。</p></section>`;
  const cutoffs = Object.entries(k.cutoffs || {}).filter(([, v]) => v).map(([m, v]) => `${escape(m)}：${escape(v.cutoff)}`).join('、');
  const head = Object.keys(SEGMENT_LABELS).map(name => `<th>${SEGMENT_LABELS[name]}<br><small>${k.segments[name]?.cases || 0} 個案例</small></th>`).join('');
  const body = Object.entries(k.by_group).map(([group, item]) => `<tr><td>${escape(group)}</td>${Object.keys(SEGMENT_LABELS).map(name => `<td>${percentage(item.selective_accuracy[name])}</td>`).join('')}<td>${item.after_minus_before == null ? '—' : `${(item.after_minus_before * 100).toFixed(1)} pt`}</td></tr>`).join('');
  return `<section class="stats-substep"><div class="section-label">4.1b / 模型知識截止日前後</div><p class="hint">知識截止日：${cutoffs}。${escape(k.note)}</p><div class="table-wrap"><table><thead><tr><th>方法</th>${head}<th>後 − 前</th></tr></thead><tbody>${body}</tbody></table></div><p class="hint">表內為有下注時的方向準確率（60 日、扣成本）。</p></section>`;
}

function completionBlock(c) {
  if (!c) return '';
  if (c.target_cases == null) return `<section class="stats-substep"><div class="section-label">完成狀態（不同門檻）</div><p class="hint">目前沒有可辨識的實驗協議與事前登記目標，無法判定整批完成；達到最低統計案例數也不代表正式樣本完整。</p></section>`;
  const formal = c.formal_sample_status === 'complete' ? '完整' : c.formal_sample_status === 'not_preregistered' ? '尚未事前登記' : '未完整';
  const quality = c.quality_status === 'passed_for_all_completed' ? '目前完成案例皆通過' : c.quality_status === 'has_exclusions' ? `有排除（${c.quality_excluded_completed_cases ?? 0} 案）` : '尚無可判定案例';
  return `<section class="stats-substep"><div class="section-label">完成狀態（不同門檻）</div><div class="table-wrap"><table><thead><tr><th>工作執行</th><th>品質條件</th><th>事前登記樣本</th><th>可做統計</th></tr></thead><tbody><tr><td>${c.work_completed_cases}/${c.target_cases} 案${c.work_complete ? ' · 全部工作完成' : ' · 尚未全數完成'}</td><td>${escape(quality)} · ${c.quality_passed_cases} 案</td><td>${escape(formal)}${c.formal_sample_complete ? ` · ${c.target_cases}/${c.target_cases}` : ''}</td><td>${c.inference_ready ? '達最低統計門檻' : `未達 ${c.inference_minimum_cases ?? 30} 案`}</td></tr></tbody></table></div><p class="hint">「達最低統計門檻」不代表整批工作完成或正式樣本完整。</p></section>`;
}

function dateClusterBlock(comparisons, primaryHorizon) {
  const rows = (comparisons || []).filter(item => item.horizon === primaryHorizon && item.cost_model === 'corwin_schultz' && item.decision_layer === 'candidate' && item.portfolio_basis === 'all');
  const records = rows.flatMap(item => {
    const sensitivity = item.date_cluster_direction_sensitivity;
    return (sensitivity?.by_block_length || []).map(block => ({item, sensitivity, block}));
  }).filter(row => row.block.status === 'ok');
  if (!records.length) return '';
  const body = records.map(({item, sensitivity, block}) => `<tr><td>D vs ${escape(item.groups?.[1] || '')}</td><td>${block.block_length_dates}</td><td>${sensitivity.n_dates}</td><td>${sensitivity.n_pairs}</td><td>${percentage(sensitivity.estimate)}</td><td>${percentage(block.confidence_interval?.[0])} – ${percentage(block.confidence_interval?.[1])}</td></tr>`).join('');
  return `<section class="stats-substep"><div class="section-label">日期群聚／連續日期區塊敏感度</div><p class="hint">方向準確率差（D 減比較組）的配對日期區塊 bootstrap 95% percentile 區間；依日期整組重抽，並以較長連續日期區塊保留部分時間相依。這是敏感度區間，不是另一個顯著性 p 值；季度只有 20 個日期群聚，需保守解讀。</p><div class="table-wrap"><table><thead><tr><th>比較</th><th>區塊（日期）</th><th>日期群聚</th><th>配對方向案例</th><th>差值</th><th>95% 區間</th></tr></thead><tbody>${body}</tbody></table></div></section>`;
}

function temporalSplitBlock(result) {
  if (!result?.splits) return '';
  const body = Object.entries(result.splits).flatMap(([name, split]) => Object.entries(split.by_group || {}).map(([group, item]) => `<tr><td>${escape(split.label || name)}</td><td>${escape(group)}</td><td>${split.completed_cases}/${split.target_cases}</td><td>${item.directional_cases}/${item.cases}</td><td>${percentage(item.coverage)}</td><td>${percentage(item.selective_accuracy)}</td><td>${item.mean_net_return == null ? '—' : percentage(item.mean_net_return)}</td></tr>`)).join('');
  return `<section class="stats-substep"><div class="section-label">Training／Validation／Test 分開呈現</div><p class="hint">各年度區段僅報描述統計，分母與下注覆蓋分開列示；Test 僅供最終評估，不用於調參。</p><div class="table-wrap"><table><thead><tr><th>切分</th><th>方法</th><th>完成/目標</th><th>有方向案例</th><th>覆蓋率</th><th>條件準確率</th><th>平均成本後報酬</th></tr></thead><tbody>${body}</tbody></table></div></section>`;
}

function numericQualityBlock(q) {
  if (!q || q.status !== 'available') return '';
  const body = Object.entries(q.strata || {}).map(([name, stratum]) => `<tr><td>${name === 'redaction' ? '移除數字或丟棄數字主張' : '無數字修補'}</td><td>${stratum.cases}</td>${['A', 'B', 'C', 'D'].map(group => `<td>${stratum.by_group?.[group]?.cases ? `${percentage(stratum.by_group[group].selective_accuracy)} · ${stratum.by_group[group].directional_cases}/${stratum.by_group[group].cases}` : '—'}</td>`).join('')}</tr>`).join('');
  return `<section class="stats-substep"><div class="section-label">數字驗證品質分層</div><p class="hint">${q.redacted_cases} 個案例、${q.redacted_calls} 個決策呼叫曾移除數字或丟棄數字主張（${q.redacted_numeric_tokens} 個數字、${q.removed_numeric_claims || 0} 項主張）。分層是品質／選擇診斷，不證明修補是否改變決策。</p><div class="table-wrap"><table><thead><tr><th>品質層</th><th>案例數</th><th>A 準確率 · n</th><th>B 準確率 · n</th><th>C 準確率 · n</th><th>D 準確率 · n</th></tr></thead><tbody>${body}</tbody></table></div></section>`;
}

function sentimentCoverageBlock(report) {
  const coverage = report.sentiment_coverage;
  if (!coverage) return '';
  const rows = coverage.by_ticker_year.map(item => {
    const target = item.scopes.target, context = item.scopes.context;
    const sourceText = Object.entries(target.source_counts || {}).map(([name, values]) => `${escape(name)} ${values.scored_count}/${values.headline_count}`).join('；') || '無';
    const contextSourceText = Object.entries(context.source_counts || {}).map(([name, values]) => `${escape(name)} ${values.scored_count}/${values.headline_count}`).join('；') || '無';
    return `<tr><td>${escape(item.ticker)}</td><td>${escape(item.year)}</td><td>${item.coverage_recorded_cases}/${item.cases}</td><td>${item.window_days == null ? '未記錄' : `${item.window_days} 日`}</td><td>${target.scored_count}/${target.headline_count}</td><td>${percentage(target.missing_score_rate)}</td><td>${target.indicator_cases}/${item.coverage_recorded_cases}</td><td>${sourceText}</td><td>${context.scored_count}/${context.headline_count}</td><td>${contextSourceText}</td></tr>`;
  }).join('');
  const coverageNote = coverage.status === 'available'
    ? `${coverage.cases_with_coverage} 案有窗口覆蓋紀錄、${coverage.cases_without_coverage || 0} 案未記錄`
    : `所有 ${coverage.cases_without_coverage || 0} 案均未記錄窗口覆蓋；這不等於窗口內沒有新聞`;
  return `<section class="stats-substep"><div class="section-label">全量 FinBERT 新聞覆蓋與缺失</div><p class="hint">${coverageNote}；依股票與年份列出窗口內新聞數、缺分率、指標產生率及目標／背景來源組成。</p><details><summary>展開股票 × 年份覆蓋表</summary><div class="table-wrap"><table><thead><tr><th>股票</th><th>年份</th><th>覆蓋紀錄/案例</th><th>窗口</th><th>目標：已評分/新聞數</th><th>目標缺分率</th><th>產生指標/覆蓋案例</th><th>目標來源：已評分/新聞數</th><th>背景：已評分/新聞數</th><th>背景來源：已評分/新聞數</th></tr></thead><tbody>${rows}</tbody></table></div></details></section>`;
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
  const primaryHorizon = report.primary_horizon || 60;
  const primary = report.summary.filter(r => r.horizon === primaryHorizon && r.cost_model === 'corwin_schultz' && r.decision_layer === 'candidate' && r.portfolio_basis === 'all');
  const completionStatus = report.completion;
  const completed = completionStatus?.work_completed_cases ?? report.unique_cases ?? 0;
  const target = completionStatus?.target_cases;
  const quality = completionStatus?.quality_passed_cases ?? 0;
  const batchComplete = Boolean(completionStatus?.work_complete && completionStatus?.formal_sample_complete);
  const progressText = target == null ? `${completed} 案；品質合格 ${quality} 案` : `${completed}/${target} 案；品質合格 ${quality} 案`;
  flow.set('stats', {status: batchComplete ? 'done' : 'warn', sub: progressText});
  const insufficient = report.status === 'insufficient_cases' ? `<p class="protocol-warning">目前只有 ${report.unique_cases || 0} 個完成的案例，至少要 ${report.required_cases || 30} 個才會計算統計檢定。</p>` : '';
  const prereg = report.preregistration;
  const preregBlock = prereg
    ? `<p class="${prereg.post_freeze_dataset_ids.length ? 'protocol-warning' : 'hint'}">研究樣本已於 ${escape(formatStamp(prereg.frozen_at))} 鎖定（事前登記），共 ${prereg.dataset_ids.length} 個資料集。${prereg.post_freeze_dataset_ids.length ? `⚠️ 鎖定後又追加了 ${prereg.post_freeze_dataset_ids.length} 個資料集的實驗；這些是看過結果後才加入的，不應算進正式結論。` : '目前所有案例都在鎖定的樣本內。'}</p>`
    : `<p class="hint">尚未鎖定研究樣本（事前登記）。正式實驗要在執行前鎖定：到「建立實驗」的批次研究匯入案例清單，並勾選「先鎖定這批研究樣本」。只有鎖定後建立的實驗算正式結果；已經跑完的結果即使之後鎖定，也只算探索性分析，避免看了結果才挑樣本。</p>`;
  const completion = completionBlock(report.completion);
  const directionBlocks = dateClusterBlock(report.comparisons, primaryHorizon);
  const splits = temporalSplitBlock(report.temporal_split_results);
  const numericQuality = numericQualityBlock(report.numeric_validation_quality);
  const newsCoverage = sentimentCoverageBlock(report);
  element.innerHTML = `<section class="stats-substep"><div class="section-label">4.1 / 回測摘要</div><h2>同協議研究比較</h2><p class="hint">只比較用同一套研究規則（同協議版本）跑出的結果。以下為 ${primaryHorizon} 個交易日、扣除估計交易成本（Corwin–Schultz）、各案例等權重的結果，共 ${report.unique_cases || 0} 個完成的案例；同一案例重跑的紀錄會保留但不重複計算。</p>${insufficient}${preregBlock}
    <div class="chart-pair">${comparisonBars(primary, 'selective_accuracy', '有下注時的方向準確率', percentage)}${comparisonBars(primary, 'sharpe', 'Sharpe', number)}</div>
    <div class="table-wrap"><table><thead><tr><th>方法</th><th>下注比例</th><th>有下注時準確率</th><th>Hold 比例</th><th>Sharpe</th><th>總報酬</th></tr></thead><tbody>${primary.map(r => `<tr><td>${escape(r.group)}</td><td>${percentage(r.coverage)}</td><td>${percentage(r.selective_accuracy)}</td><td>${percentage(r.hold_rate)}</td><td>${number(r.sharpe)}</td><td>${percentage(r.total_return)}</td></tr>`).join('')}</tbody></table></div></section>
    ${completion}${directionBlocks}${splits}${numericQuality}${newsCoverage}${knowledgeCutoffBlock(report.knowledge_cutoff)}
    <section class="stats-substep"><div class="section-label">4.2 / 品質與匯出</div><p class="hint">試跑檢查（pilot）：${pilot.verdict === 'proceed' ? '通過，可以開始正式批次' : pilot.verdict === 'blocked' ? '尚未通過' : '—'}。這是正式批次前的健檢，用來確認各組結果沒有異常（例如全部都 Hold）。「Hold 門檻」的敏感度分析是用既有預測重算，不會重新呼叫模型。</p>${pilotReasons(pilot.blocking_reasons)}<div class="actions"><a href="/api/studies/${protocol}/summary.csv">下載摘要表（summary.csv）</a><a href="/api/studies/${protocol}" download="statistics.json">下載完整統計（statistics.json）</a></div></section>
    <section class="stats-substep"><div class="section-label">4.3 / 詳細稽核</div><details><summary>試跑檢查、門檻、切分、新聞與數字品質（原始數據）</summary>${copyablePre(JSON.stringify({pilot, hold_band: band, completeness: report.completeness, completion: report.completion, temporal_split_results: report.temporal_split_results, numeric_validation_quality: report.numeric_validation_quality, sentiment_coverage: report.sentiment_coverage}, null, 2))}</details><details><summary>統計檢定結果與計算方式（原始數據）</summary>${copyablePre(JSON.stringify({comparisons: report.comparisons, conventions: report.conventions}, null, 2))}</details></section>`;
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
