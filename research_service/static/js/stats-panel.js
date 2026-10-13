// Step 4 · statistics for the selected run's protocol.
import { $, escape, percentage, number, formatStamp, copyablePre } from './ui.js';
import { state, on } from './store.js';
import { api, task } from './api.js';
import { flow } from './flow.js';
import { setTab } from './nav.js';
import { rqStatsSection } from './rq-stats.js';

const GROUP_TONES = {A: 'a', B: 'b', C: 'c', D: 'd'};
const GROUP_NAMES = {A: '單次判斷', B: '獨立投票', C: '固定立場辯論', D: '立場交換辯論'};
const BENCHMARK = 'BuyAndHoldActiveWindows';
let loadedFor = null;

const points = value => value == null ? '—' : `${value >= 0 ? '+' : '−'}${Math.abs(value * 100).toFixed(1)}`;
const signed = value => value == null ? '—' : `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(2)}`;
const pvalue = value => value == null ? '—' : Number(value).toFixed(2);
const pct2 = value => value == null ? '—' : `${(value * 100).toFixed(2)}%`;
const sharpe2 = value => value == null ? '—' : Number(value).toFixed(2);

// Report table「四組績效」: candidate decisions, primary horizon, net of cost,
// with the same-window buy-and-hold reference as its own row.
function performanceTable(primary, benchmark, horizon) {
  const row = r => `<tr><th scope="row"><span class="group-chip tone-${GROUP_TONES[r.group]}">${escape(r.group)}</span>${escape(GROUP_NAMES[r.group] || r.group)}</th><td>${percentage(r.coverage)}</td><td>${percentage(r.selective_accuracy)}</td><td>${pct2(r.total_return)}</td><td>${pct2(r.max_drawdown)}</td><td>${r.sharpe == null ? '—' : r.sharpe.toFixed(2)}</td></tr>`;
  const reference = benchmark ? `<tr class="reference-row"><th scope="row">買進持有（同案同期間）</th><td>—</td><td>—</td><td>${pct2(benchmark.total_return)}</td><td>${pct2(benchmark.max_drawdown)}</td><td>${benchmark.sharpe == null ? '—' : benchmark.sharpe.toFixed(2)}</td></tr>` : '';
  return `<div class="table-wrap"><table class="report-table"><caption>四組績效（${horizon} 個交易日，扣除交易成本）</caption><thead><tr><th>組別</th><th>出手率</th><th>條件準確率</th><th>累積報酬</th><th>最大回撤</th><th>年化 Sharpe</th></tr></thead><tbody>${primary.map(row).join('')}${reference}</tbody></table></div>
    <p class="hint">決策為守門員之前之候選決策。出手率為買進或賣出（非持有）之比例；條件準確率以有出手之案例計算。組合將每個「股票×分析日」案例視為固定權重之部位，僅於該案持有期間依決策做多或放空，其餘時間以零報酬現金計。買進持有參照採相同配置，於每案相同期間做多該股票。</p>`;
}

// Report table「立場交換組之配對檢定」: D against C (primary), B and A.
function pairedTestsTable(comparisons, horizon, primaryInference) {
  const rows = ['C', 'B', 'A'].map(group => (comparisons || []).find(item => item.groups?.[1] === group && item.horizon === horizon
    && item.cost_model === 'corwin_schultz' && item.decision_layer === 'candidate' && item.portfolio_basis === 'all')).filter(Boolean);
  if (!rows.length) return '';
  const body = rows.map(item => {
    const m = item.mcnemar || {}, lw = item.ledoit_wolf || {}, group = item.groups[1];
    return `<tr${group === 'C' ? ' class="primary-row"' : ''}><th scope="row">D 對 ${escape(group)}${group === 'C' ? '（主要）' : ''}</th><td>${m.n ?? '—'}</td><td>${m.discordant ?? '—'}</td><td>${points(m.accuracy_difference)}</td><td>${pvalue(m.pvalue)}</td><td>${signed(lw.annualized_difference)}</td><td>${pvalue(lw.pvalue)}</td></tr>`;
  }).join('');
  const holm = (primaryInference?.endpoints || []).map(item => `${item.endpoint === 'direction_accuracy' ? '準確率' : 'Sharpe'} ${pvalue(item.holm_pvalue)}`).join('、');
  return `<div class="table-wrap"><table class="report-table"><caption>立場交換組（D）之配對檢定（${horizon} 個交易日）</caption><thead><tr><th>比較</th><th>配對案例</th><th>方向不同</th><th>準確率差</th><th>McNemar p</th><th>Sharpe 差</th><th>Ledoit–Wolf p</th></tr></thead><tbody>${body}</tbody></table></div>
    <p class="hint">準確率差單位為百分點。${holm ? `主要比較經 Holm 校正後之 p 值為 ${holm}。` : ''}與 A、B 之比較以兩組皆出手之案例計算。</p>`;
}

