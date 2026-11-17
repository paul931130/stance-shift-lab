'use strict';
/* Stance Shift Lab — 立場流場（互動簡報）
   同一份頁面兩種用法：往下捲的閱讀模式，以及按 P 進入的簡報模式。
   背景流場的走法跟著場景換：暖色粒子 = 看多、冷色粒子 = 看空。 */
const $ = (q, el = document) => el.querySelector(q);
const $$ = (q, el = document) => [...el.querySelectorAll(q)];
const root = document.documentElement;
root.classList.add('js');
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ───────── 流場 ───────── */
const Field = (() => {
  const cv = $('#field'), ctx = cv.getContext('2d');
  const TAU = Math.PI * 2;
  let W = 0, H = 0, P = [], mode = 'drift', prev = 'drift', mix = 1, t = 0, raf = 0, ptr = null, col = ['#ff6b3d', '#3fc8ff'], light = false, level = 1, lv = 1, off = false;
  const sm = (a, b, x) => { const k = Math.max(0, Math.min(1, (x - a) / (b - a))); return k * k * (3 - 2 * k); };

  function resize() {
    const dpr = Math.min(devicePixelRatio || 1, 1.5);
    W = innerWidth; H = innerHeight;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round(Math.max(420, Math.min(1700, W * H / 1000)));
    P = [];
    for (let i = 0; i < n; i++) {
      const x = Math.random() * W, y = Math.random() * H;
      P.push({ x, y, px: x, py: y, k: i % 2, lane: (i >> 1) % 4, off: (Math.random() + Math.random() + Math.random() - 1.5) / 1.5,
        home: Math.random(), sp: .6 + Math.random() * .8, ph: Math.random() * TAU, n: i });
    }
    if (REDUCED) still();
  }
  function colors() {
    const s = getComputedStyle(root);
    col = [s.getPropertyValue('--bull').trim() || col[0], s.getPropertyValue('--bear').trim() || col[1]];
    light = root.dataset.theme === 'light';
  }
  // 每種走法回傳粒子這一格的速度（像素）
  function vel(m, p, out) {
    const u = p.x / W, S = Math.max(.7, Math.min(W, H) / 800);
    if (m === 'drift' || m === 'calm') {
      const a = (Math.sin(p.x * .0031 + t * .21) + Math.sin(p.y * .0043 - t * .17) + Math.sin((p.x + p.y) * .0022 + t * .13 + p.k * .9)) * 2.1;
      const s = (m === 'calm' ? .45 : 1) * p.sp * S;
      out[0] = Math.cos(a) * s + .25 * S; out[1] = Math.sin(a) * s; return;
    }
    let ty = .5, th = .045, vx = 1.5;
    if (m === 'same') { ty = .5 + .12 * Math.sin(u * TAU + t * .25); th = .1; }
    else if (m === 'fixed' || m === 'hetero') ty = p.k ? .67 : .33;
    else if (m === 'swap') { const s = Math.max(-1, Math.min(1, Math.cos(TAU * u) * 1.7)); ty = .5 + (p.k ? 1 : -1) * .17 * s; }
    else if (m === 'converge') { const g = sm(.1, .6, u); ty = .5 + (p.k ? 1 : -1) * (.17 - .15 * g); th = .05 - .02 * g; }
    else if (m === 'domains') { ty = .17 + p.lane * .22; ty += (.5 - ty) * sm(.45, .8, u); th = .03; }
    else if (m === 'pipeline') { ty = p.home; th = 0; vx = 2.6; }
    const wob = Math.sin(u * 7 + p.ph + t * .5) * .012;
    let vy = ((ty + p.off * th + wob) * H - p.y) * .05;
    vy = Math.max(-4 * S, Math.min(4 * S, vy));
    vx *= p.sp * S;
    if (m === 'hetero' && p.k) { vx *= .5; vy += Math.sin(p.x * .09 + p.ph) * 1.1 * S; }
    out[0] = vx; out[1] = vy;
  }
  const a = [0, 0], b = [0, 0];
  function step() {
    t += .016;
    if (mix < 1) mix = Math.min(1, mix + 1 / 80);
    const e = mix * mix * (3 - 2 * mix);
    for (const p of P) {
      p.px = p.x; p.py = p.y;
      vel(mode, p, a);
      if (e < 1) { vel(prev, p, b); a[0] = b[0] + (a[0] - b[0]) * e; a[1] = b[1] + (a[1] - b[1]) * e; }
      if (ptr) { // 游標附近打一個小渦旋
        const dx = p.x - ptr.x, dy = p.y - ptr.y, d2 = dx * dx + dy * dy;
        if (d2 < 26000 && d2 > 1) { const f = (1 - d2 / 26000) * 2.4, d = Math.sqrt(d2); a[0] += (-dy / d) * f + (dx / d) * f * .35; a[1] += (dx / d) * f + (dy / d) * f * .35; }
      }
      p.x += a[0]; p.y += a[1];
      if (p.x > W + 12) { p.x = -10; p.px = p.x; p.py = p.y; }
      else if (p.x < -12) { p.x = W + 10; p.px = p.x; p.py = p.y; }
      if (p.y > H + 12) { p.y = -10; p.px = p.x; p.py = p.y; }
      else if (p.y < -12) { p.y = H + 10; p.px = p.x; p.py = p.y; }
    }
  }
  function paint(alpha) {
    ctx.globalCompositeOperation = light ? 'source-over' : 'lighter';
    ctx.globalAlpha = alpha * (.3 + .7 * lv);
    const lim = P.length * (.4 + .6 * lv);   // 內容頁少畫一些粒子
    for (let k = 0; k < 2; k++) {
      ctx.beginPath();
      for (const p of P) if (p.k === k && p.n < lim) { ctx.moveTo(p.px, p.py); ctx.lineTo(p.x, p.y); }
      ctx.strokeStyle = col[k];
      ctx.lineWidth = mode === 'hetero' && k ? 2.3 : 1.15;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
  function frame() {
    lv += (level - lv) * .04;
    step();
    ctx.globalCompositeOperation = 'destination-out';
    ctx.fillStyle = 'rgba(0,0,0,.075)';
    ctx.fillRect(0, 0, W, H);
    paint(light ? .7 : .55);
    raf = requestAnimationFrame(frame);
  }
  // 減少動態：直接算一張靜止的流線圖
  function still() {
    ctx.clearRect(0, 0, W, H); mix = 1; lv = level;
    for (let i = 0; i < 150; i++) { step(); paint(.12); }
  }
  function start() { if (!REDUCED && !off && !raf && !document.hidden) raf = requestAnimationFrame(frame); }
  function stop() { cancelAnimationFrame(raf); raf = 0; }
  function set(m) {
    if (!m || m === mode) return;
    prev = mode; mode = m; mix = 0;
    if (REDUCED) still();
  }
  addEventListener('resize', resize);
  addEventListener('pointermove', e => { ptr = { x: e.clientX, y: e.clientY }; });
  addEventListener('pointerleave', () => { ptr = null; });
  document.addEventListener('visibilitychange', () => document.hidden ? stop() : start());
  colors(); resize(); start();
  function setLevel(v) { level = v; root.dataset.fl = v >= 1 ? 'full' : 'dim'; if (REDUCED) still(); }
  function toggle(force) {
    off = force ?? !off;
    root.classList.toggle('nofield', off);
    if (off) stop(); else { start(); if (REDUCED) still(); }
    try { localStorage.setItem('ssl-field', off ? 'off' : 'on'); } catch { /* 無法儲存就算了 */ }
  }
  try { if (localStorage.getItem('ssl-field') === 'off') toggle(true); } catch { /* 同上 */ }
  return { set, level: setLevel, toggle, colors: () => { colors(); if (REDUCED) still(); } };
})();

/* ───────── 場景、導覽、簡報模式 ───────── */
const scenes = $$('.scene');
const hooks = {};            // 場景自己的逐步動作：{ count, apply(k) }
const state = { i: 0, step: 0, deck: false, t0: 0 };
const pad = n => String(n).padStart(2, '0');

scenes.forEach(s => $$('.in > *', s).forEach((el, n) => el.style.setProperty('--i', n)));

const rail = $('#rail'), overList = $('#over-list');
scenes.forEach((s, i) => {
  const b = document.createElement('button'); b.type = 'button';
  const label = document.createElement('span'); label.textContent = `${pad(i)} ${s.dataset.title}`;
  b.append(label); b.setAttribute('aria-label', `${pad(i)} ${s.dataset.title}`);
  b.addEventListener('click', () => goto(i));
  rail.append(b);
  const li = document.createElement('li'), ob = document.createElement('button'); ob.type = 'button';
  const num = document.createElement('i'); num.textContent = pad(i);
  ob.append(num, document.createTextNode(s.dataset.title));
  ob.addEventListener('click', () => { toggleOver(false); goto(i); });
  li.append(ob); overList.append(li);
});

function stepsOf(s) {
  const marks = $$('[data-step]', s).map(el => Number(el.dataset.step));
  return Math.max(0, hooks[s.id]?.count || 0, ...marks);
}
function refreshField() { const d = scenes[state.i].dataset; Field.set(d.field); Field.level(Number(d.level || .3)); }
function mark(i) {            // 目前場景改變時，同步導覽、標籤、流場
  state.i = i;
  const s = scenes[i];
  s.classList.add('seen');
  $$('button', rail).forEach((b, n) => n === i ? b.setAttribute('aria-current', 'true') : b.removeAttribute('aria-current'));
  $$('button', overList).forEach((b, n) => n === i ? b.setAttribute('aria-current', 'true') : b.removeAttribute('aria-current'));
  $('#where').textContent = `${pad(i)} / ${pad(scenes.length - 1)} · ${s.dataset.title}`;
  history.replaceState(null, '', `#${s.id}`);
  refreshField();
}
function applyStep() {
  const s = scenes[state.i];
  $$('[data-step]', s).forEach(el => el.classList.toggle('shown', Number(el.dataset.step) <= state.step));
  hooks[s.id]?.apply(state.step);
  refreshField();
}
function show(i, step = 0) {  // 簡報模式：切到第 i 頁的第 step 步
  i = Math.max(0, Math.min(scenes.length - 1, i));
  scenes.forEach((s, n) => s.classList.toggle('on', n === i));
  mark(i);
  state.step = Math.min(step, stepsOf(scenes[i]));
  applyStep();
  $('#hud-count').textContent = `${pad(i)} / ${pad(scenes.length - 1)}`;
  $('#hud-title').textContent = scenes[i].dataset.title;
  $('#hud-prog').style.width = `${(i + (stepsOf(scenes[i]) ? state.step / (stepsOf(scenes[i]) + 1) : 0)) / (scenes.length - 1) * 100}%`;
  $('#notes').textContent = scenes[i].dataset.notes || '';
}
function goto(i) { state.deck ? show(i) : scenes[i].scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth' }); }
function next() {
  if (state.step < stepsOf(scenes[state.i])) { state.step++; show(state.i, state.step); }
  else if (state.i < scenes.length - 1) show(state.i + 1);
}
function back() {
  if (state.step > 0) { state.step--; show(state.i, state.step); }
  else if (state.i > 0) show(state.i - 1, Infinity);
}
function setDeck(on) {
  if (on === state.deck) return;
  state.deck = on;
  root.classList.toggle('deck', on);
  if (on) {
    if (!state.t0) state.t0 = Date.now();
    show(state.i);
  } else {
    $$('[data-step]').forEach(el => el.classList.remove('shown'));
    scenes.forEach(s => s.classList.remove('on'));
    $('#notes').hidden = true;
    if (document.fullscreenElement) document.exitFullscreen?.();
    scenes[state.i].scrollIntoView({ behavior: 'instant' });
    onScroll();
  }
}
function toggleOver(force) {
  const el = $('#over'); const open = force ?? el.hidden;
  el.hidden = !open;
  if (open) $('button[aria-current]', el)?.focus();
}
function toggleTheme() {
  const lightNow = root.dataset.theme === 'light';
  if (lightNow) delete root.dataset.theme; else root.dataset.theme = 'light';
  try { localStorage.setItem('ssl-theme', lightNow ? 'dark' : 'light'); } catch { /* 無法儲存就算了 */ }
  Field.colors();
}

// 閱讀模式：捲到哪個場景就算哪個
function onScroll() {
  if (state.deck) return;
  const mid = innerHeight / 2;
  let hit = state.i;
  scenes.forEach((s, n) => {
    const r = s.getBoundingClientRect();
    if (r.top < innerHeight * .85 && r.bottom > 0) s.classList.add('seen');
    if (r.top <= mid && r.bottom > mid) hit = n;
  });
  if (hit !== state.i) mark(hit);
}
addEventListener('scroll', onScroll, { passive: true });
addEventListener('resize', onScroll);

$('#btn-deck').addEventListener('click', () => setDeck(true));
$('#btn-over').addEventListener('click', () => toggleOver());
$('#btn-theme').addEventListener('click', toggleTheme);
$('#hud-next').addEventListener('click', next);
$('#hud-prev').addEventListener('click', back);
$('#hud-clock').addEventListener('click', () => { state.t0 = Date.now(); tick(); });
$('#over').addEventListener('click', e => { if (e.target.id === 'over') toggleOver(false); });
function tick() {
  if (!state.t0) return;
  const s = Math.floor((Date.now() - state.t0) / 1000);
  $('#hud-clock').textContent = `${pad(Math.floor(s / 60))}:${pad(s % 60)}`;
}
setInterval(tick, 1000);

addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
  const k = e.key;
  if (k === 'Escape') { if (!$('#over').hidden) toggleOver(false); else if (state.deck) setDeck(false); return; }
  if (k === 'o' || k === 'O') return toggleOver();
  if (k === 't' || k === 'T') return toggleTheme();
  if (k === 'b' || k === 'B') return Field.toggle();
  if (k === 'p' || k === 'P') return setDeck(!state.deck);
  if (k === 'f' || k === 'F') { document.fullscreenElement ? document.exitFullscreen?.() : root.requestFullscreen?.().catch(() => {}); return; }
  if (!state.deck || !$('#over').hidden) return;
  if (k === 'n' || k === 'N') { $('#notes').hidden = !$('#notes').hidden; return; }
  // 焦點在按鈕上時，空白鍵與 Enter 留給按鈕
  if ((k === ' ' || k === 'Enter') && (tag === 'BUTTON' || tag === 'A')) return;
  if (k === 'ArrowRight' || k === 'PageDown' || k === ' ' || k === 'ArrowDown' || k === 'Enter') { e.preventDefault(); next(); }
  else if (k === 'ArrowLeft' || k === 'PageUp' || k === 'ArrowUp' || k === 'Backspace') { e.preventDefault(); back(); }
  else if (k === 'Home') show(0);
  else if (k === 'End') show(scenes.length - 1, Infinity);
});
let touch = null;
addEventListener('touchstart', e => { touch = e.touches.length === 1 ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : null; }, { passive: true });
addEventListener('touchend', e => {
  if (!touch || !state.deck) return;
  const dx = e.changedTouches[0].clientX - touch.x, dy = e.changedTouches[0].clientY - touch.y;
  if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) dx < 0 ? next() : back();
  touch = null;
}, { passive: true });

