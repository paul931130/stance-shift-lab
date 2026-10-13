/*
 * Live data-flow map: the main view of the workspace.
 *
 * Renders the pipeline (sources → data agents → immutable snapshot → research
 * agents → neutral report → A/B/C/D → Gatekeeper → backtest → statistics) as
 * SVG and animates particles along the edges. Step modules push real backend
 * state through `flow.set*`; the map never invents progress on its own.
 *
 * The selected job's research design reshapes the map (`flow.setDesign`):
 *   RQ1  the layout above.
 *   RQ2  the same layout; C and D carry AA/AB/BA(/BB) assignment badges.
 *   RQ3  a second lane: four domain debates → Final Aggregator → Gatekeeper.
 */
const NS = 'http://www.w3.org/2000/svg';
const DOMAINS = ['technical', 'fundamental', 'sentiment', 'macro'];
const GROUPS = ['A', 'B', 'C', 'D'];
const DOMAIN_NAME = {technical: '技術', fundamental: '基本面', sentiment: '情緒', macro: '總經'};
const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

// Stage names follow the research-architecture figure in the project report.
const STAGES = ['01 資料來源', '02 資料代理人', '03 資料快照', '04 研究代理人', '05 中立報告', '06 四組決策', '07 守門員', '08 回測', '09 統計'];
const STAGES_RQ3 = ['01 資料來源', '02 資料代理人', '03 資料快照', '04 研究代理人', '05 中立報告', '06 通才與領域辯論', '07 最終彙整者', '08 守門員', '09 回測', '10 統計'];
const ASSIGNMENT_NOTE = {AA: 'Bull＝A、Bear＝A', AB: 'Bull＝A、Bear＝B', BA: 'Bull＝B、Bear＝A', BB: 'Bull＝B、Bear＝B'};

