/*
 * Live data-flow map: the main view of the workspace.
 *
 * Renders the pipeline (sources → data agents → immutable snapshot → research
 * agents → neutral report → A/B/C/D → Gatekeeper → backtest → statistics) as
 * SVG and animates particles along the edges. Step modules push real backend
 * state through `flow.set*`; the map never invents progress on its own.
 */
const NS = 'http://www.w3.org/2000/svg';
const W = 1240, H = 400;
const COLS = [78, 218, 356, 494, 632, 770, 908, 1036, 1164];
const ROWS = [92, 170, 248, 326];
const MID = 209;
const DOMAINS = ['technical', 'fundamental', 'sentiment', 'macro'];
const GROUPS = ['A', 'B', 'C', 'D'];
const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

const STAGES = ['01 來源', '02 資料 Agent', '03 資料集', '04 研究 Agent', '05 報告', '06 決策組', '07 風控', '08 回測', '09 統計'];
// Each band is one workflow step; clicking it opens that step's panel.
const BANDS = [
  {from: 0, to: 1, tab: 'data', label: '1 · 資料準備'},
  {from: 2, to: 2, tab: 'experiment', label: '2 · 實驗'},
  {from: 3, to: 7, tab: 'runs', label: '3 · Agent 執行與回測'},
  {from: 8, to: 8, tab: 'stats', label: '4 · 統計'},
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
  {id: 'snapshot', col: 2, y: MID, h: 86, label: '資料集', sub: '建立後不再變動', tone: 'core', tab: 'experiment'},
  {id: 'ra-technical', col: 3, y: ROWS[0], label: '技術研究', sub: '等待分析', tone: 'technical', tab: 'runs'},
  {id: 'ra-fundamental', col: 3, y: ROWS[1], label: '基本面研究', sub: '等待分析', tone: 'fundamental', tab: 'runs'},
  {id: 'ra-sentiment', col: 3, y: ROWS[2], label: '情緒研究', sub: '等待分析', tone: 'sentiment', tab: 'runs'},
  {id: 'ra-macro', col: 3, y: ROWS[3], label: '總經研究', sub: '等待分析', tone: 'macro', tab: 'runs'},
  {id: 'report', col: 4, y: MID, h: 86, label: '中立報告', sub: '鎖定後分派', tone: 'core', tab: 'runs'},
  {id: 'g-A', col: 5, y: ROWS[0], label: 'A 單次', sub: '0/1', tone: 'A', tab: 'runs', progress: true},
  {id: 'g-B', col: 5, y: ROWS[1], label: 'B 投票', sub: '0/7', tone: 'B', tab: 'runs', progress: true},
  {id: 'g-C', col: 5, y: ROWS[2], label: 'C 固定立場', sub: '0/7', tone: 'C', tab: 'runs', progress: true},
  {id: 'g-D', col: 5, y: ROWS[3], label: 'D 立場交換', sub: '0/7', tone: 'D', tab: 'runs', progress: true},
  {id: 'gate', col: 6, y: MID, h: 86, label: 'Gatekeeper', sub: '引用與門檻', tone: 'core', tab: 'runs'},
  {id: 'backtest', col: 7, y: MID, h: 86, label: '回測', sub: '30／60／90 日', tone: 'core', tab: 'runs'},
  {id: 'stats', col: 8, y: MID, h: 86, label: '統計', sub: '配對檢定', tone: 'core', tab: 'stats'},
];
const byId = new Map(nodes.map(n => [n.id, n]));

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
edges.push({from: 'gate', to: 'backtest', tone: 'core'});
edges.push({from: 'backtest', to: 'stats', tone: 'core'});

const status = new Map(nodes.map(n => [n.id, 'idle']));
const particles = [];
const bandEls = new Map();
let svg = null, particleLayer = null, running = false, visible = true, lastFrame = 0, focusTab = null;
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

