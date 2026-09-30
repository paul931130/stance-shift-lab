// Formal studies: one card per preregistered sample with batch progress, an
// honest ETA, GPU state (incl. auto-stop) and whole-study controls. This is
// the screen for "run the 180 cases and don't waste GPU time".
import { $, escape, notify, formatStamp } from './ui.js';
import { api, task } from './api.js';

const GPU_POLL_MS = 60000;
let studies = [], gpu = null, gpuFetchedAt = 0;
const expanded = new Set();

function hours(value) {
  if (value == null) return '—';
  if (value < 1) return `${Math.max(1, Math.round(value * 60))} 分鐘`;
  return `${value.toFixed(1)} 小時`;
}

function gpuLine() {
  if (!gpu) return '<p class="hint">GPU 狀態讀取中…</p>';
  if (!gpu.configured) return '<p class="hint">未設定 GPUtw；GPU 需自行在 GPUtw 控制台開關。</p>';
  const status = gpu.instance?.status || (gpu.status === 'error' ? '無法讀取' : '未指定執行個體');
  const auto = gpu.autostop;
  const failed = auto?.last_action && auto.last_action.status !== 'stopped';
  const autoText = !auto ? '' : !auto.enabled
    ? ' · 自動關機未啟用（需 GPUtw 金鑰與 GPUTW_INSTANCE_ID）'
    : failed ? ` · 自動關機失敗：${auto.last_action.message || auto.last_action.status}`
    : auto.idle_minutes == null
      ? ` · 佇列閒置 ${auto.idle_minutes_limit} 分鐘後自動關機`
      : ` · 已閒置 ${auto.idle_minutes} 分鐘，${Math.max(0, auto.idle_minutes_limit - auto.idle_minutes).toFixed(0)} 分鐘後自動關機`;
  const running = status === 'RUNNING';
  return `<p class="study-gpu ${running ? 'on' : 'off'}"><i aria-hidden="true"></i>GPU ${escape(status)}${escape(autoText)}${
    auto?.last_action ? `<br><small>上次自動關機：${escape(formatStamp(auto.last_action.at))}（${escape(auto.last_action.status)}）</small>` : ''}</p>`;
}

function card(study) {
  const p = study.progress, c = p.counts;
  const title = p.version ? `${p.version} · ${p.model || ''}` : `協議 ${study.protocol_hash.slice(0, 8)}（尚未排入）`;
  const pct = Math.round((p.done_fraction || 0) * 100);
  const state = !p.current ? '舊版協議：只能查看，不能續跑'
    : p.active ? (p.eta_hours != null ? `預估還要 ${hours(p.eta_hours)}（${p.rate_cases_per_hour} 案／小時）` : '執行中，完成 3 案後估算剩餘時間')
    : c.complete === p.total ? '全部完成' : p.errors.length ? '已停止：有錯誤待處理' : p.not_created ? '尚未排入' : '已暫停';
  const actionable = p.current;
  const errors = p.errors.length ? `<details class="study-errors"${expanded.has(study.protocol_hash) ? ' open' : ''} data-errors="${escape(study.protocol_hash)}">
      <summary>${p.errors.length} 案因錯誤暫停</summary>
      <ul>${p.errors.slice(0, 20).map(e => `<li><button type="button" class="linkish" data-open="${escape(e.id)}">${escape(e.ticker)} · ${escape(e.analysis_date)}</button><small>${escape(e.error)}</small></li>`).join('')}</ul>
      ${p.errors.length > 20 ? `<p class="hint">另有 ${p.errors.length - 20} 案，請用佇列篩選「已暫停」。</p>` : ''}
    </details>` : '';
  return `<article class="study-card" data-study="${escape(study.protocol_hash)}">
    <header><strong>${escape(title)}</strong><small>登記 ${escape(formatStamp(p.frozen_at))} · ${escape(study.protocol_hash.slice(0, 8))}</small></header>
    <div class="study-meter" role="progressbar" aria-valuemin="0" aria-valuemax="${p.total}" aria-valuenow="${c.complete}" aria-label="已完成案例"><i data-ratio="${pct}"></i></div>
    <p class="study-count"><b>${c.complete}</b> / ${p.total} 完成 · ${pct}%</p>
    <p class="study-state">${escape(state)}</p>
    <ul class="study-breakdown">
      <li>執行中 ${c.running}</li><li>等待 ${c.queued}</li><li class="${c.paused ? 'warn' : ''}">暫停 ${c.paused}</li>${p.not_created ? `<li class="warn">未排入 ${p.not_created}</li>` : ''}
    </ul>
    ${errors}
    <div class="study-actions">
      ${actionable && p.not_created ? `<label class="button-like">排入批次檔…<input type="file" accept=".json,application/json" data-enqueue="${escape(study.protocol_hash)}" hidden></label>` : ''}
      ${actionable && c.paused ? `<button type="button" data-study-command="resume" data-hash="${escape(study.protocol_hash)}">全部繼續（${c.paused}）</button>` : ''}
      ${p.active ? `<button type="button" class="quiet" data-study-command="pause" data-hash="${escape(study.protocol_hash)}">全部暫停</button>` : ''}
    </div>
  </article>`;
}