// RQ1 and RQ2 share one layout; RQ3 adds a second lane for the domain debates.
function makeGraph(layout) {
  const rq3 = layout === 'rq3';
  const COLS = rq3 ? [78, 218, 356, 494, 632, 770, 908, 1046, 1174, 1302] : [78, 218, 356, 494, 632, 770, 908, 1036, 1164];
  const H = rq3 ? 520 : 400, W = rq3 ? 1380 : 1240;
  const MID = rq3 ? 270 : 209;
  const ROWS = [0, 78, 156, 234].map(offset => MID - 117 + offset);
  const gate = rq3 ? 7 : 6, backtest = gate + 1, stats = gate + 2;
  // Each band is one workflow step; clicking it opens that step's panel.
  const bands = [
    {from: 0, to: 1, tab: 'data', label: '1 · 資料準備'},
    {from: 2, to: 2, tab: 'experiment', label: '2 · 實驗'},
    {from: 3, to: backtest, tab: 'runs', label: '3 · 代理人執行與回測'},
    {from: stats, to: stats, tab: 'stats', label: '4 · 統計'},
  ];
  const nodes = [
    {id: 'src-technical', col: 0, y: ROWS[0], label: 'Yahoo OHLC', sub: '還原行情', tone: 'technical', tab: 'data'},
    {id: 'src-fundamental', col: 0, y: ROWS[1], label: 'SEC XBRL', sub: 'filing date', tone: 'fundamental', tab: 'data'},
    {id: 'src-sentiment', col: 0, y: ROWS[2], label: 'AV · FNSPID', sub: '新聞標題', tone: 'sentiment', tab: 'data'},
    {id: 'src-macro', col: 0, y: ROWS[3], label: 'FRED · ALFRED', sub: 'vintage', tone: 'macro', tab: 'data'},
    {id: 'da-technical', col: 1, y: ROWS[0], label: 'TECH', sub: '技術資料', tone: 'technical', tab: 'data'},
    {id: 'da-fundamental', col: 1, y: ROWS[1], label: 'FUND', sub: '基本面資料', tone: 'fundamental', tab: 'data'},
    {id: 'da-sentiment', col: 1, y: ROWS[2], label: 'SENT', sub: '情緒資料', tone: 'sentiment', tab: 'data'},
    {id: 'da-macro', col: 1, y: ROWS[3], label: 'MACRO', sub: '總經資料', tone: 'macro', tab: 'data'},
    {id: 'snapshot', col: 2, y: MID, h: 86, label: '資料快照', sub: '分析日前 · 不可變', tone: 'core', tab: 'experiment'},
    {id: 'ra-technical', col: 3, y: ROWS[0], label: '技術研究', sub: '等待分析', tone: 'technical', tab: 'runs'},
    {id: 'ra-fundamental', col: 3, y: ROWS[1], label: '基本面研究', sub: '等待分析', tone: 'fundamental', tab: 'runs'},
    {id: 'ra-sentiment', col: 3, y: ROWS[2], label: '情緒研究', sub: '等待分析', tone: 'sentiment', tab: 'runs'},
    {id: 'ra-macro', col: 3, y: ROWS[3], label: '總經研究', sub: '等待分析', tone: 'macro', tab: 'runs'},
    {id: 'report', col: 4, y: MID, h: 86, label: '中立報告', sub: '鎖定後分流', tone: 'core', tab: 'runs'},
  ];
  const generalist = {A: ['A 單次判斷', '0/1'], B: ['B 獨立投票', '0/7'],
    C: [rq3 ? 'C 通才固定' : 'C 固定立場', '0/7'], D: [rq3 ? 'D 通才交換' : 'D 立場交換', '0/7']};
  GROUPS.forEach((g, i) => nodes.push({id: `g-${g}`, col: 5, y: rq3 ? 80 + i * 48 : ROWS[i], h: rq3 ? 40 : undefined,
    compact: rq3, label: generalist[g][0], sub: generalist[g][1], tone: g, tab: 'runs', progress: true}));
  if (rq3) {
    DOMAINS.forEach((d, i) => nodes.push({id: `dd-${d}`, col: 5, y: 316 + i * 48, h: 40, compact: true,
      label: `${DOMAIN_NAME[d]}辯論`, sub: '看多 vs 看空', tone: d, tab: 'runs', progress: true}));
    nodes.push({id: 'agg', col: 6, y: 388, h: 74, label: '最終彙整者', sub: 'Final Aggregator', tone: 'core', tab: 'runs'});
  }
  nodes.push(
    {id: 'gate', col: gate, y: MID, h: 86, label: '守門員', sub: '引用 · 波動度', tone: 'core', tab: 'runs'},
    {id: 'backtest', col: backtest, y: MID, h: 86, label: '回測', sub: '60 日 · 扣成本', tone: 'core', tab: 'runs'},
    {id: 'stats', col: stats, y: MID, h: 86, label: '統計', sub: '配對檢定 · Holm', tone: 'core', tab: 'stats'});
  const edges = [];
  for (const d of DOMAINS) {
    edges.push({from: `src-${d}`, to: `da-${d}`, tone: d});
    edges.push({from: `da-${d}`, to: 'snapshot', tone: d});
    edges.push({from: 'snapshot', to: `ra-${d}`, tone: d});
    edges.push({from: `ra-${d}`, to: 'report', tone: d});
  }
  for (const g of GROUPS) {
    edges.push({from: 'report', to: `g-${g}`, tone: g});
    edges.push({from: `g-${g}`, to: 'gate', tone: g});
  }
  if (rq3) {
    for (const d of DOMAINS) {
      edges.push({from: 'report', to: `dd-${d}`, tone: d});
      edges.push({from: `dd-${d}`, to: 'agg', tone: d});
    }
    edges.push({from: 'agg', to: 'gate', tone: 'core'});
  }
  edges.push({from: 'gate', to: 'backtest', tone: 'core'});
  edges.push({from: 'backtest', to: 'stats', tone: 'core'});
  return {layout, COLS, W, H, bands, nodes, edges, stages: rq3 ? STAGES_RQ3 : STAGES};
}

let graph = makeGraph('rq1');
let COLS = graph.COLS, W = graph.W, H = graph.H, nodes = graph.nodes, edges = graph.edges;
let byId = new Map(nodes.map(n => [n.id, n]));
let design = {kind: 'rq1'}, designKey = JSON.stringify(design);
// Sub-text and progress survive a layout switch; the SVG nodes do not.
const nodeState = new Map();

const status = new Map();
const particles = [];
const bandEls = new Map();
let svg = null, host = null, particleLayer = null, running = false, visible = true, lastFrame = 0, focusTab = null;
let navigate = () => {};

const el = (name, attrs = {}, parent = null) => {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
};
const nodeW = n => (n.col === 0 ? 118 : 112);
const nodeH = n => n.h || 54;
const x = n => COLS[n.col];
const activate = (target, fn) => {
  target.addEventListener('click', fn);
  target.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); fn(); } });
};

