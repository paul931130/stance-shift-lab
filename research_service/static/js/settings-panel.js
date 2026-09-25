// Server-side source/model settings and the read-only GPUtw status check.
import { $, escape, notify } from './ui.js';
import { api, task } from './api.js';

const GROUPS = [
  {title: '回測資料來源', names: ['SEC_USER_AGENT', 'FRED_API_KEY', 'ALPHA_VANTAGE_API_KEY']},
  {title: '回測模型', names: ['DEFAULT_MODEL']},
  {title: 'GPUtw／遠端 Ollama', names: ['GPUTW_API_URL', 'GPUTW_API_KEY', 'GPUTW_INSTANCE_ID', 'GPUTW_OLLAMA_BASE_URL', 'GPUTW_OLLAMA_API_KEY']},
  {title: '本機研究資料路徑', names: ['FNSPID_NEWS_PATH', 'ALPHA_VANTAGE_NEWS_PATH']},
  {title: '雲端模型金鑰（進階）', names: ['OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY'], collapsed: true},
];
const SOURCE_LABELS = {sec: 'SEC', alfred: 'FRED／ALFRED', alpha_vantage: 'Alpha Vantage', fnspid: 'FNSPID', finbert_local: '本機 FinBERT', gputw: 'GPUtw'};

const renderField = field => `<div class="setting-item"><label>${escape(field.label)} · <span class="setting-state${field.configured ? ' on' : ''}">${field.configured ? '已設定' : '未設定'}</span><input data-setting="${escape(field.name)}" type="${field.secret ? 'password' : 'text'}" autocomplete="off" value="${escape(field.display_value || '')}" placeholder="留白保留原值"></label><label class="check"><input type="checkbox" data-clear-setting="${escape(field.name)}">清除此設定</label></div>`;

export async function refreshSettings() {
  const settings = await api('/api/settings');
  const grouped = GROUPS.map(group => {
    const fields = settings.fields.filter(field => group.names.includes(field.name));
    if (!fields.length) return '';
    return group.collapsed
      ? `<details class="settings-group settings-advanced"><summary>${group.title}</summary><div class="settings-grid">${fields.map(renderField).join('')}</div></details>`
      : `<section class="settings-group"><h3>${group.title}</h3><div class="settings-grid">${fields.map(renderField).join('')}</div></section>`;
  }).join('');
  const known = new Set(GROUPS.flatMap(group => group.names));
  const other = settings.fields.filter(field => !known.has(field.name));
  $('settings-fields').innerHTML = grouped + (other.length ? `<section class="settings-group"><h3>其他設定</h3><div class="settings-grid">${other.map(renderField).join('')}</div></section>` : '');
}

function gputwText(config) {
  return config.gputw?.configured
    ? `GPUtw key 已設定${config.gputw.instance_configured ? ' · 已指定執行個體' : ''}${config.gputw.ollama_configured ? ' · 遠端 Ollama 已設定' : ''}；按「檢查 GPUtw 狀態」測試連線。`
    : 'GPUtw 尚未設定；可留白使用本機 Ollama。';
}

export function applySourceState(config) {
  $('source-state').innerHTML = Object.entries(config.sources)
    .map(([key, value]) => `<span class="source-chip${value ? ' on' : ''}">${escape(SOURCE_LABELS[key] || key)}</span>`).join('');
  $('gputw-state').textContent = gputwText(config);
}

$('settings-form').addEventListener('submit', e => {
  e.preventDefault();
  task(e.submitter, async () => {
    const values = {};
    document.querySelectorAll('[data-setting]').forEach(input => { if (input.value.trim()) values[input.dataset.setting] = input.value.trim(); });
    const clear = [...document.querySelectorAll('[data-clear-setting]:checked')].map(input => input.dataset.clearSetting);
    await api('/api/settings', {values, clear});
    await refreshSettings();
    notify('設定已儲存在伺服器並立即生效。');
    applySourceState(await api('/api/config'));
  });
});
$('gputw-check-button').addEventListener('click', e => task(e.currentTarget, async () => {
  const [s, resources] = await Promise.all([api('/api/gputw/status'), api('/api/gputw/resources')]);
  const statusText = s.status === 'ready' ? 'API 已連線' : s.status === 'not_configured' ? '尚未設定 GPUtw key' : (s.message || '狀態查詢失敗');
  const usage = resources.status === 'ready' ? ' · GPU 資源已回傳' : resources.status === 'needs_instance' ? ' · 尚未指定執行個體' : resources.status === 'not_configured' ? '' : ' · 資源查詢失敗';
  $('gputw-state').textContent = `${statusText}${usage}`;
  if (s.status === 'ready' && s.instance) notify(`GPUtw 執行個體狀態已取得：${s.instance.status || s.instance.state || '已回傳'}。`);
  else if (s.status === 'error') notify(s.message || 'GPUtw 查詢失敗', true);
}));