/* ───────── 00 封面：押注 ───────── */
let bet = null;
$$('[data-bet]').forEach(b => b.addEventListener('click', () => {
  bet = b.dataset.bet;
  $$('[data-bet]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
  $('#bet-echo').textContent = `你押的是 ${bet}。`;
  $('#results').dataset.field = bet === 'C' ? 'fixed' : 'swap';
  refreshField();
}));

/* ───────── 02 辯論場 ───────── */
const arena = $('#arena');
const ROUND_TEXT = {
  C: ['C：看多、看空各守立場辯三輪，裁決者最後選買進或賣出。三輪各兩次發言加一次裁決，共 7 次預定決策呼叫。',
    '第 1 輪：雙方各自提出論點並引用證據。',
    '第 2 輪：維持立場，看得到對方第 1 輪的發言，互相批評與回應。',
    '第 3 輪：維持立場，整理論點。',
    '裁決者讀完整場辯論與報告，逐項核對證據，選擇買進或賣出。'],
  D: ['D：流程與 C 相同，但第 2 輪兩位代理人互換立場，而且只能反駁自己。',
    '第 1 輪：與 C 相同，雙方各自提出論點並引用證據。',
    '第 2 輪：交換立場。這一輪看不到對手，只看得到自己的第 1 輪；必須引用自己的原文再反駁，引用會被驗證，不合格就重試。',
    '第 3 輪：換回原立場，整合前兩輪的主張與反駁，說明仍不確定的地方。模型沒有換。',
    '裁決者讀完整場辯論與報告，逐項核對證據，選擇買進或賣出。同樣是 7 次預定決策呼叫。']
};
const LINKS = { C: ['各自提證據', '⇅ 互相批評', '⇅ 整理論點'], D: ['各自提證據', '✕ 看不到對手', '⇅ 回來整合'] };
function renderArena(arm = arena.dataset.arm, round = Number(arena.dataset.round)) {
  const armChanged = arm !== arena.dataset.arm;
  arena.dataset.arm = arm; arena.dataset.round = round;
  $$('[data-arm]', $('#design')).forEach(b => b.tagName === 'BUTTON' && b.setAttribute('aria-pressed', String(b.dataset.arm === arm)));
  $$('.steps [data-round]').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.round) === round)));
  $$('.nd', arena).forEach(nd => {
    const agent = Number(nd.dataset.agent), r = Number(nd.dataset.r);
    const swapped = arm === 'D' && r === 2;
    const bull = (agent === 0) !== swapped;
    nd.className = `nd ${bull ? 'bull' : 'bear'}`;
    nd.replaceChildren(document.createTextNode(bull ? '看多' : '看空'));
    const small = document.createElement('small');
    small.textContent = swapped ? '交換立場，反駁自己第 1 輪' : arm === 'D' && r === 3 ? '換回原立場' : r === 1 ? '提出論點' : r === 2 ? '批評與回應' : '整理論點';
    nd.append(small);
    if (armChanged && r === 2 && !REDUCED) { nd.classList.add('flip'); setTimeout(() => nd.classList.remove('flip'), 600); }
  });
  $$('.lk', arena).forEach((lk, n) => { lk.textContent = LINKS[arm][n]; lk.classList.toggle('cut', arm === 'D' && n === 1); });
  $('#round-text').textContent = ROUND_TEXT[arm][round];
  $('#design').dataset.field = arm === 'C' ? 'fixed' : 'swap';
  if (scenes[state.i].id === 'design') refreshField();
}
$$('#design .seg [data-arm]').forEach(b => b.addEventListener('click', () => renderArena(b.dataset.arm)));
$$('.steps [data-round]').forEach(b => b.addEventListener('click', () => renderArena(undefined, Number(b.dataset.round))));
hooks.design = { count: 4, apply: k => k === 0 ? renderArena('C', 0) : renderArena('D', k) };
renderArena('C', 0);

