import { $, notify } from './ui.js';
import { emit } from './store.js';

// Keep a stalled browser request from making the whole workspace look frozen.
// GETs are safe to retry once because they do not create jobs or mutate data.
const API_TIMEOUT_MS = 15000, API_GET_RETRY_LIMIT = 1;
export const BATCH_TIMEOUT = {timeoutMs: 180000};

// GitHub Pages demo. Without a recorded timeline, GETs return the last recorded response. With one, the
// launch call (first recorded non-GET to jobs/studies/batches) starts a live-speed replay of the timeline.
const demoClock = {t: null, anchorWall: 0, anchorT: 0};
const demoBase = key => key.split('?')[0];
const demoLaunch = e => e.method !== 'GET' && /^\/api\/(jobs|studies|batches)/.test(e.key) && !e.key.endsWith('/preflight');
function demoNow(timeline) {
  if (demoClock.t === null) {
    const launch = timeline.find(demoLaunch);
    const start = launch ? launch.t : timeline[timeline.length - 1].t;
    demoClock.t = new URLSearchParams(location.search).get('final') === '1' ? Infinity : start - 0.01;
  }
  if (!demoClock.anchorWall || demoClock.t === Infinity) return demoClock.t;
  return demoClock.anchorT + (performance.now() - demoClock.anchorWall) / 1000;
}
function staticDemo(path, verb) {
  const {responses = {}, timeline = []} = globalThis.STATIC_DEMO;
  const readOnly = () => new Error('這是線上展示版，無法新增或修改；完整功能請在本機執行系統。');
  const missing = () => new Error('線上展示版沒有這項資料');
  const fallback = () => {
    const key = path in responses ? path : demoBase(path);
    if (!(key in responses)) throw missing();
    return structuredClone(responses[key]);
  };
  if (!timeline.length) {
    if (verb !== 'GET') throw readOnly();
    return fallback();
  }
  const now = demoNow(timeline), base = demoBase(path);
  const latest = match => timeline.filter(e => e.t <= now && e.method === verb && match(e)).pop();
  if (verb === 'GET') {
    // Prefer the exact request, unless the same endpoint was recorded more recently with another
    // query (e.g. /api/dashboard?selected=…): then use that newer state minus the unrequested detail.
    const exact = latest(e => e.key === path), recent = latest(e => demoBase(e.key) === base);
    if (!exact && !recent) return fallback();
    if (exact && exact.t >= recent.t) return structuredClone(exact.response);
    const data = structuredClone(recent.response);
    if (path === base && data && typeof data === 'object' && 'selected' in data) data.selected = null;
    return data;
  }
  const same = timeline.filter(e => e.method === verb && demoBase(e.key) === base);
  if (!same.length) throw readOnly();
  const launchT = timeline.find(demoLaunch)?.t;
  const launch = same.find(e => demoLaunch(e) && e.t >= launchT);
  // Start one second past the launch so the UI's immediate refresh already sees the queued job.
  if (launch) Object.assign(demoClock, {anchorWall: performance.now(), anchorT: launch.t + 1});
  return structuredClone((launch || same[same.length - 1]).response);
}

// Batch operations validate every case (hundreds of datasets) and pass a longer timeoutMs.
export async function api(path, body, method, {timeoutMs = API_TIMEOUT_MS} = {}) {
  const verb = (method || (body === undefined ? 'GET' : 'POST')).toUpperCase();
  const retryable = verb === 'GET';
  // GitHub Pages demo: answer from responses recorded in demo mode; nothing can really be changed.
  if (globalThis.STATIC_DEMO) return staticDemo(path, verb);
  let lastError;
  for (let attempt = 0; attempt <= (retryable ? API_GET_RETRY_LIMIT : 0); attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(path, {
        method: verb,
        headers: body === undefined ? {} : {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      let data;
      try { data = await response.json(); }
      catch { data = {detail: `服務回傳了無法讀取的內容（HTTP ${response.status}）`}; }
      if (!response.ok) {
        if (response.status === 401) { $('login').hidden = false; $('workspace').hidden = true; }
        // FastAPI validation errors are a list of {loc, msg}; show them as "field: reason".
        const detail = typeof data.detail === 'string' ? data.detail
          : Array.isArray(data.detail) ? '輸入內容不正確：' + data.detail.map(d => `${(d.loc || []).slice(1).join('.') || '內容'}：${d.msg}`).join('；')
          : JSON.stringify(data.detail || data);
        const error = new Error(detail || `服務請求失敗（HTTP ${response.status}）`);
        // A transient upstream error gets one quiet retry; validation and
        // authentication errors are returned immediately so users see the cause.
        if (!(retryable && (response.status === 408 || response.status === 429 || response.status >= 500) && attempt < API_GET_RETRY_LIMIT)) {
          error.noRetry = true;
          throw error;
        }
        lastError = error;
      } else return data;
    } catch (error) {
      clearTimeout(timeout);
      lastError = error?.name === 'AbortError'
        ? new Error(`服務回應逾時（${timeoutMs / 1000} 秒）；請確認 Docker Desktop 與研究服務仍在執行。`)
        : error;
      if (error?.noRetry || !(retryable && attempt < API_GET_RETRY_LIMIT)) throw lastError;
    }
    await new Promise(resolve => setTimeout(resolve, 400 * (attempt + 1)));
  }
  throw lastError || new Error('服務請求失敗');
}

// Run a user action: disable its button, surface errors as notices, and let
// the experiment guard re-evaluate afterwards.
export async function task(button, fn) {
  if (button) button.disabled = true;
  try { await fn(); }
  catch (error) { notify(error.message, true); }
  finally { if (button) button.disabled = false; emit('task:settled'); }
}
