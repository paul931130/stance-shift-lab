// Step 3 detail blocks for the RQ2 (heterogeneous model) and RQ3 (domain debate) designs.
import { escape, percentage, number } from './ui.js';
import { stripOllama } from './design-panel.js';

const DOMAINS = ['technical', 'fundamental', 'sentiment', 'macro'];
const DOMAIN_LABEL = {technical: '技術面', fundamental: '基本面', sentiment: '情緒面', macro: '總經面'};
const ARM_LABEL = {C_domain: '領域辯論 · 固定立場（對照 C）', D_domain: '領域辯論 · 立場交換（對照 D）'};
const GENERALIST_OF = {C_domain: 'C', D_domain: 'D'};
const DIRECTION = {Buy: ['dir-buy', 'Buy 買進'], Sell: ['dir-sell', 'Sell 賣出'], Abstain: ['dir-abstain', 'Abstain 棄權'],
  InsufficientInfo: ['dir-info', 'InsufficientInfo 資訊不足'], Hold: ['dir-abstain', 'Hold'], NoTrade: ['dir-abstain', 'NoTrade']};
const ASSIGNMENT_PLAYERS = {AA: ['A', 'A'], AB: ['A', 'B'], BA: ['B', 'A'], BB: ['B', 'B']};

export const dirChip = direction => {
  const [cls, text] = DIRECTION[direction] || ['dir-abstain', direction ?? '—'];
  return `<span class="dir-chip ${cls}">${escape(text)}</span>`;
};
const table = (head, rows, caption = '') => `<div class="table-wrap"><table class="rq-table">${caption ? `<caption>${caption}</caption>` : ''}<thead><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
const short = (text, n = 90) => { const t = String(text ?? ''); return t.length > n ? `${t.slice(0, n)}…` : t; };

// ---------------- RQ2 ----------------
function correctness(rows, group) {
  const row = rows.find(item => item.group === group);
  if (!row || row.status === 'pending') return '<span class="pending">待成熟</span>';
  if (row.status !== 'complete') return escape(row.status);
  if (row.correct == null) return '—';
  return row.correct ? '<span class="ok-mark">正確</span>' : '<span class="bad-mark">錯誤</span>';
}

export function rq2RunPanel(job, s) {
  const p = job.config.protocol, list = p.debate_assignments || ['AA'];
  const models = {A: stripOllama(p.debate_model_a), B: stripOllama(p.debate_model_b)};
  const horizon = p.primary_horizon || 60;
  const scored = [...(s.cases || []), ...(s.routed_cases || [])].filter(row => row.horizon === horizon
    && row.cost_model === 'corwin_schultz' && (row.decision_layer || 'gated') === 'candidate');
  const decision = (group, assignment) => assignment === 'AA' ? s.decisions?.[group] : s.routed_decisions?.[`${group}@${assignment}`];
  const cell = (group, assignment) => {
    const d = decision(group, assignment);
    return d ? `<b>${escape(d.action)}</b> <small>信心 ${percentage(d.confidence)}</small>` : '<span class="pending">等待中</span>';
  };
  const rows = list.map(assignment => {
    const [bull, bear] = ASSIGNMENT_PLAYERS[assignment];
    const key = group => assignment === 'AA' ? group : `${group}@${assignment}`;
    return `<tr><th scope="row"><span class="assign-chip ${bull === bear ? 'is-hom' : 'is-het'}">${assignment}</span></th><td>${escape(models[bull])}<small> (${bull})</small></td><td>${escape(models[bear])}<small> (${bear})</small></td><td>${cell('C', assignment)}</td><td>${cell('D', assignment)}</td><td>${correctness(scored, key('C'))}</td><td>${correctness(scored, key('D'))}</td></tr>`;
  });
  const routeRecords = (s.records || []).filter(r => r.audit?.model_route && ['C', 'D'].includes(r.group));
  const routeRows = routeRecords.map(r => {
    const m = r.audit.model_route;
    const role = m.model_slot === 'JUDGE' ? '裁決者' : `${m.agent === 'agent-a' ? 'Bull' : 'Bear'}（原立場 ${escape(m.original_stance || '—')}）`;
    return `<tr><td>${escape(r.key)}</td><td>${escape(m.assignment || '—')}</td><td>${role}</td><td>${m.round ?? '—'} · ${escape(m.round_stance || '—')}</td><td>${escape(m.model_slot)} · ${escape(stripOllama(m.model))}</td><td>${escape(m.endpoint || '—')}</td><td>${m.prompt_tokens ?? '—'}／${m.completion_tokens ?? '—'}</td><td>${m.latency_seconds == null ? '—' : Number(m.latency_seconds).toFixed(1)}</td><td>${m.seed_applied === true ? '是' : m.seed_applied === false ? '否' : '未知'}</td><td>${m.provider_attempts ?? 1}／${m.validation_retries ?? 0}</td></tr>`;
  });
  const presentations = (s.records || []).filter(r => r.judge_presentation).map(r => {
    const order = r.judge_presentation.order || [];
    return `<tr><td>${escape(r.key)}</td><td>${order.map(a => `${escape(r.judge_presentation.labels?.[a] || a)}＝${a === 'agent-a' ? 'Bull' : 'Bear'}`).join('，')}</td><td>${escape(r.judge_presentation.basis || '')}</td></tr>`;
  });
  const usage = Object.entries(s.routed_compute_usage || {}).map(([arm, u]) =>
    `<tr><td>${escape(arm)}</td><td>${u.logical_calls ?? u.calls ?? '—'}</td><td>${u.provider_attempts ?? '—'}</td><td>${u.validation_retry_calls ?? 0}</td><td>${u.prompt_tokens ?? '—'}／${u.completion_tokens ?? '—'}</td><td>${u.wall_seconds == null ? '—' : Number(u.wall_seconds).toFixed(1)}</td></tr>`);
  return `<section class="execution-block rq-block"><div class="subheading"><h3>RQ2 · 異質模型辯論</h3><small>模型 A＝${escape(models.A)} · 模型 B＝${escape(models.B)} · 裁決者、研究代理人與 A、B 組＝${escape(stripOllama(p.model))}</small></div>
    ${table(['指派', 'Bull 模型', 'Bear 模型', 'C 決策', 'D 決策', `C ${horizon} 日`, `D ${horizon} 日`], rows, `各指派之 C／D 決策與 ${horizon} 日方向（候選決策、扣成本）`)}
    <p class="hint">同一案例在 ${list.join('、')} 各自完成一次 C 與 D；AB 與 BA 互換模型與初始立場，用來平衡模型身份與看多／看空角色。D 組只在第 2 輪交換立場，辯論者全程使用同一個模型。${routeRecords.length ? '' : '尚未有呼叫紀錄。'}</p>
    <details><summary>每次呼叫的模型路由（${routeRecords.length} 筆）</summary>${routeRows.length ? table(['呼叫', '指派', '角色', '輪次 · 立場', '模型槽 · 模型', '端點', 'token 輸入／輸出', '秒', 'seed 已套用', '嘗試／驗證重試'], routeRows) : '<p class="hint">尚無紀錄。</p>'}
      ${presentations.length ? table(['裁決呼叫', '裁決者看到的順序', '依據'], presentations, '裁決者的辯論者呈現順序（依報告雜湊決定，已記錄）') : ''}
      ${usage.length ? table(['分組', '邏輯呼叫', '提供者嘗試', '驗證重試呼叫', 'token 輸入／輸出', '耗時秒'], usage, '各非 AA 分組之運算用量') : ''}</details></section>`;
}

// ---------------- RQ3 ----------------
function viewRow(domain, record) {
  if (!record) return `<tr><th scope="row">${DOMAIN_LABEL[domain]}</th><td colspan="6"><span class="pending">等待領域辯論完成</span></td></tr>`;
  const o = record.output || {};
  const counter = o.counter_evidence_ids || [];
  const gaps = (o.information_gaps || []).join('；');
  return `<tr${o.deterministic ? ' class="skipped"' : ''}><th scope="row">${DOMAIN_LABEL[domain]}${o.deterministic ? '<small>略過辯論</small>' : ''}</th><td>${dirChip(o.direction)}</td><td>${percentage(o.confidence)}</td><td>${o.expected_return_pct == null ? '—' : `${number(o.expected_return_pct)}%`}</td><td>${(o.supporting_evidence_ids || []).length}</td><td>${counter.length ? `${counter.length} 筆<br><small>${escape(short(counter.join('、'), 60))}</small>` : '無'}</td><td>${escape(short(o.uncertainty, 80))}${gaps ? `<br><small>缺口：${escape(short(gaps, 80))}</small>` : ''}<details><summary>理由</summary><p>${escape(o.rationale || '')}</p></details></td></tr>`;
}

export function rq3RunPanel(job, s) {
  const settings = job.config.domain_debate || {};
  const diagnostics = s.rq3_diagnostics || {};
  const records = s.domain_records || [];
  const arms = ['C_domain', 'D_domain'].filter(arm => settings.rule === 'both' || (settings.rule === 'fixed') === (arm === 'C_domain'));
  const MATCH = {unspecified: '未指定', nominal_calls: '名義呼叫次數', total_tokens: '總 token 數', wall_time: '牆鐘時間', report_frontier: '報告成本–績效前緣'};
  const summary = `規則 ${{fixed: '固定', switch: '交換', both: '固定＋交換'}[settings.rule] || settings.rule} · 彙整者輸入 ${settings.aggregator_input === 'views' ? '僅領域觀點' : '觀點＋辯論全文'} · 順序 ${settings.aggregator_order === 'fixed' ? '固定' : '隨機'} · 運算量標記 ${MATCH[settings.compute_matching] || settings.compute_matching}`;
  const cards = arms.map(arm => {
    const views = Object.fromEntries(records.filter(r => r.arm === arm && r.kind === 'view').map(r => [r.domain, r]));
    const final = s.decisions?.[arm], agreement = diagnostics.agreement?.[arm];
    const generalist = s.decisions?.[GENERALIST_OF[arm]];
    const relation = {follows_majority: '與多數方向一致', against_majority: '與多數方向相反', no_majority: '領域觀點平手', final_not_directional: '最終決策非方向性'}[agreement?.final_relation] || '';
    const aggregator = final ? `<div class="rq-aggregator"><div><small>最終彙整者決策</small><strong>${escape(final.action)}</strong></div>
        <div><small>信心／預期報酬</small><b>${percentage(final.confidence)}</b> · ${number(final.expected_return_pct)}%</div>
        <div><small>領域觀點一致性</small><b>${agreement?.pattern || '不分類'}</b>${agreement ? ` · Buy ${agreement.buy}／Sell ${agreement.sell}${agreement.abstain ? `／Abstain ${agreement.abstain}` : ''}${agreement.insufficient_info ? `／資訊不足 ${agreement.insufficient_info}` : ''}` : ''}<br><small>${escape(relation)}</small></div>
        <div><small>對照通才 ${GENERALIST_OF[arm]}</small><b>${generalist ? escape(generalist.action) : '—'}</b><small> ${final.action === generalist?.action ? '決策相同' : '決策不同'}</small></div>
        <p class="hint">${escape(short(final.rationale, 220))}${agreement?.aggregator ? `<br>輸入順序：${agreement.aggregator.input_order.map(d => DOMAIN_LABEL[d]).join(' → ')}（${agreement.aggregator.order_mode === 'fixed' ? '固定' : '隨機'}）· 可引用證據 ${agreement.aggregator.citable_evidence}` : ''}</p></div>`
      : '<p class="hint">四個領域觀點完成後，由最終彙整者整合並通過守門員。</p>';
    return `<div class="rq-arm"><h4>${ARM_LABEL[arm]}<small>${arm}</small></h4>
      ${table(['領域', '方向', '信心', '預期報酬', '支持證據', '反證', '不確定性與理由'], DOMAINS.map(d => viewRow(d, views[d])), 'Domain Views（每個領域的看多／看空辯論由領域裁決者總結）')}
      ${aggregator}</div>`;
  }).join('');
  const transcript = records.filter(r => r.kind === 'debate').map(r => `<article class="trace" data-group="${escape(r.group)}"><strong>${escape(r.arm)} · ${escape(DOMAIN_LABEL[r.domain] || r.domain)} · 第 ${r.round} 輪 · ${escape(r.stance)}</strong><p>${escape(r.output?.rationale || '')}</p><small>引用：${escape((r.output?.evidence_ids || []).join(', '))}</small></article>`).join('');
  return `<section class="execution-block rq-block"><div class="subheading"><h3>RQ3 · 領域專業辯論</h3><small>${escape(summary)}</small></div>
    ${cards || '<p class="hint">尚無領域辯論結果。</p>'}
    <p class="hint">通才組 A、B、C、D 照常執行；領域組與同規則的通才組配對比較。領域觀點是同一案例的中間輸出，不是四個獨立樣本。已記錄領域辯論與觀點 ${records.length} 筆。</p>
    <details><summary>領域辯論逐步論證（${records.filter(r => r.kind === 'debate').length}）</summary>${transcript || '<p class="hint">尚無紀錄。</p>'}</details></section>`;
}
