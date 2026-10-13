// Research design selector (RQ1 / RQ2 / RQ3) shared by the batch and the
// single-case experiment forms. It renders the extra fields, reads them back
// into the job/plan payload and reports the nominal calls per case.
//
//   RQ1  D (role-switching) vs C (fixed-role), one model.
//   RQ2  Bull/Bear on different models: AA homogeneous, AB+BA heterogeneous, optional BB.
//   RQ3  four domain Bull/Bear debates -> Domain Views -> Final Aggregator.
import { $ } from './ui.js';

export const ROUTER_VERSION = 'v3-1006.1';
export const DEFAULT_MODEL_A = 'ollama/qwen3:32b';
export const DEFAULT_MODEL_B = 'ollama/gemma3:27b';
const DESIGNS = [
  {id: 'rq1', label: 'RQ1 立場交換', hint: '同一模型：立場交換辯論（D）對固定立場辯論（C）。'},
  {id: 'rq2', label: 'RQ2 異質模型', hint: '看多與看空辯論者使用不同模型；同質 AA 與異質 AB／BA 同案比較。'},
  {id: 'rq3', label: 'RQ3 領域辯論', hint: '技術、基本面、情緒、總經四個領域各自辯論，由最終彙整者決策。'},
];
const MATCHING = {unspecified: '未指定', nominal_calls: '名義呼叫次數', total_tokens: '總 token 數', wall_time: '牆鐘時間', report_frontier: '報告成本–績效前緣'};
const BASE_CALLS = voting => 15 + Number(voting);   // A 1 + B n + C 7 + D 7
const DOMAIN_ARM_CALLS = 29;                          // 4 domains x (6 debate turns + 1 view) + 1 aggregator

// ---- pure helpers (also used to label stored jobs) ----
export function designOf(config = {}) {
  const protocol = config.protocol || {};
  if (config.domain_debate) return 'rq3';
  return protocol.version === ROUTER_VERSION || protocol.debate_model_b ? 'rq2' : 'rq1';
}

export function nominalCalls(design, voting, {assignments = ['AA', 'AB', 'BA'], rule = 'both'} = {}) {
  const base = BASE_CALLS(voting);
  if (design === 'rq2') return base + 14 * Math.max(0, assignments.length - 1);
  if (design === 'rq3') return base + DOMAIN_ARM_CALLS * (rule === 'both' ? 2 : 1);
  return base;
}

export function designLabel(config = {}) {
  const design = designOf(config);
  if (design === 'rq2') return `RQ2 · ${(config.protocol.debate_assignments || []).join('／')}`;
  if (design === 'rq3') return `RQ3 · ${{fixed: '固定', switch: '交換', both: '固定＋交換'}[config.domain_debate.rule] || config.domain_debate.rule}`;
  return 'RQ1';
}