function edgePath(e) {
  const a = byId.get(e.from), b = byId.get(e.to);
  const x1 = x(a) + nodeW(a) / 2, x2 = x(b) - nodeW(b) / 2, dx = (x2 - x1) * 0.5;
  return `M${x1},${a.y} C${x1 + dx},${a.y} ${x2 - dx},${b.y} ${x2},${b.y}`;
}

const mapLabel = () => (design.kind === 'rq3'
  ? '研究架構（RQ3）：資料來源、資料代理人、資料快照、研究代理人、中立報告，分流為 A/B/C/D 通才組與技術、基本面、情緒、總經四個領域辯論，領域辯論經最終彙整者後與通才組一起進入守門員、回測、統計。點選節點可開啟對應步驟。'
  : design.kind === 'rq2'
    ? '研究架構（RQ2）：資料來源、資料代理人、資料快照、研究代理人、中立報告、A/B/C/D 四組決策（C、D 的看多與看空辯論者依指派使用模型 A 或 B）、守門員、回測、統計。點選節點可開啟對應步驟。'
    : '研究架構：資料來源、資料代理人、資料快照、研究代理人、中立報告、A/B/C/D 四組決策、守門員、回測、統計。點選節點可開啟對應步驟。');

// Small AA / AB / BA (/ BB) pills on the top edge of C and D: which model plays Bull and Bear.
function drawBadges() {
  for (const n of nodes) {
    n.badgeEl?.remove();
    n.badgeEl = null;
    n.note = '';
  }
  if (design.kind !== 'rq2') return;
  const list = design.assignments || [];
  const models = design.models || {};
  for (const id of ['g-C', 'g-D']) {
    const n = byId.get(id);
    if (!n?.g) continue;
    const w = nodeW(n), pillW = 23, gap = 3;
    const group = el('g', {class: 'flow-pills'}, n.g);
    list.forEach((assignment, i) => {
      const left = w - 6 - (list.length - i) * pillW - (list.length - i - 1) * gap;
      const pill = el('g', {class: `flow-pill ${assignment[0] === assignment[1] ? 'is-hom' : 'is-het'}`, transform: `translate(${left},-6)`}, group);
      el('rect', {width: pillW, height: 12, rx: 6}, pill);
      el('text', {x: pillW / 2, y: 9, 'text-anchor': 'middle'}, pill).textContent = assignment;
    });
    n.badgeEl = group;
    n.note = `辯論模型：A＝${models.A || '—'}、B＝${models.B || '—'}；指派 ${list.map(a => `${a}（${ASSIGNMENT_NOTE[a] || a}）`).join('、')}`;
  }
}

function build() {
  svg = el('svg', {viewBox: `0 0 ${W} ${H}`, class: 'flow-svg', role: 'group', 'aria-label': mapLabel()});
  svg.dataset.layout = graph.layout;
  const defs = el('defs', {}, svg);
  const glow = el('filter', {id: 'flow-glow', x: '-50%', y: '-50%', width: '200%', height: '200%'}, defs);
  el('feGaussianBlur', {stdDeviation: '3', result: 'b'}, glow);
  const merge = el('feMerge', {}, glow);
  el('feMergeNode', {in: 'b'}, merge);
  el('feMergeNode', {in: 'SourceGraphic'}, merge);

  const bands = el('g', {class: 'flow-bands'}, svg);
  bandEls.clear();
  for (const band of graph.bands) {
    const left = COLS[band.from] - 66, right = COLS[band.to] + 66;
    const g = el('g', {class: 'flow-band', tabindex: '0', role: 'button', 'aria-label': `開啟 ${band.label}`}, bands);
    el('rect', {x: left + 2, y: 40, width: right - left - 4, height: H - 56, rx: 14}, g);
    el('text', {x: left + 12, y: H - 26, class: 'flow-band-label'}, g).textContent = band.label;
    activate(g, () => navigate(band.tab));
    bandEls.set(band.tab, g);
  }
  const stages = el('g', {class: 'flow-stages'}, svg);
  graph.stages.forEach((label, col) => { el('text', {x: COLS[col], y: 28, 'text-anchor': 'middle'}, stages).textContent = label; });

  const edgeLayer = el('g', {class: 'flow-edges'}, svg);
  for (const e of edges) {
    e.d = edgePath(e);
    e.base = el('path', {d: e.d, class: `flow-edge tone-${e.tone}`}, edgeLayer);
    e.dash = el('path', {d: e.d, class: `flow-edge-dash tone-${e.tone}`}, edgeLayer);
    e.len = e.base.getTotalLength();
    e.next = performance.now() + Math.random() * 4000;
    e.mode = undefined;
  }
  particleLayer = el('g', {class: 'flow-particles', filter: 'url(#flow-glow)'}, svg);

  const nodeLayer = el('g', {class: 'flow-nodes'}, svg);
  for (const n of nodes) {
    const w = nodeW(n), h = nodeH(n);
    const g = el('g', {transform: `translate(${x(n) - w / 2},${n.y - h / 2})`, tabindex: '0', role: 'button'}, nodeLayer);
    el('rect', {class: 'flow-node-ring', width: w, height: h, rx: 10}, g);
    el('rect', {class: 'flow-node-box', width: w, height: h, rx: 10}, g);
    el('rect', {class: 'flow-node-stripe', width: 3, height: h - 16, x: 0, y: 8, rx: 1.5}, g);
    el('circle', {class: 'flow-node-dot', cx: w - 12, cy: n.compact ? 11 : 13, r: 4}, g);
    const labelY = n.compact ? 16 : n.h ? h / 2 - 4 : 23;
    el('text', {class: 'flow-node-label', x: 12, y: labelY}, g).textContent = n.label;
    n.subEl = el('text', {class: 'flow-node-sub', x: 12, y: labelY + (n.compact ? 14 : 16)}, g);
    n.subEl.textContent = n.sub;
    if (n.progress) {
      const barY = n.compact ? h - 6 : h - 9;
      el('rect', {class: 'flow-node-track', x: 12, y: barY, width: w - 24, height: 3, rx: 1.5}, g);
      n.barEl = el('rect', {class: 'flow-node-bar', x: 12, y: barY, width: 0, height: 3, rx: 1.5}, g);
    }
    n.title = el('title', {}, g);
    n.g = g;
    activate(g, () => navigate(n.tab));
    const saved = nodeState.get(n.id);
    if (saved) paint(n, saved);
  }
  host.appendChild(svg);
  drawBadges();
  applyAll();
}