// Current-version studies that still need work come first; finished or old ones fold away.
const isLive = s => s.progress.current && s.progress.counts.complete < s.progress.total;

function render() {
  const box = $('studies');
  if (!box) return;
  if (!studies.length) {
    box.innerHTML = gpuLine() + '<p class="hint">尚無事前登記的研究。在「建立實驗」匯入批次並勾選事前登記後，會出現在這裡。</p>';
    return;
  }
  const live = studies.filter(isLive), other = studies.filter(s => !isLive(s));
  const otherOpen = box.querySelector('details.study-others')?.open ? ' open' : '';
  box.innerHTML = gpuLine() + (live.length ? live.map(card).join('') : '<p class="hint">目前沒有待執行的正式研究。</p>')
    + (other.length ? `<details class="study-others"${otherOpen}><summary>其他 ${other.length} 個研究（已完成或舊版）</summary>${other.map(card).join('')}</details>` : '');
  for (const bar of box.querySelectorAll('.study-meter i')) bar.style.width = `${bar.dataset.ratio}%`;
}

export async function refreshStudies({gpuNow = false} = {}) {
  const now = Date.now();
  const wantGpu = gpuNow || now - gpuFetchedAt > GPU_POLL_MS;
  const [list, gpuStatus] = await Promise.all([api('/api/studies'),
    wantGpu ? api('/api/gputw/status').catch(() => null) : Promise.resolve(gpu)]);
  studies = list;
  if (wantGpu) { gpu = gpuStatus; gpuFetchedAt = now; }
  render();
}

async function enqueueFile(hash, file) {
  let payload;
  try { payload = JSON.parse(await file.text()); }
  catch { throw new Error('批次檔不是有效的 JSON'); }
  if (!Array.isArray(payload.cases)) throw new Error('批次檔需要 cases 陣列');
  const result = await api(`/api/studies/${encodeURIComponent(hash)}/enqueue`, payload);
  notify(`已排入 ${result.created} 案${result.skipped_existing ? `，略過已建立的 ${result.skipped_existing} 案` : ''}。`);
}

export function initStudyPanel(onChange) {
  const box = $('studies');
  box.addEventListener('toggle', e => {
    const hash = e.target.dataset?.errors;
    if (hash) { if (e.target.open) expanded.add(hash); else expanded.delete(hash); }
  }, true);
  box.addEventListener('change', e => {
    const input = e.target.closest('[data-enqueue]');
    if (!input?.files?.[0]) return;
    task(null, async () => { await enqueueFile(input.dataset.enqueue, input.files[0]); await onChange(); });
  });
  box.addEventListener('click', e => {
    const button = e.target.closest('[data-study-command]');
    if (!button) return;
    const {studyCommand: command, hash} = button.dataset;
    if (command === 'pause' && !confirm('暫停這個研究的所有案例？執行中的呼叫完成後才會停下，進度都會保存。')) return;
    task(button, async () => {
      const result = await api(`/api/studies/${encodeURIComponent(hash)}/${command}-all`, {});
      notify(`${command === 'pause' ? '已暫停' : '已繼續'} ${result.changed} 案。`);
      await onChange();
    });
  });
  $('gpu-refresh')?.addEventListener('click', e => task(e.currentTarget, () => refreshStudies({gpuNow: true})));
}