// Verdict against the preregistered success rule, phrased the way the report
// states it: not reaching superiority is not evidence of equivalence.
function verdictBlock(result, ready) {
  if (!ready || !result) return `<div class="verdict pending"><b>尚未判定</b><p>主要比較需要足夠的完成案例與可估計的兩個端點；目前僅能檢視描述統計。</p></div>`;
  if (result.success === true) return `<div class="verdict pass"><b>達到預先指定之優越性判準</b><p>D 對 C 之方向準確率與年化 Sharpe 差皆為正，且經 Holm 校正後 p &lt; ${result.alpha}。仍屬鎖定規則下之結果，需搭配敏感性分析解讀。</p></div>`;
  if (result.success === false) return `<div class="verdict fail"><b>未達預先指定之優越性判準</b><p>不支持立場交換辯論（D）優於固定立場辯論（C）。未事前訂定等效／非劣性界值，故不能由未顯著推論兩組等效。</p></div>`;
  return `<div class="verdict pending"><b>主要端點尚未全部可估計</b><p>${escape(result.note || '請檢查完成案例數與資料品質。')}</p></div>`;
}

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

function primaryInferenceBlock(result) {
  if (!result) return '';
  const rows = (result.endpoints || []).map(item => {
    const effect = item.endpoint === 'direction_accuracy'
      ? percentage(item.effect_difference) : number(item.effect_difference);
    const label = item.endpoint === 'direction_accuracy' ? '方向準確率差（D − C）' : '年化 Sharpe 差（D − C）';
    return `<tr><td>${label}</td><td>${effect}</td><td>${item.pvalue == null ? '不可估計' : number(item.pvalue)}</td><td>${item.holm_pvalue == null ? '—' : number(item.holm_pvalue)}</td></tr>`;
  }).join('');
  const verdict = result.success === true ? '兩個主要端點都達到預先指定條件'
    : result.success === false ? '未達到預先指定的共同成功條件'
      : '主要端點尚未全部可估計';
  return `<section class="stats-substep"><div class="section-label">預先指定的主要假說（D 對 C，Holm 校正）</div><p class="hint">${escape(verdict)}。D 對 C；方向準確率與年化 Sharpe 差皆須為正，且同一個兩端點 family 經 Holm 校正後 p &lt; ${result.alpha}。${escape(result.note || '')}</p><div class="table-wrap"><table><thead><tr><th>端點</th><th>差值</th><th>原始 p</th><th>Holm p</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
}

function numericQualityBlock(q) {
  if (!q || q.status !== 'available') return '';
  const decisionRows = Object.entries(q.decision_by_group || {}).map(([group, item]) =>
    `<tr><td>${escape(group)}</td><td>${item.cases}</td><td>${item.calls_with_unsupported_numbers}/${item.audited_calls}</td><td>${percentage(item.unsupported_call_rate)}</td><td>${item.unsupported_number_mentions}</td><td>${item.legacy_redacted_calls}</td></tr>`).join('');
  const researchRows = Object.entries(q.research_by_domain || {}).map(([domain, item]) =>
    `<tr><td>${escape(domain)}</td><td>${item.cases}</td><td>${item.calls_with_unsupported_numbers}/${item.audited_calls}</td><td>${percentage(item.unsupported_call_rate)}</td><td>${item.unsupported_number_mentions}</td><td>${item.legacy_redacted_calls}</td></tr>`).join('');
  const overall = q.decision_overall || {};
  return `<section class="stats-substep"><div class="section-label">未匹配來源數字品質指標</div><p class="hint">決策輸出 ${overall.calls_with_unsupported_numbers || 0}/${overall.audited_calls || 0} 次呼叫含至少一項未匹配來源數字（${percentage(overall.unsupported_call_rate)}；${overall.unsupported_number_mentions || 0} 次數值出現）。舊協議移除數字的呼叫另列 ${overall.legacy_redacted_calls || 0} 次。分母以有 audit 紀錄的模型輸出呼叫計；這不是所有數字 token 的比例，也不是事實正確率。</p><div class="table-wrap"><table><thead><tr><th>決策組</th><th>案例</th><th>有未匹配數字呼叫/已稽核呼叫</th><th>呼叫比例</th><th>數值出現次數</th><th>舊版移除呼叫</th></tr></thead><tbody>${decisionRows}</tbody></table></div><p class="hint">研究輸出依領域記錄：</p><div class="table-wrap"><table><thead><tr><th>領域</th><th>案例</th><th>有未匹配數字呼叫/已稽核呼叫</th><th>呼叫比例</th><th>數值出現次數</th><th>舊版移除呼叫</th></tr></thead><tbody>${researchRows}</tbody></table></div></section>`;
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
  const job = state.allJobs.find(item => item.id === state.selectedJob) || state.allJobs.find(item => item.config.protocol_hash === protocol);
  const rqSection = job ? await rqStatsSection(job.config) : '';
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
  const groups = primary.filter(r => GROUP_NAMES[r.group]);
  const benchmark = primary.find(r => r.group === BENCHMARK);
  const ready = report.status !== 'insufficient_cases' && Boolean(report.primary_inference);
  element.innerHTML = `<section class="stats-substep"><div class="section-label">4.1 / 實驗結果</div><h2>四組績效與主要比較</h2><p class="hint">只比較同一套研究規則（同協議版本）跑出的結果：${primaryHorizon} 個交易日、開盤對開盤、扣除 Corwin–Schultz 估計之買賣價差，共 ${report.unique_cases || 0} 個完成的案例；同一案例重跑的紀錄會保留但不重複計算。</p>${insufficient}${preregBlock}
    ${verdictBlock(report.primary_inference, ready)}
    <div class="chart-pair">${comparisonBars(groups, 'selective_accuracy', '條件準確率', percentage)}${comparisonBars(groups, 'sharpe', `年化 Sharpe${benchmark?.sharpe != null ? `（買進持有參照 ${benchmark.sharpe.toFixed(2)}）` : ''}`, sharpe2)}</div>
    ${performanceTable(groups, benchmark, primaryHorizon)}</section>
    ${rqSection}
    <section class="stats-substep"><div class="section-label">4.2 / 配對檢定</div>${pairedTestsTable(report.comparisons, primaryHorizon, report.primary_inference) || '<p class="hint">完成案例達最低統計門檻後，才會計算 D 對 C、B、A 之配對檢定。</p>'}${primaryInferenceBlock(report.primary_inference)}${directionBlocks}</section>
    <details class="stats-group"><summary>4.3 / 敏感性分析與資料品質（完成狀態、年度切分、數字品質、新聞覆蓋、知識截止日）</summary>${completion}${splits}${numericQuality}${newsCoverage}${knowledgeCutoffBlock(report.knowledge_cutoff)}</details>
    <section class="stats-substep"><div class="section-label">4.4 / 品質與匯出</div><p class="hint">試跑檢查（pilot）：${pilot.verdict === 'proceed' ? '通過，可以開始正式批次' : pilot.verdict === 'blocked' ? '尚未通過' : '—'}。這是正式批次前的健檢，用來確認各組結果沒有異常（例如全部都 Hold）。「Hold 門檻」的敏感度分析是用既有預測重算，不會重新呼叫模型。</p>${pilotReasons(pilot.blocking_reasons)}<div class="actions"><a href="/api/studies/${protocol}/summary.csv">下載摘要表（summary.csv）</a><a href="/api/studies/${protocol}" download="statistics.json">下載完整統計（statistics.json）</a></div></section>
    <section class="stats-substep"><div class="section-label">4.5 / 詳細稽核</div><details><summary>試跑檢查、門檻、切分、新聞與數字品質（原始數據）</summary>${copyablePre(JSON.stringify({pilot, hold_band: band, completeness: report.completeness, completion: report.completion, temporal_split_results: report.temporal_split_results, numeric_validation_quality: report.numeric_validation_quality, sentiment_coverage: report.sentiment_coverage}, null, 2))}</details><details><summary>統計檢定結果與計算方式（原始數據）</summary>${copyablePre(JSON.stringify({primary_inference: report.primary_inference, comparisons: report.comparisons, conventions: report.conventions}, null, 2))}</details></section>`;
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