const STATUS_TEXT = {idle: '尚未開始', ready: '可用', active: '進行中', done: '完成', warn: '需注意', error: '錯誤'};
function edgeMode(e) {
  const a = status.get(e.from) || 'idle', b = status.get(e.to) || 'idle';
  if (b === 'error' || a === 'error') return 'error';
  if (b === 'active') return 'active';
  if (a === 'active' && b !== 'done') return 'active';
  if ((a === 'done' || a === 'ready' || a === 'warn') && (b === 'done' || b === 'warn')) return 'done';
  if (a === 'ready' || a === 'done') return 'ready';
  return 'idle';
}
function applyAll() {
  if (!svg) return;
  for (const n of nodes) {
    const s = status.get(n.id) || 'idle';
    n.g.setAttribute('class', `flow-node tone-${n.tone} is-${s}${n.tab === focusTab ? ' in-focus' : ''}`);
    n.g.setAttribute('aria-label', `${n.label}（${n.subEl.textContent}）：${STATUS_TEXT[s] || s}${n.note ? `。${n.note}` : ''}`);
    n.title.textContent = `${n.label} · ${n.subEl.textContent} · ${STATUS_TEXT[s] || s}${n.note ? `\n${n.note}` : ''}`;
  }
  for (const [tab, g] of bandEls) g.setAttribute('class', `flow-band${tab === focusTab ? ' is-focus' : ''}`);
  for (const e of edges) {
    const mode = edgeMode(e);
    if (mode !== e.mode) {
      e.mode = mode;
      e.base.setAttribute('class', `flow-edge tone-${e.tone} is-${mode}`);
      e.dash.setAttribute('class', `flow-edge-dash tone-${e.tone} is-${mode}`);
      e.next = performance.now() + Math.random() * 300;
    }
  }
  svg.closest('.flow-hero')?.classList.toggle('is-busy', nodes.some(n => status.get(n.id) === 'active'));
}

