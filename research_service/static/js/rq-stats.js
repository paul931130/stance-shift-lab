// Step 4 sections for the RQ2 and RQ3 designs. Everything here is descriptive:
// no p-values or intervals are computed until the preregistered analysis runs.
import { escape, percentage } from './ui.js';
import { api } from './api.js';
import { designOf, stripOllama } from './design-panel.js';

const pp = value => value == null ? '—' : `${value >= 0 ? '+' : '−'}${Math.abs(value * 100).toFixed(1)} 個百分點`;
const fixed = (value, digits = 1) => value == null ? '—' : Number(value).toFixed(digits);
const ratio = value => value == null ? '—' : `${Number(value).toFixed(2)}×`;
const table = (caption, head, rows, cls = '') => `<div class="table-wrap"><table class="report-table ${cls}"><caption>${caption}</caption><thead><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
const DESCRIPTIVE = '<span class="descriptive-tag">描述統計 · 尚未計算 p 值</span>';

function rq2Block(report, protocol) {
  if (!report.cases) return `<section class="stats-substep"><div class="section-label">4.1c / RQ2 異質模型</div><h2>異質模型辯論 ${DESCRIPTIVE}</h2><p class="hint">還沒有已完成並取得回測結果的 RQ2 案例；60 日回測成熟後才會有準確率。</p></section>`;
  const assignments = protocol.debate_assignments || ['AA', 'AB', 'BA'];
  const acc = report.accuracy || {};
  const columns = assignments.map(a => a);
  const arm = (group, a) => acc[`${group}@${a}`];
  const row = group => `<tr><th scope="row">${group} ${group === 'C' ? '固定立場' : '立場交換'}</th>${columns.map(a => `<td>${percentage(arm(group, a))}</td>`).join('')}<td>${percentage(report.hetero_case_mean_accuracy?.[group])}</td></tr>`;
  const diff = a => arm('D', a) == null || arm('C', a) == null ? null : arm('D', a) - arm('C', a);
  const hetD = report.hetero_case_mean_accuracy?.D, hetC = report.hetero_case_mean_accuracy?.C;
  const diffRow = `<tr class="reference-row"><th scope="row">D − C</th>${columns.map(a => `<td>${pp(diff(a))}</td>`).join('')}<td>${pp(hetD == null || hetC == null ? null : hetD - hetC)}</td></tr>`;
  const interaction = report.interaction;
  const verdict = interaction == null ? '需要 AA 與 AB／BA 的 C、D 都有成熟回測才能計算。'
    : interaction > 0 ? '異質配置下 D 相對 C 的優勢大於同質配置（描述上）。'
      : interaction < 0 ? '異質配置下 D 相對 C 的優勢小於同質配置（描述上）。' : '兩者相同。';
  return `<section class="stats-substep"><div class="section-label">4.1c / RQ2 異質模型</div><h2>異質模型辯論 ${DESCRIPTIVE}</h2>
    <p class="hint">模型 A＝${escape(stripOllama(protocol.debate_model_a))}、模型 B＝${escape(stripOllama(protocol.debate_model_b))}。${report.cases} 個完成案例；${escape(report.basis || '')}。每格為該指派在同一批案例上的方向準確率。</p>
    ${table(`C／D × 模型指派之方向準確率（${columns.join('、')}）`, ['組別', ...columns.map(a => `${a}`), '異質平均（AB、BA 同案平均）'], [row('C'), row('D'), diffRow], 'rq-table')}
    <div class="verdict pending rq-interaction"><b>Δ<sub>interaction</sub> ＝ (D − C)<sub>異質</sub> − (D − C)<sub>同質</sub> ＝ ${pp(interaction)}</b>
      <p>${escape(verdict)}異質值為同案 AB、BA 準確率的平均。這是描述統計：AB 與 BA 共用同一批案例，不是獨立觀察，也沒有 p 值或信賴區間；正式推論由事前登記的分析計畫（配對／日期群聚重抽樣）進行。</p></div>
    <p class="hint">${escape(report.note || '')}</p></section>`;
}

const RESOURCE_COLUMNS = [['nominal_calls', '名義呼叫'], ['logical_calls', '實際呼叫'], ['provider_attempts', '提供者嘗試'],
  ['validation_retry_calls', '驗證重試'], ['total_tokens', 'token 總量'], ['sum_call_seconds', '呼叫秒數'], ['critical_path_seconds', '關鍵路徑秒']];
const ARM_NAME = {A: 'A 單次判斷', B: 'B 獨立投票', C: 'C 通才固定', D: 'D 通才交換', C_domain: 'C_domain 領域固定', D_domain: 'D_domain 領域交換'};

function rq3Block(report) {
  if (report.status !== 'complete') {
    const text = report.status === 'mixed_protocols' ? '這個協議下混有不同的 RQ3 設定，無法彙整。' : '還沒有完成的 RQ3 案例。';
    return `<section class="stats-substep"><div class="section-label">4.1c / RQ3 領域辯論</div><h2>領域專業辯論 ${DESCRIPTIVE}</h2><p class="hint">${text}</p></section>`;
  }
  const pairs = report.rule_matched_pairs || [];
  const RULE = {fixed: '固定立場', switch: '立場交換'};
  const accuracyOf = {};
  for (const pair of pairs) { Object.assign(accuracyOf, pair.accuracy); }
  const pairRows = pairs.map(pair => {
    const a = pair.accuracy[pair.generalist], b = pair.accuracy[pair.domain];
    const o = pair.outcomes || {};
    return `<tr><th scope="row">${RULE[pair.rule] || pair.rule}<small>${pair.generalist} vs ${pair.domain}</small></th><td>${pair.scored_pairs}</td><td>${percentage(a)}</td><td>${percentage(b)}</td><td>${pp(a == null || b == null ? null : b - a)}</td><td>${pair.discordant.generalist_only}／${pair.discordant.domain_only}</td><td>${o.both_correct || 0}／${o.both_wrong || 0}${o.not_scored ? `<small>另有 ${o.not_scored} 案未計分</small>` : ''}</td></tr>`;
  });
  const arms = Object.keys(report.resources || {}).sort((x, y) => Object.keys(ARM_NAME).indexOf(x) - Object.keys(ARM_NAME).indexOf(y));
  const costRows = arms.map(arm => {
    const means = report.resources[arm].means || {}, missing = report.resources[arm].cases_missing_metric || {};
    return `<tr><th scope="row">${escape(ARM_NAME[arm] || arm)}</th><td>${percentage(accuracyOf[arm])}</td>${RESOURCE_COLUMNS.map(([key]) => `<td>${means[key] == null ? '—' : fixed(means[key], key.includes('seconds') ? 1 : 1)}${missing[key] ? `<small>${missing[key]} 案缺值</small>` : ''}</td>`).join('')}</tr>`;
  });
  const ratioRows = pairs.map(pair => `<tr><th scope="row">${pair.domain} ÷ ${pair.generalist}</th>${['nominal_calls', 'provider_attempts', 'total_tokens', 'sum_call_seconds', 'critical_path_seconds'].map(key => `<td>${ratio(pair.domain_over_generalist_cost?.[key])}</td>`).join('')}</tr>`);
  const agreementBlocks = Object.entries(report.agreement || {}).map(([arm, a]) => {
    const patterns = a.patterns || {};
    const complete = ['4:0', '3:1', '2:2'].reduce((sum, key) => sum + (patterns[key] || 0), 0);
    const incomplete = Object.entries(patterns).filter(([key]) => !['4:0', '3:1', '2:2'].includes(key));
    const incompleteTotal = incomplete.reduce((sum, [, count]) => sum + count, 0);
    const rows = ['4:0', '3:1', '2:2'].map(key => `<tr><th scope="row">${key}</th><td>${patterns[key] || 0}</td><td>${complete ? percentage((patterns[key] || 0) / complete) : '—'}</td></tr>`);
    const relation = Object.entries(a.final_relation || {}).map(([key, count]) => `${{follows_majority: '與多數一致', against_majority: '與多數相反', no_majority: '無多數', final_not_directional: '非方向性', not_applicable: '不適用'}[key] || key} ${count}`).join('、');
    return `<div class="rq-arm"><h4>${escape(ARM_NAME[arm] || arm)}</h4>${table('四個領域觀點皆為 Buy／Sell 的案例', ['分布', '案例數', '佔完整案例'], [...rows,
      `<tr class="reference-row"><th scope="row">含棄權／資訊不足（不分類）</th><td>${incompleteTotal}</td><td>${incomplete.map(([key, count]) => `${escape(key.replace('incomplete:', '').replace('_binary', ' 個方向觀點'))}：${count} 案`).join('、') || '—'}</td></tr>`])}
      <p class="hint">棄權觀點 ${a.abstain_views} 個、資訊不足觀點 ${a.insufficient_info_views} 個（這些案例不會被硬分到 2:2）。最終決策相對多數：${escape(relation || '—')}。</p></div>`;
  }).join('');
  const matching = report.compute_matching || {};
  return `<section class="stats-substep"><div class="section-label">4.1c / RQ3 領域辯論</div><h2>領域專業辯論 ${DESCRIPTIVE}</h2>
    <p class="hint">${report.cases} 個完成案例；${report.horizon} 日方向準確率、${escape(report.cost_model)} 成本、${escape(report.decision_layer)} 決策層。領域組與同規則的通才組逐案配對；${escape(report.note || '')}</p>
    ${table(`規則配對比較（${report.horizon} 日）`, ['規則', '計分配對', '通才準確率', '領域準確率', '領域 − 通才', '只有通才對／只有領域對', '兩者皆對／皆錯'], pairRows)}
    <p class="hint">「只有通才對／只有領域對」是配對檢定（McNemar）的不一致案例，供之後的正式檢定使用；此處不報 p 值。</p>
    ${table('績效–成本（每案平均）', ['組別', `${report.horizon} 日準確率`, ...RESOURCE_COLUMNS.map(([, label]) => label)], costRows)}
    ${table('領域組相對通才組之成本比', ['比較', '名義呼叫', '提供者嘗試', 'token', '呼叫秒數', '關鍵路徑秒'], ratioRows)}
    <p class="hint">運算量對齊標記：${escape(matching.declared || 'unspecified')}${matching.enforced ? '' : '（僅標記，系統不會重新分配預算）'}。成本欄為每案平均，缺值案例另標示而不當作 0。</p>
    <h3 class="substep">領域觀點一致性</h3>${agreementBlocks}</section>`;
}

// Fetch and render the section for the selected job's design; '' for RQ1 or on failure.
export async function rqStatsSection(config) {
  const kind = designOf(config);
  if (kind === 'rq1') return '';
  const hash = config.protocol_hash;
  try {
    const report = await api(`/api/studies/${encodeURIComponent(hash)}/${kind}`);
    return kind === 'rq2' ? rq2Block(report, config.protocol) : rq3Block(report);
  } catch (error) {
    return `<section class="stats-substep"><div class="section-label">4.1c / ${kind.toUpperCase()}</div><p class="error-text">${escape(error.message)}</p></section>`;
  }
}
