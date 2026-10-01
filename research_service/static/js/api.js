import { $, notify } from './ui.js';
import { emit } from './store.js';

// Keep a stalled browser request from making the whole workspace look frozen.
// GETs are safe to retry once because they do not create jobs or mutate data.
const API_TIMEOUT_MS = 15000, API_GET_RETRY_LIMIT = 1;
export const BATCH_TIMEOUT = {timeoutMs: 180000};

// Batch operations validate every case (hundreds of datasets) and pass a longer timeoutMs.
export async function api(path, body, method, {timeoutMs = API_TIMEOUT_MS} = {}) {
  const verb = (method || (body === undefined ? 'GET' : 'POST')).toUpperCase();
  const retryable = verb === 'GET';
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
