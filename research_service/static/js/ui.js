// Shared DOM helpers, formatting and notices. No research state lives here.
import { state } from './store.js';

export const $ = (id) => document.getElementById(id);
export const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const percentage = value => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
export const number = value => value == null ? '—' : Number(value).toFixed(3);
export const statuses = {queued:'等待執行',running:'執行中',paused:'已暫停',complete:'已完成',cancelled:'已取消'};
export const COLLECTION_DOMAINS = ['technical','fundamental','sentiment','macro'];
export const DOMAIN_LABELS = {technical:'技術面',fundamental:'基本面',sentiment:'情緒面',macro:'總經面'};

export function friendlyJobError(error) {
  const value = String(error || '');
  if (/HTTP Error 403|HTTP 403|拒絕連線/.test(value)) return '模型服務拒絕連線（HTTP 403）。請檢查遠端 Ollama 連接埠或存取 key；這不是 NoTrade。';
  if (/HTTP Error 429|HTTP 429|限流/.test(value)) return '模型服務暫時限流（HTTP 429），稍後按「繼續執行」重試；這不是 NoTrade。';
  if (/evidence_id|研究代理人引用/.test(value)) return '模型輸出引用了不存在的證據，已標記為可重試錯誤；這不是 NoTrade。';
  return value;
}

export function options(items) { return items.map(v => `<option value="${escape(v)}">${escape(v)}</option>`).join(''); }
export function modelOptions(items, details) {
  const byId = new Map((details || []).map(item => [item.id, item]));
  return items.map(value => {
    const detail = byId.get(value), size = detail?.parameter_size, count = Number.parseFloat(size);
    const formalSmall = value.trim().toLowerCase() === 'ollama/qwen3:8b';
    const suffix = size ? ` · ${size}${Number.isFinite(count) && count < 14 && !formalSmall ? ' · 僅冒煙' : ''}` : '';
    return `<option value="${escape(value)}">${escape(value + suffix)}</option>`;
  }).join('');
}
export function formatStamp(value) {
  try { return new Intl.DateTimeFormat('zh-TW',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(value)); }
  catch { return value || '—'; }
}
export function terminalStamp(value = new Date()) {
  try { return new Intl.DateTimeFormat('zh-TW',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(value); }
  catch { return '--:--:--'; }
}

export function datasetCut(d) { return d.requested_analysis_date || (d.used_analysis_dates || []).slice(-1)[0] || null; }
export function datasetLabel(d) {
  const cut = datasetCut(d);
  return `${d.ticker} · ${d.kind === 'synthetic' ? '合成測試' : '歷史資料'} v${d.version} · ${cut ? `研究日 ${cut}` : '研究日未記錄'} · 未來行情終點 ${d.price_end}（只供回測）`;
}
export function missingPolicyLabel(protocol = {}) {
  return (protocol.missing_data_policy || 'force_no_trade') === 'allow_decision' ? '缺資料對照 · 保留模型決策' : '保守門檻 · 強制 NoTrade';
}
export function protocolLabel(protocol = {}) {
  const version = protocol.version || '未記錄';
  return `協議 ${version}${state.currentProtocolVersion && version !== state.currentProtocolVersion ? ' · 舊版結果' : ''}`;
}
export function traceMessage(node = '') {
  if (node === 'coordinator') return 'Coordinator 鎖定資料集、分析日與研究協議';
  if (node.startsWith('parallel_research_agents')) return '派出技術、基本面、情緒、總經四個研究 Agent';
  if (node === 'neutral_report_locked') return '四個面向的摘要已合併，中立研究報告已鎖定';
  if (node.startsWith('parallel_decision_wave')) return `決策波次：${node.slice(node.indexOf('[') + 1, -1)}`;
  if (node === 'gatekeeper_decisions_locked') return 'Gatekeeper 已核對引用、資料覆蓋與風險門檻';
  if (node === 'backtest_and_memory_write') return '回測結果與供後續案例參考的記憶已儲存';
  return node.replaceAll('_', ' ');
}

// ---------- Notices ----------
let notices = [], noticeSeq = 0;
function renderNotices() {
  const el = $('notice');
  el.hidden = notices.length === 0;
  el.innerHTML = notices.map(n => `<div class="notice-item ${n.error ? 'error' : ''}"><span>${escape(n.message)}</span><button type="button" data-dismiss-notice="${n.id}" aria-label="關閉通知">×</button></div>`).join('');
}
export function dismissNotice(id) { notices = notices.filter(n => n.id !== id); renderNotices(); }
export function notify(message, error = false) {
  const id = ++noticeSeq;
  notices.push({id, message, error});
  if (notices.length > 4) notices.shift();
  renderNotices();
  if (!error) setTimeout(() => dismissNotice(id), 8000);
}
document.addEventListener('click', e => {
  const button = e.target.closest('[data-dismiss-notice]');
  if (button) dismissNotice(Number(button.dataset.dismissNotice));
});

export const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