/* ───────── 04 結果 ───────── */
const METRICS = {
  acc: { c: 58.3, d: 55.0, digits: 1, unit: '%', diff: '−3.3 個百分點', p: 'Holm 校正後 p = 0.42', max: 100,
    rows: [['C 固定立場', 58.3, ''], ['D 立場交換', 55.0, 'd'], ['一律看多', 62.2, 'ref']],
    note: '180 個季度案例；C 105／180、D 99／180。條紋列「一律看多」（112／180）是看到結果後才加入的事後基準，不屬主要比較，相對 C、D 的事後檢定也未達顯著。' },
  sharpe: { c: 0.59, d: 0.54, digits: 2, unit: '', diff: '−0.05', p: 'Holm 校正後 p = 0.80', max: 1.2,
    rows: [['C 固定立場', 0.59, ''], ['D 立場交換', 0.54, 'd'], ['買進持有', 1.01, 'ref']],
    note: '由 180 案形成的 1,219 個交易日日序列計算。條紋列是同配置買進持有的描述性參照，報告沒有檢定它與 C、D 的 Sharpe 差。' }
};
let revealed = false, metric = 'acc';
function countUp(el, to, digits, unit) {
  if (REDUCED) { el.textContent = to.toFixed(digits) + unit; return; }
  const t0 = performance.now(), dur = 1300;
  (function f(now) {
    const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = (to * e).toFixed(digits) + unit;
    if (k < 1) requestAnimationFrame(f);
  })(t0);
}
function renderMetric(key = metric) {
  metric = key; const m = METRICS[key];
  $$('[data-metric]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.metric === key)));
  countUp($('#num-c'), m.c, m.digits, m.unit); countUp($('#num-d'), m.d, m.digits, m.unit);
  $('#num-d-c').textContent = m.diff; $('#num-p').textContent = m.p; $('#metric-note').textContent = m.note;
  const bars = $('#bars'); bars.replaceChildren();
  m.rows.forEach(([label, value, cls]) => {
    const row = document.createElement('div'); row.className = `bar-row ${cls}`;
    const name = document.createElement('span'); name.textContent = label;
    const trk = document.createElement('div'); trk.className = 'trk';
    const fill = document.createElement('div'); fill.className = 'fill'; trk.append(fill);
    const num = document.createElement('b'); num.textContent = value.toFixed(m.digits) + m.unit;
    row.append(name, trk, num); bars.append(row);
    requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.width = `${value / m.max * 100}%`; }));
  });
}
function setRevealed(on) {
  if (on === revealed) return;
  revealed = on;
  $('#sealed').hidden = on; $('#opened').hidden = !on;
  $('#results').dataset.field = on ? 'converge' : 'fixed';
  if (on) renderMetric();
  if (scenes[state.i].id === 'results') refreshField();
}
$('#reveal').addEventListener('click', () => { if (state.deck) next(); else setRevealed(true); });
$$('[data-metric]').forEach(b => b.addEventListener('click', () => renderMetric(b.dataset.metric)));
hooks.results = { count: 1, apply: k => setRevealed(k >= 1) };