function build(host) {
  svg = el('svg', {viewBox: `0 0 ${W} ${H}`, class: 'flow-svg', role: 'group',
    'aria-label': '研究資料流向：來源、資料 Agent、資料集、研究 Agent、報告、A/B/C/D、風控、回測、統計。點選節點可開啟對應步驟。'});
  const defs = el('defs', {}, svg);
  const glow = el('filter', {id: 'flow-glow', x: '-50%', y: '-50%', width: '200%', height: '200%'}, defs);
  el('feGaussianBlur', {stdDeviation: '3', result: 'b'}, glow);
  const merge = el('feMerge', {}, glow);
  el('feMergeNode', {in: 'b'}, merge);
  el('feMergeNode', {in: 'SourceGraphic'}, merge);

  const bands = el('g', {class: 'flow-bands'}, svg);
  for (const band of BANDS) {
    const left = COLS[band.from] - 66, right = COLS[band.to] + 66;
    const g = el('g', {class: 'flow-band', tabindex: '0', role: 'button', 'aria-label': `開啟 ${band.label}`}, bands);
    el('rect', {x: left + 2, y: 40, width: right - left - 4, height: H - 56, rx: 14}, g);
    el('text', {x: left + 12, y: H - 26, class: 'flow-band-label'}, g).textContent = band.label;
    activate(g, () => navigate(band.tab));
    bandEls.set(band.tab, g);
  }
  const stages = el('g', {class: 'flow-stages'}, svg);
  STAGES.forEach((label, col) => { el('text', {x: COLS[col], y: 28, 'text-anchor': 'middle'}, stages).textContent = label; });

  const edgeLayer = el('g', {class: 'flow-edges'}, svg);
  for (const e of edges) {
    e.d = edgePath(e);
    e.base = el('path', {d: e.d, class: `flow-edge tone-${e.tone}`}, edgeLayer);
    e.dash = el('path', {d: e.d, class: `flow-edge-dash tone-${e.tone}`}, edgeLayer);
    e.len = e.base.getTotalLength();
    e.next = performance.now() + Math.random() * 4000;
  }
  particleLayer = el('g', {class: 'flow-particles', filter: 'url(#flow-glow)'}, svg);

  const nodeLayer = el('g', {class: 'flow-nodes'}, svg);
  for (const n of nodes) {
    const w = nodeW(n), h = nodeH(n);
    const g = el('g', {transform: `translate(${x(n) - w / 2},${n.y - h / 2})`, tabindex: '0', role: 'button'}, nodeLayer);
    el('rect', {class: 'flow-node-ring', width: w, height: h, rx: 10}, g);
    el('rect', {class: 'flow-node-box', width: w, height: h, rx: 10}, g);
    el('rect', {class: 'flow-node-stripe', width: 3, height: h - 16, x: 0, y: 8, rx: 1.5}, g);
    el('circle', {class: 'flow-node-dot', cx: w - 12, cy: 13, r: 4}, g);
    const labelY = n.h ? h / 2 - 4 : 23;
    el('text', {class: 'flow-node-label', x: 12, y: labelY}, g).textContent = n.label;
    n.subEl = el('text', {class: 'flow-node-sub', x: 12, y: labelY + 16}, g);
    n.subEl.textContent = n.sub;
    if (n.progress) {
      el('rect', {class: 'flow-node-track', x: 12, y: h - 9, width: w - 24, height: 3, rx: 1.5}, g);
      n.barEl = el('rect', {class: 'flow-node-bar', x: 12, y: h - 9, width: 0, height: 3, rx: 1.5}, g);
    }
    n.title = el('title', {}, g);
    n.g = g;
    activate(g, () => navigate(n.tab));
  }
  host.appendChild(svg);
  applyAll();
}

const STATUS_TEXT = {idle: '尚未開始', ready: '可用', active: '進行中', done: '完成', warn: '需注意', error: '錯誤'};
function edgeMode(e) {
  const a = status.get(e.from), b = status.get(e.to);
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
    const s = status.get(n.id);
    n.g.setAttribute('class', `flow-node tone-${n.tone} is-${s}${n.tab === focusTab ? ' in-focus' : ''}`);
    n.g.setAttribute('aria-label', `${n.label}（${n.subEl.textContent}）：${STATUS_TEXT[s] || s}`);
    n.title.textContent = `${n.label} · ${n.subEl.textContent} · ${STATUS_TEXT[s] || s}`;
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

function setOne(id, value) {
  const n = byId.get(id);
  if (!n || value === undefined || value === null) return;
  const extra = typeof value === 'object' ? value : {status: value};
  if (extra.status) status.set(id, extra.status);
  if (extra.sub !== undefined) n.subEl.textContent = extra.sub;
  if (n.barEl && extra.total) n.barEl.setAttribute('width', ((nodeW(n) - 24) * Math.min(1, (extra.count || 0) / extra.total)).toFixed(1));
}

export const flow = {
  mount(host) {
    if (svg || !host) return;
    build(host);
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(entries => { visible = entries.some(en => en.isIntersecting); }, {threshold: 0.05}).observe(host);
    }
    if (!reduceMotion) { running = true; requestAnimationFrame(frame); }
  },
  set(id, value) { setOne(id, value); applyAll(); },
  setMany(map) { for (const [id, value] of Object.entries(map)) setOne(id, value); applyAll(); },
  get(id) { return status.get(id); },
  focus(tab) { focusTab = tab; applyAll(); },
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
