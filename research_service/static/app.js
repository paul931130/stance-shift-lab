const $ = (id) => document.getElementById(id);
const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const percentage = value => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
const number = value => value == null ? '—' : Number(value).toFixed(3);
const statuses = {queued:'等待執行',running:'執行中',paused:'已暫停',complete:'已完成',cancelled:'已取消'};
let selectedJob = null, selectedProtocol = null, busy = false, datasetRows = [], parallelWorkers = 1, currentProtocolVersion = '', terminalEvents = [];
let currentTab = 'setup', currentFlow = 'data', autoStatsJob = null;
const TABS = ['setup', 'runs', 'stats'];
let modelDetails = new Map(), installedModels = new Set();
let submitting = false, scoring = false;
let hasActiveJobs = false, pollTimer = null, finbertReady = false, pollFailures = 0;
let allJobs = [];
const ACTIVE_POLL_MS = 3000, IDLE_POLL_MS = 30000, MAX_POLL_MS = 60000;
// Keep a stalled browser request from making the whole workspace look frozen.
// GETs are safe to retry once because they do not create jobs or mutate data.
const API_TIMEOUT_MS = 15000, API_GET_RETRY_LIMIT = 1;
function syncNextAction() {
  const box = $('next-action');
  if (!box) return;
  const active = allJobs.find(job => ['queued','running','paused'].includes(job.status));
  const completed = allJobs.some(job => job.status === 'complete');
  let step, title, detail, action = '';
  if (active) {
    step = '3 / 執行中'; title = '研究正在背景執行';
    detail = `${active.config?.ticker || '案例'} · ${statuses[active.status] || active.status}`;
    action = '<button type="button" data-next-tab="runs">查看執行紀錄</button>';
  } else if (completed) {
    step = '4 / 統計'; title = '已有完成案例可以檢視';
    detail = '前往執行紀錄查看報告，或開啟同協議統計。';
    action = '<button type="button" data-next-tab="runs">查看結果</button>';
  } else if ($('dataset')?.value || datasetRows.length) {
    step = '2 / 建立實驗'; title = $('dataset')?.value ? '資料集已選好，可以開始實驗' : '資料已就緒，請選一筆資料集';
    detail = $('dataset')?.value ? '確認模型與缺資料策略後，按下開始研究實驗。' : '進入下一步選擇資料集。';
    action = '<button type="button" data-next-flow="experiment">前往建立實驗</button>';
  } else {
    step = '1 / 資料準備'; title = '先準備第一筆研究資料';
    detail = '選股票與分析日，啟動四個資料 Agent。';
    action = '<button type="button" data-next-flow="data">開始準備資料</button>';
  }
  box.innerHTML = `<div class="next-step">${escape(step)}</div><strong>${escape(title)}</strong><span>${escape(detail)}</span>${action}`;
}
let notices = [], noticeSeq = 0;
function renderNotices() {
  const el = $('notice');
  el.hidden = notices.length === 0;
  el.innerHTML = notices.map(n => `<div class="notice-item ${n.error ? 'error' : ''}"><span>${escape(n.message)}</span><button type="button" data-dismiss-notice="${n.id}" aria-label="關閉通知">×</button></div>`).join('');
}
function dismissNotice(id) { notices = notices.filter(n => n.id !== id); renderNotices(); }
function notify(message, error = false) {
  const id = ++noticeSeq;
  notices.push({ id, message, error });
  if (notices.length > 4) notices.shift();
  renderNotices();
  if (!error) setTimeout(() => dismissNotice(id), 8000);
}
function syncUrl() {
  const params = new URLSearchParams();
  if (currentTab && currentTab !== 'setup') params.set('tab', currentTab);
  if (selectedJob) params.set('selected', selectedJob);
  const query = params.toString();
  const url = location.pathname + (query ? `?${query}` : '');
  if (location.pathname + location.search !== url) history.replaceState(null, '', url);
}
function setTab(tab, opts = {}) {
  if (!TABS.includes(tab)) tab = 'setup';
  currentTab = tab;
  const grid = $('workspace-grid');
  if (grid) grid.dataset.activeTab = tab;
  for (const name of TABS) {
    for (const el of document.querySelectorAll(`[data-tab-panel="${name}"]`)) el.hidden = name !== tab;
  }
  for (const btn of document.querySelectorAll('[data-tab-button]')) {
    const active = btn.dataset.tabButton === tab;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  }
  if (grid) grid.classList.toggle('full-width', tab !== 'setup');
  syncModeBanner();
  if (!opts.skipUrl) syncUrl();
}
function syncModeBanner() {
  const el = $('mode-banner');
  if (!el) return;
  const modes={
    setup:['操作台','在這裡準備資料、選模型、設定缺資料策略，最後啟動一筆回測實驗。'],
    runs:['監控台','在這裡查看四個研究 Agent、背景佇列、錯誤、決策與回測結果。'],
    stats:['統計報告','在這裡查看同協議統計、準確率、Hold 比例與研究限制。'],
    live:['即時觀察（選用）','這是上線資料觀察區，和歷史回測操作完全分開。'],
  };
  const [title,detail]=modes[currentTab]||modes.setup;
  const selectedStatus = allJobs.find(job=>job.id===selectedJob)?.status;
  const active = allJobs.some(job=>['queued','running','paused'].includes(job.status)) ? 3 : (selectedStatus==='complete' && currentTab==='stats' ? 4 : (currentTab==='setup' && currentFlow==='experiment' ? 2 : 1));
  const steps=[['1','準備資料'],['2','建立實驗'],['3','監控執行'],['4','查看統計']];
  el.innerHTML=`<div class="mode-copy"><strong>${escape(title)}</strong><span>${escape(detail)}</span></div><div class="workflow-steps">${steps.map(([n,label])=>`<span class="workflow-step ${n<=active?'done':''} ${Number(n)===active?'current':''}"><b>${n}</b>${label}</span>`).join('<i aria-hidden="true">›</i>')}</div>`;
}
async function api(path, body, method) {
  const verb = (method || (body === undefined ? 'GET' : 'POST')).toUpperCase();
  const retryable = verb === 'GET';
  let lastError;
  for (let attempt = 0; attempt <= (retryable ? API_GET_RETRY_LIMIT : 0); attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
    try {
      const response = await fetch(path, {
        method: verb,
        headers: body === undefined ? {} : {'Content-Type':'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      let data;
      try { data = await response.json(); }
      catch { data = {detail: `服務回傳了無法讀取的內容（HTTP ${response.status}）`}; }
      if (!response.ok) {
        if (response.status === 401) { $('login').hidden = false; $('workspace').hidden = true; }
        const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
        const error = new Error(detail || `服務請求失敗（HTTP ${response.status}）`);
        // A transient upstream error should get one quiet retry; validation and
        // authentication errors are returned immediately so users see the cause.
        if (!(retryable && (response.status === 408 || response.status === 429 || response.status >= 500) && attempt < API_GET_RETRY_LIMIT)) {
          error.noRetry = true;
          throw error;
        }
        lastError = error;
      } else return data;
    } catch (error) {
      clearTimeout(timeout);
      const timedOut = error?.name === 'AbortError';
      lastError = timedOut
        ? new Error(`服務回應逾時（${API_TIMEOUT_MS / 1000} 秒）；請確認 Docker Desktop 與研究服務仍在執行。`)
        : error;
      if (error?.noRetry || !(retryable && attempt < API_GET_RETRY_LIMIT)) throw lastError;
    }
    await new Promise(resolve => setTimeout(resolve, 400 * (attempt + 1)));
  }
  throw lastError || new Error('服務請求失敗');
}
function setFlow(flow) {
  currentFlow = flow === 'experiment' ? 'experiment' : 'data';
  for (const name of ['data','experiment']) {
    for (const el of document.querySelectorAll(`[data-flow-panel="${name}"]`)) el.hidden = name !== currentFlow;
  }
  for (const btn of document.querySelectorAll('[data-flow-tab]')) {
    const active = btn.dataset.flowTab === currentFlow;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  }
}
async function task(button, fn) { if (button) button.disabled = true; try { await fn(); } catch(error) { notify(error.message, true); } finally { if(button) button.disabled = false; syncExperimentGuard(); } }
function options(items) { return items.map(v => `<option value="${escape(v)}">${escape(v)}</option>`).join(''); }
function modelOptions(items, details) {
  const byId=new Map((details||[]).map(item=>[item.id,item]));
  return items.map(value=>{const detail=byId.get(value), size=detail?.parameter_size, count=Number.parseFloat(size);
    const suffix=size?` · ${size}${Number.isFinite(count)&&count<14?' · 僅冒煙':''}`:'';
    return `<option value="${escape(value)}">${escape(value+suffix)}</option>`;}).join('');
}
function formatStamp(value) { try { return new Intl.DateTimeFormat('zh-TW',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(value)); } catch { return value || '—'; } }
function terminalStamp(value=new Date()) { try { return new Intl.DateTimeFormat('zh-TW',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(value); } catch { return '--:--:--'; } }
function renderAgentTerminal() {
  const output=$('agent-terminal-output'); if(!output)return;
  output.innerHTML=terminalEvents.map(item=>`<div class="terminal-line ${escape(item.tone)}"><time>${escape(item.at)}</time><b>[${escape(item.agent)}]</b><span>${escape(item.message)}</span></div>`).join('')+'<div class="terminal-cursor" aria-hidden="true"><span>›</span><i></i></div>';
  output.scrollTop=output.scrollHeight;
}
function resetAgentTerminal() { terminalEvents=[]; renderAgentTerminal(); }
function terminalLine(agent,message,tone='') { terminalEvents.push({at:terminalStamp(),agent,message,tone}); if(terminalEvents.length>80)terminalEvents.shift(); renderAgentTerminal(); }
function datasetCut(d) { return d.requested_analysis_date || (d.used_analysis_dates || []).slice(-1)[0] || null; }
function datasetLabel(d) { const cut=datasetCut(d); return `${d.ticker} · ${d.kind === 'synthetic' ? '合成測試' : '歷史資料'} v${d.version} · ${cut ? `研究日 ${cut}` : '研究日未記錄'} · 未來行情終點 ${d.price_end}（只供回測）`; }
const collectorInfo={technical:['技術面 Agent','Yahoo 還原 OHLC'],fundamental:['基本面 Agent','SEC XBRL'],sentiment:['情緒面 Agent','Alpha Vantage／FNSPID'],macro:['總經面 Agent','ALFRED vintage']};
const collectorStatus={idle:'尚未啟動',running:'收集中',complete:'完成',needs_input:'待補資料',needs_configuration:'未設定來源',missing:'缺資料',error:'失敗'};
function missingPolicyLabel(protocol={}) { return (protocol.missing_data_policy||'force_no_trade')==='allow_decision'?'缺資料對照 · 保留模型決策':'保守門檻 · 強制 NoTrade'; }
function protocolLabel(protocol={}) { const version=protocol.version||'未記錄'; return `協議 ${version}${currentProtocolVersion&&version!==currentProtocolVersion?' · 舊版結果':''}`; }
function renderCollectionAgents(dataset=null, phase='idle') {
  const counts=dataset?.coverage?.domains||{};
  let complete=0, gaps=0;
  for(const [domain,[title,source]] of Object.entries(collectorInfo)){
    let status=phase;
    let message=phase==='running'?'正在並行蒐集與驗證…':source;
    if(dataset){
      const count=counts[domain]||0;
      status=(domain==='technical'?count>=61:count>0)?'complete':'missing';
      message=status==='complete'?`分析日前 ${count} 筆可用資料`:'分析日前資料不足';
    }
    if(status==='complete')complete++; else if(dataset)gaps++;
    const card=$(`collector-${domain}`); card.className=`agent-card ${status}`;
    card.innerHTML=`<b>${escape(title)}</b><small>${escape(source)}</small><span>${escape(collectorStatus[status]||status)}</span><p>${escape(message)}</p>`;
  }
  const readiness=$('data-readiness');
  if(phase==='running') readiness.textContent='四個資料 Agent 已啟動；技術、基本面與總經來源正在並行處理，情緒 Agent 同時檢查可用摘要。';
  else if(!dataset) readiness.textContent='選擇股票與研究分析日後，讓四個 Agent 開始蒐集與驗證資料。';
  else if(gaps===0) {
    const quality=dataset.coverage?.sentiment_quality||{}, pending=[];
    if(!dataset.coverage?.fundamental_quality?.passes_quality_gate)pending.push('SEC 基本面缺少可比較期間');
    if(quality.items>0 && !quality.passes_quality_gate)pending.push('新聞目標相關性未通過');
    if(quality.items>0 && !quality.finbert_complete)pending.push(`FinBERT ${quality.finbert_scored||0}/${quality.items}`);
    if(!dataset.coverage?.backtest_ready)pending.push('60 日後續行情不足');
    readiness.textContent=pending.length
      ? `四域證據完整；正式主實驗前仍需處理：${pending.join('、')}。`
      : '四域證據、新聞品質、FinBERT 與 60 日回測行情均已驗證，可啟動 A/B/C/D 四組實驗。';
  }
  else readiness.textContent=`資料結構與行情已驗證；${complete}/4 個領域就緒、${gaps} 個領域有缺口。可直接作為缺資料對照，系統會保留缺口標記並依你選的策略處理決策。`;
}
function renderDatasetDetail(alignDate = false) {
  const d=datasetRows.find(row=>row.id===$('dataset').value), detail=$('dataset-detail');
  if(!d){detail.hidden=true;detail.innerHTML='';$('analysis-date').disabled=false;$('score-finbert-button').disabled=true;$('analysis-date-help').textContent='分析日只使用 2021–2025 的季末切點；資料集的行情終點只供分析日後回測。';return;}
  const cut=datasetCut(d), uses=(d.used_analysis_dates||[]).join('、') || '尚未建立實驗';
  detail.hidden=false;
  const quality=d.coverage?.sentiment_quality;
  const fundamental=d.coverage?.fundamental_quality||{};
  const qualityText=quality
    ? `新聞目標相關率 ${percentage(quality.target_relevance_rate??quality.ticker_mention_rate)}（標題直接提及 ${percentage(quality.ticker_mention_rate)}） · ${quality.passes_quality_gate?'通過相關性':'未通過相關性'} · FinBERT ${quality.finbert_scored||0}/${quality.items||0}${quality.median_relevance==null?'':` · 中位相關性 ${number(quality.median_relevance)}`}`
    : '新聞相關性尚未計算';
  detail.innerHTML=`<span class="version">v${d.version}</span><strong>${escape(d.ticker)} · ${d.kind === 'synthetic' ? '合成測試' : '歷史資料'}</strong><br>研究前行情起點 ${escape(d.price_start)} · ${d.price_count} 個交易日 · ${d.evidence_count} 筆證據<br><b>${cut ? `研究分析日：${escape(cut)}` : '研究分析日：舊資料集未記錄'}</b> · 已用切點 ${escape(uses)}<br><b>未來行情終點：${escape(d.price_end)}（只供 30／60／90 日回測，不能選為分析日）</b><br><small>SEC 可比較指標 ${fundamental.comparative_items||0}/${fundamental.items||0} · ${escape(qualityText)}</small><br>建立 ${escape(formatStamp(d.created_at))} · ${escape(d.source)}<br><code title="完整資料集 ID">ID ${escape(d.id)}</code>`;
  if(alignDate && cut && [...$('analysis-date').options].some(option=>option.value===cut)) $('analysis-date').value=cut;
  $('analysis-date').disabled=Boolean(cut && d.kind==='historical');
  $('score-finbert-button').disabled=scoring || !finbertReady || !(d.evidence_by_domain?.sentiment > 0);
  const isLiveCase = cut && cut === new Date().toISOString().slice(0, 10);
  $('analysis-date-help').textContent=isLiveCase
    ? `這筆資料集的研究分析日是今天（${cut}）：屬於當下單次分析，未來交易日尚未發生，30／60／90 日回測會顯示「pending」，不計入正式研究統計。`
    : cut
    ? `這筆資料集的研究分析日是 ${cut}；${d.price_end} 是未來行情終點，只拿來計算分析日後 30／60／90 個交易日的回測。`
    : `這筆舊版或匯入資料未記錄研究分析日；請選計劃書的季末切點。${d.price_end} 是未來行情終點，不能當分析日。`;
}
function syncExperimentGuard() {
  const d=datasetRows.find(row=>row.id===$('dataset').value);
  const localModel=$('model').value, detail=modelDetails.get(localModel);
  const result=computeExperimentReadiness({
    dataset: d, analysisDate: $('analysis-date').value,
    allowLowQualitySentiment: $('allow-low-quality-sentiment').checked,
    allowPointFundamental: $('allow-point-fundamental').checked,
    allowSmallModel: $('allow-small-model').checked,
    cloudModel: $('cloud-model').value, localModel,
    localAvailable: installedModels.has(localModel),
    localParameterSize: detail?.parameter_size,
  });
  const guard=$('experiment-guard'), button=$('run-button');
  button.disabled=!result.ready || submitting;
  guard.classList.toggle('ready',result.ready);
  const messages={
    no_dataset:'尚未選擇資料集，因此不能啟動實驗。',
    date_mismatch:'資料集與研究分析日不一致，不能啟動實驗。',
    sentiment_quality:`新聞品質尚未通過：目標相關率 ${percentage(result.quality?.target_relevance_rate??result.quality?.ticker_mention_rate)}、FinBERT ${result.quality?.finbert_scored||0}/${result.quality?.items||0}；請建立新版或明確勾選資料品質敏感性覆寫。`,
    fundamental_quality:'此資料集只有不可比較的 SEC 點時欄位；請重新採集新版資料，或明確勾選點時基本面敏感性覆寫。',
    model_not_installed:`本機尚未安裝 ${result.localModel}；請改選已安裝模型或先安裝正式模型。`,
    model_too_small:`${result.localModel} 為 ${result.localParameterSize||'14B 以下'}；若只驗證流程，請勾選小模型冒煙測試。`,
    ready:'資料集、研究分析日、模型與新聞品質均已驗證；設定會一起鎖定於新實驗。',
  };
  guard.textContent=messages[result.reason];
  const overrideFor={sentiment_quality:'override-sentiment',fundamental_quality:'override-fundamental',model_too_small:'override-model'};
  for(const el of document.querySelectorAll('.check-wrap.needs-override'))el.classList.remove('needs-override');
  const neededId=overrideFor[result.reason];
  if(neededId){$('quality-overrides').open=true;$(neededId).classList.add('needs-override');}
}
async function refreshReadiness() {
  const r=await api('/api/readiness'), done=r.evidence_complete_cases??r.complete_cases, formal=r.formal_experiment_ready_cases??0, total=r.target_cases;
  const covered=r.tickers.filter(row=>row.complete>0).map(row=>`${row.ticker} 四域 ${row.complete}／正式 ${row.formal_ready||0}`).join('、') || '尚無完整案例';
  const split=r.temporal_splits?.splits||{};
  const splitLine=['training','validation','test'].filter(name=>split[name]).map(name=>`${escape(split[name].label)} ${split[name].formal_ready_cases}/${split[name].target_cases}`).join(' · ');
  $('study-readiness').innerHTML=`<strong>正式主實驗可跑 ${formal}/${total}</strong> · 四域證據完整 ${done} · SEC 可比較 ${r.comparable_fundamental_cases??0} · FinBERT 完整 ${r.finbert_ready_cases??0} · 60 日行情齊全 ${r.backtest_ready_cases} · 90 日也齊全 ${r.all_horizons_ready_cases??0}<br><small>時間切分：${splitLine||'尚未建立'}（Test 案例在最終評估前凍結）<br>本系統是固定模型推論；Training 只用於建構設定，Validation 用於調整，Test 最後才評估。<br>部分 ${r.partial_cases} · 尚缺 ${r.missing_cases}。${escape(covered)}。${escape(r.note)}</small>`;
  const gaps=await api('/api/readiness/gaps');
  const rows=(gaps.gap_cases||[]).map(row=>`<tr><td>${escape(row.ticker)}</td><td>${escape(row.analysis_date)}</td><td>${escape(row.status)}</td><td>${escape((row.deficits||[]).join('、'))}</td><td><code>${escape(row.collect_command)}</code></td></tr>`).join('');
  let gapBody=$('gap-inventory-body');
  if(!gapBody){
    $('study-readiness').insertAdjacentHTML('afterend','<details id="gap-inventory" class="gap-inventory"><summary>查看資料缺口與補資料指令</summary><p class="hint">每列只顯示尚未達正式主實驗門檻的案例；重新蒐集會建立新版快照，不會改寫舊實驗。</p><div id="gap-inventory-body"></div></details>');
    gapBody=$('gap-inventory-body');
  }
  gapBody.innerHTML=rows
    ? `<p class="hint">共 ${gaps.gap_count} 個缺口。先補「dataset」案例，再處理新聞品質或 SEC 可比較性。</p><div class="table-wrap gap-table"><table><thead><tr><th>股票</th><th>分析日</th><th>狀態</th><th>缺少項目</th><th>終端補資料指令</th></tr></thead><tbody>${rows}</tbody></table></div>`
    : '<p class="hint">全部研究案例均已達正式主實驗門檻。</p>';
}
function renderDatasetOptions(preserveValue) {
  const value = preserveValue !== undefined ? preserveValue : $('dataset').value;
  const search = ($('dataset-picker-search')?.value || '').trim().toLowerCase();
  const filtered = datasetRows.filter(d => !search || d.ticker.toLowerCase().includes(search) || d.id === value);
  $('dataset').innerHTML = '<option value="">請選擇資料集</option>' + filtered.map(d => `<option value="${escape(d.id)}">${escape(datasetLabel(d))}</option>`).join('');
  if (datasetRows.some(d => d.id === value)) $('dataset').value = value;
}
function renderDatasetPreviewList() {
  const search = ($('dataset-search')?.value || '').trim().toLowerCase();
  const filtered = datasetRows.filter(d => !search || d.ticker.toLowerCase().includes(search));
  if (!datasetRows.length) { $('datasets').innerHTML = ''; return; }
  $('datasets').innerHTML = filtered.length
    ? filtered.slice(0,5).map(d => `<div><span class="version">v${d.version}</span><strong>${escape(d.ticker)} · ${d.kind === 'synthetic' ? '合成測試' : '歷史資料'}</strong><br>研究分析日 ${escape(datasetCut(d)||'未記錄')}<br>未來行情終點 ${escape(d.price_end)}（只供回測）<br>${d.price_count} 個交易日 · ${d.evidence_count} 筆證據 · 建立 ${escape(formatStamp(d.created_at))}<br><code title="完整資料集 ID">ID ${escape(d.id)}</code><br>${escape(d.source)}</div>`).join('')
    : `<p class="hint">沒有符合條件的資料集（共 ${datasetRows.length} 筆）。</p>`;
}
async function refreshDatasets() {
  const previous = $('dataset').value;
  datasetRows = await api('/api/datasets');
  renderDatasetOptions(previous);
  renderDatasetPreviewList();
  renderDatasetDetail(true);
  renderCollectionAgents(datasetRows.find(d=>d.id===$('dataset').value)||null);
  const selected=datasetRows.find(d=>d.id===$('dataset').value);
  $('score-finbert-button').disabled=scoring || !finbertReady || !(selected?.evidence_by_domain?.sentiment > 0);
  syncExperimentGuard();
  syncNextAction();
}
async function refreshJobs() {
  let dashboard;
  try {
    dashboard = await api('/api/dashboard' + (selectedJob ? `?selected=${encodeURIComponent(selectedJob)}` : ''));
  } catch (error) {
    if (!selectedJob) throw error;
    // A URL restored from a bookmark or refresh may point at a job that no
    // longer exists (deleted store, different environment); fall back to the
    // unfiltered dashboard instead of leaving the whole page stuck on an error.
    selectedJob = null;
    syncUrl();
    dashboard = await api('/api/dashboard');
  }
  allJobs = dashboard.jobs;
  hasActiveJobs=allJobs.some(job=>job.status==='queued'||job.status==='running');
  renderJobList();
  syncNextAction();
  const completed = allJobs.find(job=>job.status==='complete');
  if (completed && autoStatsJob !== completed.id) {
    autoStatsJob = completed.id;
    if (currentTab === 'runs' && selectedJob === completed.id) setTab('stats');
  }
  if(dashboard.selected) await showJob(selectedJob,dashboard.selected);
  schedulePoll();
}
function renderJobList() {
  const search=($('job-search')?.value||'').trim().toLowerCase();
  const status=$('job-status-filter')?.value||'';
  const jobs=allJobs.filter(j=>(!status||j.status===status)
    &&(!search||`${j.config.ticker} ${j.config.analysis_date}`.toLowerCase().includes(search)));
  $('jobs').className = jobs.length ? '' : 'empty';
  if (!allJobs.length) { $('jobs').textContent='尚無實驗。先準備資料，再建立第一筆研究。'; return; }
  if (!jobs.length) { $('jobs').textContent=`沒有符合條件的實驗（共 ${allJobs.length} 筆）。`; return; }
  $('jobs').innerHTML = jobs.map(j => `<div class="job"><div><strong>${escape(j.config.ticker)} · ${escape(j.config.analysis_date)}</strong> <span class="status ${escape(j.status)}">${escape(statuses[j.status])}</span><small>${escape(j.config.protocol.model)} · ${j.steps}/${15 + j.config.protocol.voting_samples} 模型輸出${j.wants_run === 0 && j.status === 'running' ? ' · 將在本波次後暫停' : ''}</small><small>${escape(protocolLabel(j.config.protocol))} · ${escape(missingPolicyLabel(j.config.protocol))} · ${escape(j.config.protocol.study)} · ${j.id.slice(0,8)}</small></div><button class="quiet" data-open="${escape(j.id)}">檢視</button></div>`).join('');
}
function schedulePoll() {
  if(pollTimer)clearTimeout(pollTimer);
  pollTimer=null;
  if($('workspace').hidden || document.hidden)return;
  const baseDelay=hasActiveJobs?ACTIVE_POLL_MS:IDLE_POLL_MS;
  const delay=Math.min(MAX_POLL_MS,baseDelay*(2**Math.min(pollFailures,2)));
  pollTimer=setTimeout(async()=>{
    if(document.hidden || $('workspace').hidden)return;
    if(busy){schedulePoll();return;}
    busy=true;
    try{await refreshJobs();pollFailures=0;}
    catch(error){pollFailures=Math.min(pollFailures+1,2);notify(`無法更新狀態：${error.message}`,true);}
    finally{busy=false;schedulePoll();}
  },delay);
}
function researchAgentPanel(s, jobStatus) {
  const labels={technical:'技術面',fundamental:'基本面',sentiment:'情緒面',macro:'總經面'};
  const cards=Object.entries(labels).map(([domain,label])=>{
    const item=(s.research||{})[domain];
    const status=item?.status==='complete'?'complete':item?.status==='degraded'?'degraded':item?.status==='missing'?'missing':s.inputs&&jobStatus==='running'?'running':'idle';
    const state={complete:'分析完成',degraded:'來源摘錄完成',missing:'資料缺口',running:'分析中',idle:'等待資料'}[status];
    return `<article class="agent-card ${status}"><b>${label}研究 Agent</b><small>${escape(domain)}</small><span>${state}</span><p>${escape(item?.summary||'等待 Coordinator 分派同一資料快照')}</p></article>`;
  }).join('');
  return `<section class="execution-block"><div class="subheading"><h3>四個研究 Agent</h3><small>同一資料快照 · ${parallelWorkers} workers</small></div><div class="agent-grid">${cards}</div></section>`;
}
function traceMessage(node='') {
  if(node==='coordinator')return 'Coordinator 鎖定資料快照、分析日與研究協議';
  if(node.startsWith('parallel_research_agents'))return '派發 technical／fundamental／sentiment／macro 四域研究 Agent';
  if(node==='neutral_report_locked')return '四域摘要合併完成，中立研究報告已鎖定';
  if(node.startsWith('parallel_decision_wave'))return `決策波次：${node.slice(node.indexOf('[')+1,-1)}`;
  if(node==='gatekeeper_decisions_locked')return 'Gatekeeper 已核對引用、資料覆蓋與風險門檻';
  if(node==='backtest_and_memory_write')return '回測案例與成熟記憶已持久化';
  return node.replaceAll('_',' ');
}
function runAgentTerminal(job,s) {
  const lines=(s.trace||[]).map(item=>`<div class="terminal-line ok"><time>${escape(terminalStamp(new Date(item.at)))}</time><b>[TRACE]</b><span>${escape(traceMessage(item.node))}</span></div>`).join('');
  const waiting=!['complete','cancelled','paused'].includes(job.status)?'<div class="terminal-line active"><time>NOW</time><b>[WORKER]</b><span>等待下一個持久化檢查點…</span></div>':'';
  return `<section class="execution-block"><div class="subheading"><h3>研究 Agent 終端</h3><small>真實持久化事件 · 執行時每 3 秒、閒置每 30 秒更新；背景分頁暫停更新</small></div><div class="terminal-screen run-terminal"><div class="terminal-line command"><time>CASE</time><b>[SESSION]</b><span>${escape(job.id.slice(0,8))} · ${escape(job.config.protocol.model)} · ${escape(job.config.protocol.version)}</span></div>${lines||'<div class="terminal-line"><time>--:--:--</time><b>[QUEUE]</b><span>等待 Coordinator 領取工作…</span></div>'}${waiting}</div></section>`;
}
function groupPhase(group,count,total) {
  if(count>=total)return '已完成';
  if(group==='A')return '單次決策';
  if(group==='B')return `獨立投票 ${count}/${total}`;
  if(count<2)return '第 1 輪'; if(count<4)return '第 2 輪'; if(count<6)return '第 3 輪'; return '裁決中';
}
function groupProgressPanel(s, protocol, jobStatus) {
  const totals={A:1,B:protocol.voting_samples,C:7,D:7};
  const labels={A:'單次判斷',B:'獨立投票',C:'固定立場',D:'立場交換'};
  const localOllama=String(protocol.model||'').startsWith('ollama/');
  const executionNote=localOllama
    ? '本機 Ollama 決策依序排程，避免模型佇列互相卡住'
    : `${parallelWorkers} workers · 依輪次相依關係並行`;
  const cards=Object.keys(labels).map(group=>{
    const count=(s.records||[]).filter(record=>record.group===group).length, total=totals[group];
    const status=count>=total?'complete':s.report&&jobStatus==='running'?'running':jobStatus==='paused'&&count?'paused':'idle';
    const decision=s.decisions?.[group];
    return `<article class="group-card ${status}"><b>${group} · ${labels[group]}</b><span>${groupPhase(group,count,total)}</span><progress max="${total}" value="${count}" aria-label="${group} 組進度"></progress><small>${count}/${total} 次模型輸出${decision?` · ${escape(decision.action)}`:''}</small></article>`;
  }).join('');
  return `<section class="execution-block"><div class="subheading"><h3>A/B/C/D 實驗執行</h3><small>${escape(executionNote)} · ${escape(missingPolicyLabel(protocol))} · 同輪不互看</small></div><div class="group-grid">${cards}</div></section>`;
}
function backtestComparison(s) {
  if(!s.cases?.length)return '<p class="hint">四組決策鎖定後，系統會自動產生 30／60／90 交易日回測。</p>';
  const rows=s.cases.filter(row=>row.cost_model==='corwin_schultz'&&(row.decision_layer||'gated')==='candidate');
  const cell=(group,horizon)=>{const row=rows.find(item=>item.group===group&&item.horizon===horizon);return !row||row.status==='pending'?'<span class="pending">待成熟</span>':row.status!=='complete'?escape(row.status):percentage(row.net_return);};
  const benchmark=rows.find(row=>row.horizon===60&&row.status==='complete');
  return `<section class="execution-block"><div class="subheading"><h3>四組結果與回測比較</h3><small>Corwin–Schultz 成本後淨報酬</small></div><div class="table-wrap"><table><thead><tr><th>組別</th><th>最終決策</th><th>30 日</th><th>60 日（主要）</th><th>90 日</th></tr></thead><tbody>${'ABCD'.split('').map(group=>`<tr><td><b>${group}</b></td><td>${escape(s.decisions?.[group]?.action||'—')}</td><td>${cell(group,30)}</td><td>${cell(group,60)}</td><td>${cell(group,90)}</td></tr>`).join('')}</tbody></table></div><p class="hint">同期間 60 日 Buy-and-Hold：${benchmark?percentage(benchmark.benchmark_return):'待成熟'}。完整逐日報酬、零成本版本與統計檢定可由 ZIP 下載。</p></section>`;
}
function estimateRemaining(s, total, jobStatus) {
  if(['complete','cancelled'].includes(jobStatus))return null;
  const done=(s.records||[]).length, remaining=total-done;
  if(remaining<=0)return null;
  const elapsed=(s.records||[]).map(r=>r.audit?.usage?.client_elapsed_seconds).filter(v=>typeof v==='number'&&Number.isFinite(v)&&v>0);
  if(elapsed.length<2)return null;
  const avg=elapsed.reduce((a,b)=>a+b,0)/elapsed.length, seconds=avg*remaining;
  if(seconds<60)return '不到 1 分鐘';
  const minutes=Math.round(seconds/60);
  return minutes<60?`約 ${minutes} 分鐘`:`約 ${(minutes/60).toFixed(1)} 小時`;
}
async function showJob(id, loadedJob=null) {
  selectedJob = id;
  syncUrl();
  const job = loadedJob || await api(`/api/jobs/${id}`), s = job.state, total = 15 + job.config.protocol.voting_samples;
  selectedProtocol = job.config.protocol_hash;
  const output = $('run-detail'); output.hidden = false;
  const isFinal = ['complete','cancelled'].includes(job.status);
  const trace = s.trace.at(-1)?.node || '等待 Coordinator';
  const oldProtocol = currentProtocolVersion && job.config.protocol.version !== currentProtocolVersion;
  const protocolNotice = oldProtocol
    ? `這是協議 ${job.config.protocol.version || '未記錄'} 的既有結果；決策規則修正只會套用於 ${currentProtocolVersion} 新建立的實驗。`
    : `${protocolLabel(job.config.protocol)} · 使用目前的 Buy／Hold／Sell 候選決策規則。`;
  const eta=estimateRemaining(s,total,job.status);
  output.innerHTML = `<div class="section-label">CASE / ${escape(id.slice(0,8))}</div><h2>${escape(job.config.ticker)} · ${escape(job.config.analysis_date)} <span class="status ${escape(job.status)}">${escape(statuses[job.status])}</span></h2><p class="${oldProtocol?'protocol-warning':'hint'}">${escape(protocolNotice)}</p><p class="hint">目前：${escape(trace)} · ${s.records.length}/${total} 決策輸出 · ${s.attempts.length} 次持久化波次${eta?` · 依目前平均耗時預估剩餘 ${escape(eta)}`:''}</p><progress class="progress" max="${total}" value="${s.records.length}" aria-label="決策推論進度"></progress>${job.error ? `<p class="error-text">${escape(job.error)}</p>` : ''}<div class="actions">${oldProtocol ? `<button class="quiet" data-clone="${escape(id)}">複製至新版重新執行</button>` : ''}${!isFinal && !oldProtocol ? `<button class="quiet" data-control="${job.wants_run ? 'pause' : 'resume'}">${job.wants_run ? '暫停' : '繼續執行'}</button><button class="quiet" data-control="cancel">取消實驗</button>` : ''}<a href="/api/jobs/${id}/export">下載研究產物 ZIP</a>${job.status === 'complete' ? '<button data-statistics="true">檢視同協議統計</button>' : ''}</div>${runAgentTerminal(job,s)}${researchAgentPanel(s,job.status)}${groupProgressPanel(s,job.config.protocol,job.status)}${s.decisions ? `<div class="decisions">${Object.entries(s.decisions).map(([g,d]) => `<div><small>${g} 組 · 信心 ${percentage(d.confidence)} · 預測 ${number(d.expected_return_pct)}%</small><strong>${escape(d.action)}</strong><small>模型：${escape(d.model_action||d.candidate_action)} · 推導：${escape(d.derived_action||d.candidate_action)} · 候選：${escape(d.candidate_action)}<br>中性帶 ±${number(d.hold_band_pct)}% · 資料覆蓋 ${percentage(d.gate.domain_coverage)}<br>${d.gate.missing_data_control?'缺資料對照：未覆寫模型決策<br>':''}${escape(d.gate.reasons.join(' / ') || '通過門檻')}</small></div>`).join('')}</div>` : '<p class="hint">四組完成後由 Gatekeeper 同步鎖定決策。</p>'}${backtestComparison(s)}<details><summary>中立研究報告與來源</summary><pre>${escape(JSON.stringify(s.report || s.research, null, 2))}</pre></details><details><summary>逐步論證與三輪立場交換（${s.records.length}）</summary>${s.records.map(r => `<article class="trace"><strong>${escape(r.group)} · ${escape(r.key)} · ${escape(r.stance)}</strong><p>${escape(r.output.rationale)}</p><small>引用：${escape(r.output.evidence_ids.join(', '))}<br>提示雜湊：${escape(r.audit.prompt_hash)}</small></article>`).join('')}</details><details><summary>回測、門檻與流程紀錄</summary><pre>${escape(JSON.stringify({decisions:s.decisions,cases:s.cases,compute_usage:s.compute_usage,completeness_diagnostic:s.completeness_diagnostic,trace:s.trace},null,2))}</pre></details>`;
}
async function showStatistics() {
  setTab('stats');
  const [report,pilot,band] = await Promise.all([api(`/api/studies/${selectedProtocol}`),api(`/api/studies/${selectedProtocol}/pilot`),api(`/api/studies/${selectedProtocol}/hold-band`)]), element = $('statistics'); element.hidden = false;
  const primary = report.summary.filter(r => r.horizon === 60 && r.cost_model === 'corwin_schultz' && r.decision_layer === 'candidate' && r.portfolio_basis === 'all');
  const insufficient=report.status==='insufficient_cases'?`<p class="protocol-warning">樣本數 ${report.unique_cases || 0} / ${report.required_cases || 30} 不足，尚未產出任何統計檢定。</p>`:'';
  const prereg=report.preregistration;
  const preregBlock=prereg
    ? `<p class="${prereg.post_freeze_dataset_ids.length?'protocol-warning':'hint'}">Preregistration 已於 ${escape(formatStamp(prereg.frozen_at))} 凍結，涵蓋 ${prereg.dataset_ids.length} 個資料集。${prereg.post_freeze_dataset_ids.length?`⚠️ 凍結後又新增了 ${prereg.post_freeze_dataset_ids.length} 個資料集的實驗，這些案例不應計入凍結後的正式分析結論。`:'目前所有案例都在凍結範圍內。'}</p>`
    : `<p class="hint">尚未凍結 preregistration。凍結後會鎖住目前已分析的資料集清單，之後新增的案例會被標記，避免看完結果後偷偷擴大樣本。</p><button class="quiet" type="button" data-freeze="${escape(selectedProtocol)}">凍結目前的 preregistration</button>`;
  element.innerHTML = `<div class="section-label">PRIMARY ENDPOINT / 60 交易日</div><h2>同協議研究比較</h2><p class="hint">候選決策、60 日、Corwin–Schultz、固定權重投組。${report.unique_cases || 0} 個已完成案例；後續重跑保留供稽核。</p>${insufficient}${preregBlock}<div class="table-wrap"><table><thead><tr><th>方法</th><th>覆蓋率</th><th>條件準確率</th><th>Hold</th><th>Sharpe</th><th>總報酬</th></tr></thead><tbody>${primary.map(r => `<tr><td>${escape(r.group)}</td><td>${percentage(r.coverage)}</td><td>${percentage(r.selective_accuracy)}</td><td>${percentage(r.hold_rate)}</td><td>${number(r.sharpe)}</td><td>${percentage(r.total_return)}</td></tr>`).join('')}</tbody></table></div><p class="hint">Pilot：${escape(pilot.verdict||'—')} · ${escape((pilot.blocking_reasons||[]).join(' / ')||'無阻擋原因')}。中性帶敏感性已用既有預測重算，不重新呼叫模型。</p><div class="actions"><a href="/api/studies/${selectedProtocol}/summary.csv">下載 summary.csv</a><a href="/api/studies/${selectedProtocol}" download="statistics.json">下載 statistics.json</a></div><details><summary>Pilot、hold band 與完整性診斷</summary><pre>${escape(JSON.stringify({pilot,hold_band:band,completeness:report.completeness},null,2))}</pre></details><details><summary>統計檢定與口徑</summary><pre>${escape(JSON.stringify({comparisons:report.comparisons,conventions:report.conventions},null,2))}</pre></details>`;
}
function ensureGpuTwPanel() {
  if($('gputw-state')) return;
  const form=$('settings-form'); if(!form) return;
  const block=document.createElement('div');
  block.className='gputw-block';
  block.innerHTML='<p class="hint">GPUtw 只負責 GPU 執行個體管理；本服務提供唯讀狀態與資源檢查，不會從網頁自動建立、停止或重啟付費執行個體。若使用 GPUtw Ollama 範本，將遠端位址填入設定後即可沿用同一個模型欄位。</p><button id="gputw-check-button" class="quiet" type="button">檢查 GPUtw 狀態</button><p id="gputw-state" class="hint">尚未檢查 GPUtw。</p>';
  form.insertAdjacentElement('afterend',block);
  $('gputw-check-button').addEventListener('click', e=>task(e.currentTarget,async()=>{
    const [state,resources]=await Promise.all([api('/api/gputw/status'),api('/api/gputw/resources')]);
    const statusText=state.status==='ready'?'API 已連線':state.status==='not_configured'?'尚未設定 GPUtw key':(state.message||'狀態查詢失敗');
    const usage=resources.status==='ready'?' · GPU 資源已回傳':resources.status==='needs_instance'?' · 尚未指定執行個體':resources.status==='not_configured'?'':' · 資源查詢失敗';
    $('gputw-state').textContent=`${statusText}${usage}`;
    if(state.status==='ready' && state.instance) notify(`GPUtw 執行個體狀態已取得：${state.instance.status||state.instance.state||'已回傳'}。`);
    else if(state.status==='error') notify(state.message||'GPUtw 查詢失敗',true);
  }));
}
async function initialize() {
  const c = await api('/api/config');
  ensureGpuTwPanel();
  parallelWorkers = c.parallel_workers || 1;
  currentProtocolVersion = c.default_protocol?.version || '';
  const protocolTag = document.querySelector('.tag');
  if (protocolTag && currentProtocolVersion) protocolTag.textContent = `${currentProtocolVersion} 研究協議`;
  finbertReady=Boolean(c.sources?.finbert_local);
  resetAgentTerminal();
  terminalLine('SYSTEM', `Agent Shell ready · protocol ${currentProtocolVersion}`, 'ok');
  terminalLine('COORD', `等待四域資料任務 · worker=${parallelWorkers}`);
  terminalLine('SOURCE', Object.entries(c.sources).filter(([,ready])=>ready).map(([name])=>name.toUpperCase()).join(' · ') || '尚未設定外部來源', Object.values(c.sources).some(Boolean)?'ok':'warn');
  $('login').hidden = true; $('workspace').hidden = false;
  try { $('first-time-guide').hidden = localStorage.getItem('firstTimeGuideDismissed') === '1'; } catch { $('first-time-guide').hidden = false; }
  $('ticker').innerHTML = options(c.tickers); $('ticker').value = 'NVDA';
  const todayIso = new Date().toISOString().slice(0, 10);
  const dateOptions = c.dates.map(v=>`<option value="${escape(v)}">${escape(v)} · 季末研究日</option>`).join('')
    + `<option value="${escape(todayIso)}">${escape(todayIso)} · 今天（當下分析，非正式研究）</option>`;
  $('download-date').innerHTML = dateOptions;
  $('analysis-date').innerHTML = dateOptions;
  $('download-date').value = '2024-12-31'; $('analysis-date').value = '2024-12-31';
  const sourceLabels={sec:'SEC',alfred:'FRED／ALFRED',alpha_vantage:'Alpha Vantage',fnspid:'FNSPID',finbert_local:'本機 FinBERT',gputw:'GPUtw'};
  $('source-state').textContent=Object.entries(c.sources).map(([key,value])=>`${sourceLabels[key]||key}：${value?'已設定':'未設定'}`).join(' · ');
  $('download-finbert').checked=finbertReady;
  const cloudLabels={openrouter:'OpenRouter',openai:'OpenAI',gemini:'Gemini'};
  const readyCloud=Object.entries(c.cloud_models||{}).filter(([,value])=>value).map(([key])=>cloudLabels[key]||key);
  $('cloud-model-state').textContent=readyCloud.length?`可用雲端憑證：${readyCloud.join('、')}。輸入 LiteLLM 模型名稱即可切換。`:'尚未設定常用雲端模型金鑰；可先使用 Ollama，或在上方設定表單填入金鑰。';
  if($('gputw-state')) $('gputw-state').textContent=c.gputw?.configured
    ? `GPUtw key 已設定${c.gputw.instance_configured?' · 已指定執行個體':''}${c.gputw.ollama_configured?' · 遠端 Ollama 已設定':''}；按「檢查 GPUtw 狀態」測試連線。`
    : 'GPUtw 尚未設定；可留白使用本機 Ollama。';
  const urlParams = new URLSearchParams(location.search);
  const requestedTab = urlParams.get('tab');
  selectedJob = urlParams.get('selected') || null;
  setTab(requestedTab || (selectedJob ? 'runs' : 'setup'), { skipUrl: true });
  setFlow('data');
  // These reads are independent. Loading them together prevents a slow
  // readiness scan or Ollama probe from blocking the rest of the workspace.
  const initialResults = await Promise.allSettled([
    refreshSettings(),
    refreshDatasets(),
    refreshReadiness(),
    refreshJobs(),
    api('/api/models'),
  ]);
  const initialLabels = ['設定', '資料集', '資料完整度', '實驗佇列', '模型'];
  const initialFailures = initialResults
    .map((result, index) => result.status === 'rejected' ? `${initialLabels[index]}：${result.reason?.message || '讀取失敗'}` : '')
    .filter(Boolean);
  if (initialFailures.length) notify(`部分頁面資料暫時無法載入；可稍後按重新整理重試。${initialFailures.join('、')}`, true);
  api('/api/sources/alpha-vantage-archive').then(state=>{if(state.stage==='running')pollAlphaVantageArchive();}).catch(()=>{});
  const modelResult = initialResults[4];
  const m = modelResult.status === 'fulfilled'
    ? modelResult.value
    : {ready:false, models:[], details:[], message:'Ollama 暫時無法連線；可稍後重試或改用雲端模型。'};
  modelDetails=new Map((m.details||[]).map(item=>[item.id,item]));
  installedModels=new Set(m.models||[]);
  const formal=(m.details||[]).filter(item=>Number.parseFloat(item.parameter_size)>=14);
  $('model-state').textContent = m.ready ? (formal.length
    ? `Ollama 已連線 · ${m.models.length} 個本機模型 · ${formal.length} 個符合 14B 研究門檻`
    : `Ollama 已連線 · ${m.models.length} 個本機模型；尚未偵測到 14B 以上模型，14B 以下僅可作冒煙測試`) : m.message;
  const models=[...new Set([c.model,...m.models])]; $('model').innerHTML=modelOptions(models,m.details);
  const largest=[...(m.details||[])].sort((a,b)=>(Number.parseFloat(b.parameter_size)||0)-(Number.parseFloat(a.parameter_size)||0))[0]?.id;
  $('model').value=installedModels.has(c.model)?c.model:(formal[0]?.id||largest||c.model);
  if(!m.default_available&&largest) $('model-state').textContent+=`；設定的預設模型 ${c.model} 尚未安裝，畫面已先選 ${$('model').value}`;
  syncExperimentGuard();
  if (!requestedTab) {
    const selected = allJobs.find(job => job.id === selectedJob);
    const active = allJobs.some(job => ['queued','running','paused'].includes(job.status));
    if (selected?.status === 'complete') setTab('stats');
    else if (active) setTab('runs');
    else if (datasetRows.length) { setTab('setup'); setFlow('experiment'); }
    else { setTab('setup'); setFlow('data'); }
  }
  schedulePoll();
}
$('login-form').addEventListener('submit', e => { e.preventDefault(); task(e.submitter, async()=>{await api('/api/login',{key:$('access-key').value}); $('access-key').value=''; await initialize();}); });
$('download-form').addEventListener('submit', e => { e.preventDefault(); task(e.submitter, async()=>{const ticker=$('ticker').value,analysisDate=$('download-date').value,refresh=$('refresh-data').checked,useFinbert=$('download-finbert').checked;resetAgentTerminal();terminalLine('YOU',`collect --ticker ${ticker} --as-of ${analysisDate} --domains all${refresh?' --refresh':''}${useFinbert?' --finbert':''}`,'command');terminalLine('COORD',refresh?`強制建立 ${analysisDate} 新快照，派發 4 個資料 Agent`:`先搜尋 ${ticker}／${analysisDate} 可重用的四域完整快照`);notify('資料 Agent 正在檢查快照與來源…');renderCollectionAgents(null,'running');let r;try{r=await api('/api/datasets/download',{ticker,analysis_date:analysisDate,refresh,use_finbert:useFinbert});}catch(error){terminalLine('ERROR',error.message,'error');renderCollectionAgents(datasetRows.find(d=>d.id===$('dataset').value)||null);throw error;}if(r.reused){terminalLine('CACHE',`HIT dataset v${r.version} · ${r.id.slice(0,12)}… · 未呼叫外部 API`,'ok');}else{terminalLine('COORD','已完成四域來源派工：Yahoo／SEC／Alpha+FNSPID／ALFRED');}const codes={technical:'TECH',fundamental:'FUND',sentiment:'SENT',macro:'MACRO'};for(const [domain,item] of Object.entries(r.agents))terminalLine(codes[domain],`${item.status.toUpperCase()} · ${item.records} records · ${item.message}`,item.status==='complete'?'ok':'warn');for(const limitation of r.limitations)terminalLine('AUDIT',limitation,'warn');if(!r.reused)terminalLine('STORE',`SAVED dataset ${r.id.slice(0,12)}… · immutable snapshot`,'ok');await refreshDatasets();await refreshReadiness();$('dataset').value=r.id;$('analysis-date').value=r.analysis_date;renderDatasetDetail();renderCollectionAgents(datasetRows.find(d=>d.id===r.id));setFlow('experiment');notify(r.reused?'已重用符合條件的既有資料快照；未重新呼叫來源 API。':'資料 Agent 已完成本輪工作，資料集已保存。\n'+r.limitations.join('\n'));}); });
$('source-check-button').addEventListener('click', e => task(e.currentTarget,async()=>{const result=await api('/api/sources/check',{ticker:$('ticker').value,analysis_date:$('download-date').value});const label={alpha_vantage:'Alpha Vantage',alpha_vantage_cache:'Alpha Vantage 快取',fnspid:'FNSPID'};notify(Object.entries(result).map(([key,value])=>`${label[key]||key}：${value.message}（${value.records} 筆）`).join('\n'));}));
async function pollAlphaVantageArchive(){
  while(true){
    const state=await api('/api/sources/alpha-vantage-archive');
    $('av-archive-progress').textContent=state.stage==='idle'?'':`${state.completed??0}/${state.total??'?'} · ${state.current?state.current+' · ':''}${state.message||state.stage}`;
    if(!['running'].includes(state.stage))return state;
    await new Promise(resolve=>setTimeout(resolve,2000));
  }
}
$('av-archive-button').addEventListener('click', e=>task(e.currentTarget,async()=>{
  await api('/api/sources/alpha-vantage-archive/start',{});
  const state=await pollAlphaVantageArchive();
  if(state.stage==='complete')notify(`Alpha Vantage 新聞快取已更新，本輪新增 ${state.added_rows??0} 筆。`);
  else if(state.stage==='rate_limited')notify(`今日額度已用完；${state.message||''}`,true);
  else if(state.stage==='failed')notify(state.message||'更新失敗',true);
}));
$('import-file').addEventListener('change', e => task(null,async()=>{const f=e.target.files[0];if(!f)return;const useFinbert=$('use-finbert').checked;const r=await api(`/api/datasets/import?use_finbert=${useFinbert}`,JSON.parse(await f.text()));await refreshDatasets();await refreshReadiness();$('dataset').value=r.id;renderDatasetDetail();renderCollectionAgents(datasetRows.find(d=>d.id===r.id));notify(r.finbert_applied?'資料集已驗證，新聞標題已由 FinBERT 分類並保存。':'資料集已驗證並保存。');}));
async function scoreSelectedDataset(id) {
  scoring=true;renderDatasetDetail();
  try {
    await api(`/api/datasets/${encodeURIComponent(id)}/finbert/start`,{});
    while(true){
      const state=await api(`/api/datasets/${encodeURIComponent(id)}/finbert`);
      $('finbert-progress').textContent=`${state.completed||0}/${state.total||'?'} 則 · ${state.message||state.stage}`;
      if(state.stage==='complete' && state.result){await refreshDatasets();await refreshReadiness();$('dataset').value=state.result.id;renderDatasetDetail(true);notify(`FinBERT 已建立新版本，${state.result.items} 則標題全部完成。`);break;}
      if(['failed','idle'].includes(state.stage))throw new Error(state.message||'FinBERT 未完成；可重試');
      await new Promise(resolve=>setTimeout(resolve,1500));
    }
  } finally {scoring=false;renderDatasetDetail();}
}
$('score-finbert-button').addEventListener('click',e=>task(e.currentTarget,()=>scoreSelectedDataset($('dataset').value)));
$('news-view').addEventListener('click',e=>task(e.currentTarget,async()=>{
  const id=$('dataset').value;if(!id)throw new Error('請先選擇資料集');
  const dataset=await api(`/api/datasets/${encodeURIComponent(id)}`);
  $('news-scores').innerHTML=dataset.evidence.filter(row=>row.domain==='sentiment').map(row=>`<article><b>${escape(row.headline||row.claim)}</b><p>${escape(row.available_at)} · ${escape(row.sentiment_label||'尚未評分')} · 分數 ${number(row.sentiment_score)}</p>${row.sentiment_scores?`<small>正向 ${percentage(row.sentiment_scores.positive)} · 中性 ${percentage(row.sentiment_scores.neutral)} · 負向 ${percentage(row.sentiment_scores.negative)}</small>`:''}<p class="hint">${escape(row.sentiment_method||row.source_type||'原始證據')} · ${escape(row.source)}</p></article>`).join('')||'此版本沒有新聞證據';
}));
async function refreshSettings(){
  const settings=await api('/api/settings');
  const groups=[
    {title:'回測資料來源',names:['SEC_USER_AGENT','FRED_API_KEY','ALPHA_VANTAGE_API_KEY']},
    {title:'回測模型',names:['DEFAULT_MODEL']},
    {title:'GPUtw／遠端 Ollama',names:['GPUTW_API_URL','GPUTW_API_KEY','GPUTW_INSTANCE_ID','GPUTW_OLLAMA_BASE_URL','GPUTW_OLLAMA_API_KEY']},
    {title:'本機研究資料路徑',names:['FNSPID_NEWS_PATH','ALPHA_VANTAGE_NEWS_PATH']},
    {title:'雲端模型金鑰（進階）',names:['OPENROUTER_API_KEY','OPENAI_API_KEY','GEMINI_API_KEY'],collapsed:true},
  ];
  const renderField=field=>`<div class="setting-item"><label>${escape(field.label)} · <span class="setting-state">${field.configured?'已設定':'未設定'}</span><input data-setting="${escape(field.name)}" type="${field.secret?'password':'text'}" autocomplete="off" value="${escape(field.display_value||'')}" placeholder="留白保留原值"></label><label class="check"><input type="checkbox" data-clear-setting="${escape(field.name)}">清除此設定</label></div>`;
  const grouped=groups.map(group=>{const fields=settings.fields.filter(field=>group.names.includes(field.name));if(!fields.length)return '';return group.collapsed?`<details class="settings-group settings-advanced"><summary>${group.title}</summary><div class="settings-grid">${fields.map(renderField).join('')}</div></details>`:`<section class="settings-group"><h3>${group.title}</h3><div class="settings-grid">${fields.map(renderField).join('')}</div></section>`;}).join('');
  const known=new Set(groups.flatMap(group=>group.names));
  const other=settings.fields.filter(field=>!known.has(field.name));
  $('settings-fields').innerHTML=grouped+(other.length?`<section class="settings-group"><h3>其他設定</h3><div class="settings-grid">${other.map(renderField).join('')}</div></section>`:'');
}
$('settings-form').addEventListener('submit',e=>{e.preventDefault();task(e.submitter,async()=>{
  const values={};document.querySelectorAll('[data-setting]').forEach(input=>{if(input.value.trim())values[input.dataset.setting]=input.value.trim();});
  const clear=[...document.querySelectorAll('[data-clear-setting]:checked')].map(input=>input.dataset.clearSetting);
  await api('/api/settings',{values,clear});await refreshSettings();notify('設定已儲存在伺服器並立即生效。');
  const c=await api('/api/config');
  const remote=$('gputw-state');if(remote)remote.textContent=c.gputw?.configured?`GPUtw key 已設定${c.gputw.instance_configured?' · 已指定執行個體':''}${c.gputw.ollama_configured?' · 遠端 Ollama 已設定':''}；按「檢查 GPUtw 狀態」測試連線。`:'GPUtw 尚未設定；可留白使用本機 Ollama。';
});});
$('batch-file').addEventListener('change', e => task(null,async()=>{
  const f=e.target.files[0];if(!f)return;
  const payload=JSON.parse(await f.text());
  const cases=Array.isArray(payload.cases)?payload.cases:[];
  const dates=[...new Set(cases.map(c=>c.analysis_date))].filter(Boolean).sort();
  const datasets=new Set(cases.map(c=>c.dataset_id));
  const models=[...new Set(cases.map(c=>c.model).filter(Boolean))];
  const summary=`即將建立 ${cases.length} 筆研究案例\n分析日：${dates.join('、')||'（未指定）'}\n涉及資料集：${datasets.size} 種\n模型：${models.join('、')||'使用各筆預設值'}\n\n確定要送出並排入佇列嗎？`;
  if(!cases.length || !window.confirm(summary)){e.target.value='';return;}
  const ids=await api('/api/batches',payload);
  notify(`已加入 ${ids.length} 個研究案例。`);
  await refreshJobs();
  e.target.value='';
}));
$('job-form').addEventListener('submit', e => {e.preventDefault();if(submitting)return;if(!$('dataset').value){notify('請先選擇一筆資料集，才能開始研究實驗。',true);syncExperimentGuard();return;}submitting=true;task(e.submitter,async()=>{try{const model=$('cloud-model').value.trim()||$('model').value;const j=await api('/api/jobs',{dataset_id:$('dataset').value,analysis_date:$('analysis-date').value,model,study:$('study').value,voting_samples:Number($('voting').value),missing_data_policy:$('missing-policy').value,anonymize_ticker:$('anonymize').checked,allow_point_fundamental:$('allow-point-fundamental').checked,allow_small_model:$('allow-small-model').checked,allow_low_quality_sentiment:$('allow-low-quality-sentiment').checked});selectedJob=j.id;notify(`研究已加入背景佇列，模型為 ${model}。候選決策、風控決策與品質覆寫會一起鎖定於協議。`);setTab('runs');await refreshJobs();}finally{submitting=false;}});});
document.addEventListener('click', e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.tabButton){setTab(b.dataset.tabButton);return;}if(b.dataset.flowTab){setFlow(b.dataset.flowTab);return;}if(b.dataset.nextTab){setTab(b.dataset.nextTab);return;}if(b.dataset.nextFlow){setFlow(b.dataset.nextFlow);return;}if(b.dataset.dismissNotice){dismissNotice(Number(b.dataset.dismissNotice));return;}if(b.dataset.open)task(b,()=>showJob(b.dataset.open));if(b.dataset.control)task(b,async()=>{if(b.dataset.control==='cancel'&&!window.confirm('取消此實驗？已完成紀錄會保留，取消後無法續跑。'))return;await api(`/api/jobs/${selectedJob}/${b.dataset.control}`,{});await refreshJobs();});if(b.dataset.clone)task(b,async()=>{const j=await api(`/api/jobs/${b.dataset.clone}/clone`,{});selectedJob=j.id;await refreshJobs();});if(b.dataset.statistics)task(b,showStatistics);if(b.dataset.freeze)task(b,async()=>{if(!window.confirm('凍結此協議目前分析的資料集清單？凍結後不可撤銷，之後新增的案例會被標記為凍結後追加。'))return;await api(`/api/studies/${b.dataset.freeze}/freeze`,{});await showStatistics();});});
$('refresh').addEventListener('click', e=>task(e.currentTarget,async()=>{await refreshDatasets();await refreshReadiness();await refreshJobs();}));
document.addEventListener('visibilitychange',()=>{
  if(document.hidden){if(pollTimer)clearTimeout(pollTimer);pollTimer=null;return;}
  task(null,refreshJobs);
});
$('dataset').addEventListener('change', ()=>{renderDatasetDetail(true);renderCollectionAgents(datasetRows.find(d=>d.id===$('dataset').value)||null);syncExperimentGuard();});
$('analysis-date').addEventListener('change',syncExperimentGuard);
$('allow-low-quality-sentiment').addEventListener('change',syncExperimentGuard);
$('allow-point-fundamental').addEventListener('change',syncExperimentGuard);
$('model').addEventListener('change',syncExperimentGuard);
$('cloud-model').addEventListener('input',syncExperimentGuard);
$('allow-small-model').addEventListener('change',syncExperimentGuard);
$('job-search').addEventListener('input',renderJobList);
$('job-status-filter').addEventListener('change',renderJobList);
$('dataset-search').addEventListener('input',renderDatasetPreviewList);
$('dataset-picker-search').addEventListener('input',()=>renderDatasetOptions());
$('dismiss-first-time-guide').addEventListener('click',()=>{$('first-time-guide').hidden=true;try{localStorage.setItem('firstTimeGuideDismissed','1');}catch{}});
task(null,initialize);