export const stripOllama = model => String(model || '').replace(/^ollama\//, '');

// ---- DOM ----
const field = (prefix, name) => $(`${prefix}-${name}`);

function html(prefix) {
  const endpoint = (slot, label) => `<div class="pair rq-endpoint">
      <label>模型 ${slot} 的 Ollama 位址（選填）<input id="${prefix}-ep-${slot}" type="url" inputmode="url" maxlength="300" placeholder="http://127.0.0.1:1143${slot === 'A' ? '5' : '6'}" autocomplete="off" spellcheck="false"></label>
      <label>${label}逾時秒數（10–3600，選填）<input id="${prefix}-to-${slot}" type="number" min="10" max="3600" step="10" placeholder="預設"></label>
    </div>`;
  return `<div class="design-picker" role="tablist" aria-label="研究問題">${DESIGNS.map((d, i) =>
    `<button type="button" role="tab" data-rq-pick="${d.id}" aria-selected="${i === 0}" tabindex="${i === 0 ? 0 : -1}">${d.label}</button>`).join('')}</div>
  <p class="hint" id="${prefix}-design-hint">${DESIGNS[0].hint}</p>
  <div class="design-block" id="${prefix}-rq2" hidden>
    <div class="pair">
      <label>模型 A（Bull 預設）<input id="${prefix}-model-a" maxlength="200" value="${DEFAULT_MODEL_A}" autocomplete="off" spellcheck="false"></label>
      <label>模型 B（異質對照）<input id="${prefix}-model-b" maxlength="200" value="${DEFAULT_MODEL_B}" autocomplete="off" spellcheck="false"></label>
    </div>
    <fieldset class="rq-assign"><legend>辯論者模型指派（Bull／Bear）</legend>
      <label class="check"><input type="checkbox" checked disabled>AA　同質：Bull＝A、Bear＝A（必選，同案基準）</label>
      <label class="check"><input type="checkbox" checked disabled>AB ＋ BA　異質：Bull＝A、Bear＝B 與反向（兩者必須一併執行，平衡模型與初始立場）</label>
      <label class="check"><input id="${prefix}-bb" type="checkbox">BB　選填對照：Bull＝B、Bear＝B（同質 B）</label>
    </fieldset>
    <p class="hint">裁決者、四個研究代理人與 A、B 組仍使用上方「模型」。每位辯論者三輪都用同一個模型，D 組只在第 2 輪交換立場；裁決者只看到「辯論者 1／2」，看不到模型名稱。模型不可用時該步驟失敗並暫停，不會改用別的模型。</p>
    <details class="rq-endpoints"><summary>各模型的 Ollama 位址與逾時（進階）</summary>
      ${endpoint('A', 'A ')}${endpoint('B', 'B ')}
      <p class="hint">留白＝使用伺服器設定的預設位址。實驗室伺服器請先建立 SSH 通道（例如 <code>ssh -N -L 11435:127.0.0.1:11434 帳號@主機</code>），再填 <code>http://127.0.0.1:11435</code>。位址裡不要放帳號或密碼；金鑰只能由伺服器的環境變數提供，不會經過瀏覽器。</p>
    </details>
  </div>
  <div class="design-block" id="${prefix}-rq3" hidden>
    <div class="pair">
      <label>領域辯論規則<select id="${prefix}-rule"><option value="both">兩者：固定與交換</option><option value="fixed">固定立場（對照 C）</option><option value="switch">立場交換（對照 D）</option></select></label>
      <label>最終彙整者輸入<select id="${prefix}-agg-input"><option value="views">僅領域觀點（Domain Views）</option><option value="views_and_transcripts">領域觀點＋辯論全文</option></select></label>
    </div>
    <div class="pair">
      <label>觀點呈現順序<select id="${prefix}-agg-order"><option value="randomized">隨機（每案依雜湊決定）</option><option value="fixed">固定（技術、基本面、情緒、總經）</option></select></label>
      <label>運算量對齊標記<select id="${prefix}-matching">${Object.entries(MATCHING).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></label>
    </div>
    <p class="hint">四個領域各進行三輪看多／看空辯論，產出該領域的 Domain View（方向可為 Buy、Sell、Abstain、InsufficientInfo，附信心與反證），再由最終彙整者整合並通過守門員。領域組與同規則的通才組（C 或 D）配對比較；Generalist A、B、C、D 照常執行。「運算量對齊標記」只註記分析計畫採用的資源指標，系統不會重新分配預算。RQ2 與 RQ3 不能合併在同一個實驗。</p>
  </div>
  <p class="nominal-calls" id="${prefix}-nominal" aria-live="polite"></p>`;
}

export function currentDesign(prefix) {
  return document.querySelector(`#${prefix}-design [aria-selected="true"]`)?.dataset.rqPick || 'rq1';
}

function assignments(prefix) {
  return ['AA', 'AB', 'BA', ...(field(prefix, 'bb')?.checked ? ['BB'] : [])];
}

function describe(prefix, voting) {
  const design = currentDesign(prefix), box = field(prefix, 'nominal');
  const base = BASE_CALLS(voting);
  let text;
  if (design === 'rq2') {
    const list = assignments(prefix), total = nominalCalls('rq2', voting, {assignments: list});
    text = `每案名義呼叫 ${total} 次：通才四組 ${base} 次＋${list.length - 1} 組額外指派 × 14 次（${list.join('、')}）。`;
  } else if (design === 'rq3') {
    const rule = field(prefix, 'rule').value, total = nominalCalls('rq3', voting, {rule});
    text = `每案名義呼叫 ${total} 次：通才四組 ${base} 次＋${rule === 'both' ? '2' : '1'} 組領域辯論 × ${DOMAIN_ARM_CALLS} 次（4 領域 × 7 次＋彙整者 1 次）。無證據的領域會略過辯論，實際呼叫可能較少。`;
  } else {
    text = `每案決策呼叫 ${base} 次（A 1＋B ${Number(voting)}＋C 7＋D 7）。`;
  }
  box.textContent = text;
}

function select(prefix, design) {
  for (const button of document.querySelectorAll(`#${prefix}-design [data-rq-pick]`)) {
    const on = button.dataset.rqPick === design;
    button.setAttribute('aria-selected', String(on));
    button.tabIndex = on ? 0 : -1;
  }
  field(prefix, 'rq2').hidden = design !== 'rq2';
  field(prefix, 'rq3').hidden = design !== 'rq3';
  field(prefix, 'design-hint').textContent = DESIGNS.find(d => d.id === design).hint;
}

// Render the selector into `host` (id `${prefix}-design`). `voting()` returns the B-group sample
// count so the nominal-call line follows it; `onChange` fires after every edit.
export function mountDesign(host, prefix, {voting, onChange}) {
  host.id = `${prefix}-design`;
  host.classList.add('design-selector');
  host.innerHTML = html(prefix);
  const refresh = () => { describe(prefix, voting()); onChange?.(); };
  host.addEventListener('click', event => {
    const button = event.target.closest('[data-rq-pick]');
    if (!button) return;
    select(prefix, button.dataset.rqPick);
    refresh();
  });
  host.addEventListener('input', refresh);
  host.addEventListener('change', refresh);
  describe(prefix, voting());
  return {refresh};
}

// A pasted URL with a user, password, query or fragment is refused here, before it reaches the server.
function endpointUrl(prefix, slot) {
  const raw = (field(prefix, `ep-${slot}`).value || '').trim();
  if (!raw) return null;
  let url;
  try { url = new URL(raw); } catch { throw new Error(`模型 ${slot} 的位址不是有效的網址：${raw}`); }
  if (!/^https?:$/.test(url.protocol)) throw new Error(`模型 ${slot} 的位址必須是 http 或 https`);
  if (url.username || url.password) throw new Error(`模型 ${slot} 的位址含有帳號或密碼；請移除。金鑰只能放在伺服器的環境變數`);
  if (url.search || url.hash) throw new Error(`模型 ${slot} 的位址不可帶查詢參數或片段（避免把權杖放進網址）`);
  return raw.replace(/\/+$/, '');
}

// The design-specific fields of a job/plan request ({} for RQ1). Throws a Chinese message for local mistakes.
export function designPayload(prefix) {
  const design = currentDesign(prefix);
  if (design === 'rq2') {
    const a = field(prefix, 'model-a').value.trim(), b = field(prefix, 'model-b').value.trim();
    if (!a || !b) throw new Error('RQ2 需要填寫模型 A 與模型 B');
    if (a === b) throw new Error('模型 A 與模型 B 必須不同；同一個模型請改用 RQ1');
    const endpoints = {};
    for (const [slot, model] of [['A', a], ['B', b]]) {
      const base = endpointUrl(prefix, slot), timeout = field(prefix, `to-${slot}`).value;
      const spec = {};
      if (base) spec.api_base = base;
      if (timeout) {
        const seconds = Number(timeout);
        if (!Number.isInteger(seconds) || seconds < 10 || seconds > 3600) throw new Error(`模型 ${slot} 的逾時必須是 10 到 3600 的整數秒`);
        spec.timeout_seconds = seconds;
      }
      if (Object.keys(spec).length) endpoints[model] = spec;
    }
    return {debate_model_a: a, debate_model_b: b, debate_assignments: assignments(prefix),
      ...(Object.keys(endpoints).length ? {model_endpoints: endpoints} : {})};
  }
  if (design === 'rq3') {
    return {domain_debate: {rule: field(prefix, 'rule').value, aggregator_input: field(prefix, 'agg-input').value,
      aggregator_order: field(prefix, 'agg-order').value, compute_matching: field(prefix, 'matching').value}};
  }
  return {};
}

export function designSummary(prefix) {
  const design = currentDesign(prefix);
  if (design === 'rq2') return `RQ2（${assignments(prefix).join('、')}；A ${field(prefix, 'model-a').value}／B ${field(prefix, 'model-b').value}）`;
  if (design === 'rq3') return `RQ3（${{both: '固定＋交換', fixed: '固定', switch: '交換'}[field(prefix, 'rule').value]}）`;
  return 'RQ1';
}

export function refreshNominal(prefix, voting) { describe(prefix, voting); }