/* ───────── 05 分歧地圖 ─────────
   16 個 C／D 方向不同的案例，取自 ../story-cases.json（180 案凍結證據包的靜態匯出）。
   欄位：股票、分析日、C 決策、D 決策、C 是否正確、60 個交易日標的價格變動（%，非策略報酬）。 */
const TICKERS = ['AAPL', 'NVDA', 'GOOGL', 'MSFT', 'AMZN', 'JPM', 'MCD', 'INTC', 'GE'];
const QUARTERS = []; for (let y = 2021; y <= 2025; y++) for (const q of ['03-31', '06-30', '09-30', '12-31']) QUARTERS.push(`${y}-${q}`);
const SPLIT = [['JPM', '2021-03-31', 'B', 'S', 1, 1.8], ['MCD', '2022-06-30', 'S', 'B', 1, -0.2], ['AAPL', '2022-09-30', 'S', 'B', 1, -6.0], ['GE', '2022-09-30', 'B', 'S', 1, 32.4],
  ['AAPL', '2022-12-31', 'B', 'S', 1, 24.2], ['GOOGL', '2022-12-31', 'S', 'B', 0, 12.6], ['AAPL', '2023-03-31', 'B', 'S', 1, 15.3], ['AMZN', '2023-03-31', 'B', 'S', 1, 25.9],
  ['JPM', '2023-03-31', 'B', 'S', 1, 8.7], ['NVDA', '2023-03-31', 'S', 'B', 0, 51.1], ['AAPL', '2024-03-31', 'B', 'S', 1, 23.7], ['INTC', '2024-03-31', 'B', 'S', 0, -30.5],
  ['MCD', '2024-03-31', 'B', 'S', 0, -8.2], ['INTC', '2024-06-30', 'B', 'S', 0, -25.8], ['JPM', '2025-03-31', 'B', 'S', 1, 18.5], ['JPM', '2025-09-30', 'B', 'S', 1, 5.3]];