// Emission interval (ms) per edge mode; idle edges keep a faint heartbeat so
// the map reads as a live system even before any data is collected.
const RATE = {active: 380, done: 2600, ready: 3600, idle: 9000, error: 0};
const SPEED = {active: 0.62, done: 0.3, ready: 0.24, idle: 0.16};
function spawn(e, strong = false) {
  if (!particleLayer || particles.length > 160) return;
  const mode = strong ? 'active' : e.mode;
  const c = el('circle', {r: strong ? 3.4 : mode === 'active' ? 2.8 : 2, class: `flow-dot tone-${e.tone} is-${mode}`}, particleLayer);
  particles.push({e, c, t: 0, v: (SPEED[mode] || 0.2) * (0.85 + Math.random() * 0.3)});
}
function frame(now) {
  if (!running) return;
  const dt = Math.min(0.05, (now - (lastFrame || now)) / 1000);
  lastFrame = now;
  if (visible && !document.hidden) {
    for (const e of edges) {
      const rate = RATE[e.mode || 'idle'];
      if (rate && now >= e.next) { spawn(e); e.next = now + rate * (0.7 + Math.random() * 0.6); }
    }
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.t += p.v * dt;
      if (p.t >= 1) { p.c.remove(); particles.splice(i, 1); continue; }
      const pt = p.e.base.getPointAtLength(p.t * p.e.len);
      p.c.setAttribute('cx', pt.x.toFixed(1));
      p.c.setAttribute('cy', pt.y.toFixed(1));
      p.c.setAttribute('opacity', Math.min(1, Math.sin(Math.PI * p.t) * 1.6).toFixed(2));
    }
  }
  requestAnimationFrame(frame);
}

function paint(n, saved) {
  if (saved.sub !== undefined && n.subEl) n.subEl.textContent = saved.sub;
  if (n.barEl && saved.total) n.barEl.setAttribute('width', ((nodeW(n) - 24) * Math.min(1, (saved.count || 0) / saved.total)).toFixed(1));
}

function setOne(id, value) {
  if (value === undefined || value === null) return;
  const extra = typeof value === 'object' ? value : {status: value};
  if (extra.status) status.set(id, extra.status);
  const saved = {...(nodeState.get(id) || {})};
  if (extra.sub !== undefined) saved.sub = extra.sub;
  if (extra.total) { saved.count = extra.count || 0; saved.total = extra.total; }
  nodeState.set(id, saved);
  const n = byId.get(id);
  if (n?.g) paint(n, saved);
}

// Switch the map to a job's research design. Only RQ3 changes the layout; RQ2 adds badges.
function setDesign(next = {kind: 'rq1'}) {
  const key = JSON.stringify(next);
  if (key === designKey) return;
  design = next;
  designKey = key;
  const layout = next.kind === 'rq3' ? 'rq3' : 'rq1';
  if (layout !== graph.layout) {
    graph = makeGraph(layout);
    ({COLS, W, H, nodes, edges} = graph);
    byId = new Map(nodes.map(n => [n.id, n]));
    for (const p of particles.splice(0)) p.c.remove();
    if (svg) { svg.remove(); build(); }
  } else if (svg) {
    svg.setAttribute('aria-label', mapLabel());
    drawBadges();
    applyAll();
  }
}

export const flow = {
  mount(target) {
    if (svg || !target) return;
    host = target;
    build();
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(entries => { visible = entries.some(en => en.isIntersecting); }, {threshold: 0.05}).observe(host);
    }
    if (!reduceMotion) { running = true; requestAnimationFrame(frame); }
  },
  set(id, value) { setOne(id, value); applyAll(); },
  setMany(map) { for (const [id, value] of Object.entries(map)) setOne(id, value); applyAll(); },
  get(id) { return status.get(id); },
  focus(tab) { focusTab = tab; applyAll(); },
  // {kind: 'rq1'|'rq2'|'rq3', assignments?: ['AA', ...], models?: {A, B}}
  setDesign,
  // Send a short burst toward a node, e.g. when the terminal logs an event.
  pulse(id) {
    if (reduceMotion) return;
    for (const e of edges) if (e.to === id) for (let i = 0; i < 3; i++) setTimeout(() => spawn(e, true), i * 120);
  },
  caption(text) { const c = document.getElementById('flow-caption'); if (c) c.textContent = text; },
  metric(id, value) {
    const target = document.getElementById(`flow-metric-${id}`);
    if (!target) return;
    const to = Number(value);
    if (value === null || value === undefined || value === '—' || !Number.isFinite(to)) { target.textContent = value ?? '—'; target.dataset.value = ''; return; }
    const from = Number(target.dataset.value || 0);
    target.dataset.value = String(to);
    if (reduceMotion || from === to) { target.textContent = to.toLocaleString('zh-TW'); return; }
    const start = performance.now(), span = 700;
    const tick = now => {
      const k = Math.min(1, (now - start) / span), eased = 1 - Math.pow(1 - k, 3);
      target.textContent = Math.round(from + (to - from) * eased).toLocaleString('zh-TW');
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    target.classList.remove('bump'); void target.offsetWidth; target.classList.add('bump');
  },
  onNavigate(fn) { navigate = fn; },
};