const STORIES = {
  'INTC|2024-03-31': '新聞情緒偏正面、近 20 日報酬為正，營收、淨利與營業現金流卻比去年同期大幅衰退。C 採納短期動能而買進；D 在交換輪反駁自己原本的看多理由，裁決認為基本面惡化更重要而賣出。',
  'AAPL|2023-03-31': '近 20 日上漲 11.3%、技術動能強，營收與淨利卻比去年下降。C 採納技術動能而買進；D 在交換輪再次強調基本面衰退，裁決因此賣出。同樣的推理，這次猜錯。'
};
const word = x => x === 'B' ? '買進' : '賣出';
const grid = $('#grid'), panel = $('#case-panel');
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function panelDefault() {
  panel.replaceChildren(el('h3', '16 / 180'), el('p', 'C、D 方向不同的案例。其餘 164 案兩組做出相同方向的決定。'),
    el('p', 'C 對 11 案、D 對 5 案；精確 McNemar 檢定 p ≈ 0.21。', 'big-note'),
    el('p', '點亮起的格子看個別案例。白色是 C 對，萊姆色是 D 對。這些只是描述，不能據此推論因果。'));
}
function panelCase(row) {
  const [tk, date, c, d, cOk, move] = row;
  const dl = el('dl');
  dl.append(el('dt', 'C'), el('dd', `${word(c)}（${cOk ? '方向正確' : '方向錯誤'}）`), el('dt', 'D'), el('dd', `${word(d)}（${cOk ? '方向錯誤' : '方向正確'}）`));
  const big = el('p', `${move >= 0 ? '+' : '−'}${Math.abs(move).toFixed(1)}%`, 'big');
  panel.replaceChildren(el('h3', `${tk} · ${date}`), big, el('p', '之後 60 個交易日的標的價格變動（開盤至開盤，未扣成本，不是策略報酬）。'), dl);
  const story = STORIES[`${tk}|${date}`];
  panel.append(el('p', story || '逐輪論點摘要：報告未提供。'));
  if (story) panel.append(el('p', '事後挑選的說明案例，不能代表全部分歧案例。', 'fine'));
}
TICKERS.forEach(tk => {
  grid.append(el('span', tk, 'tk'));
  QUARTERS.forEach(q => {
    const row = SPLIT.find(r => r[0] === tk && r[1] === q);
    if (!row) { grid.append(el('span', null, 'cell')); return; }
    const b = el('button', null, `cell ${row[4] ? 'cwin' : 'dwin'}`); b.type = 'button';
    b.dataset.win = row[4] ? 'C' : 'D';
    b.setAttribute('aria-label', `${tk} ${q}，${row[4] ? 'C' : 'D'} 方向正確`);
    b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', () => {
      const was = b.getAttribute('aria-pressed') === 'true';
      $$('button.cell', grid).forEach(x => x.setAttribute('aria-pressed', 'false'));
      if (was) panelDefault(); else { b.setAttribute('aria-pressed', 'true'); panelCase(row); }
    });
    grid.append(b);
  });
});
$$('[data-win]', $('#map .seg')).forEach(b => b.addEventListener('click', () => {
  $$('[data-win]', $('#map .seg')).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
  $$('button.cell', grid).forEach(c => c.classList.toggle('off', b.dataset.win !== 'all' && c.dataset.win !== b.dataset.win));
}));
panelDefault();

/* ───────── 07 RQ2 ───────── */
const CELLS = {
  AA: 'AA：看多、看空都用 qwen3:32b。同質基準，在 RQ2 的協議內重跑，不沿用 RQ1 的數字。',
  AB: 'AB：原看多 = qwen3:32b，原看空 = gemma3:27b。和 BA 是同一案的兩種指派，不能當成兩倍的獨立樣本。',
  BA: 'BA：原看多 = gemma3:27b，原看空 = qwen3:32b。兩種指派都跑，才不會讓同一個模型永遠當看多方。',
  BB: 'BB：兩邊都用 gemma3:27b。用來分辨差異來自「模型不同」，還是單純因為 B 這個模型比較強或比較弱。'
};
function renderCell(key) {
  $$('[data-cell]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.cell === key)));
  $('#matrix-text').textContent = CELLS[key];
}
$$('[data-cell]').forEach(b => b.addEventListener('click', () => renderCell(b.dataset.cell)));
renderCell('AA');

/* ───────── 08 RQ3 ───────── */
const ARMS = {
  C_domain: ['領域分工辯論', '每案 29 次呼叫', '四個領域各自多空辯論三輪（24 次），每個領域一次 View 裁決（4 次），最後由 Final Aggregator 整合（1 次）。這是 RQ3 要檢驗的架構。'],
  C: ['通才辯論', '每案 7 次呼叫', '與 RQ1 的 C 相同：看多、看空讀同一份整合報告辯三輪。C_domain 對 C 回答的是整套架構的差，包含算力差。'],
  C_budget: ['同算力的通才', '每案 29 次呼叫', '28 次獨立提案加 1 次裁決，資訊不切分。C_domain 對 C_budget 用來排除「只是多跑了幾次」。時間不夠時優先保留這一組。'],
  C_partition: ['切資訊但不辯論', '每案 1 次呼叫', '證據照四個領域切好，直接裁決一次。C_domain 對 C_partition 比較分工辯論與直接裁決的整體差異（兩者呼叫數不同）。']
};
function renderArm(key) {
  $$('[data-rq3]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.rq3 === key)));
  const [name, calls, text] = ARMS[key];
  const h = el('h3', `${key} · ${name}`); h.append(el('span', calls));
  $('#arm-text').replaceChildren(h, el('p', text));
}
$$('[data-rq3]').forEach(b => b.addEventListener('click', () => renderArm(b.dataset.rq3)));
renderArm('C_domain');

/* ───────── 啟動 ───────── */
const first = Math.max(0, scenes.findIndex(s => `#${s.id}` === location.hash));
mark(first);
if (first > 0) scenes[first].scrollIntoView({ behavior: 'instant' });
onScroll();
addEventListener('hashchange', () => {
  const i = scenes.findIndex(s => `#${s.id}` === location.hash);
  if (i >= 0 && i !== state.i) goto(i);
});
