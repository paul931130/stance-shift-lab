// A local narrated simulation. It never changes research state or submits jobs.
import { $ } from './ui.js';

const DOMAINS = ['technical', 'fundamental', 'sentiment', 'macro'];
const STEPS = [
  {act: 0, title: '選定案例與分析日', nodes: DOMAINS.map(d => `src-${d}`),
    description: '以 NVDA 的合成案例為例，先指定分析日。行情、財報、新聞與總經資料，都只能使用當時已公開的資訊。',
    output: '示意輸入：NVDA · 2024-12-31；所有內容均為固定示範。'},
  {act: 0, title: '四類資料代理人整理證據', nodes: DOMAINS.map(d => `da-${d}`),
    description: '分別整理技術、基本面、情緒與總經證據，保留來源、發布時間與證據編號，先檢查資料缺口。',
    output: '示意證據：技術趨勢偏正向、營收 110／前期 100、新聞情緒 +0.2、總經中性。'},
  {act: 0, title: '鎖定不可變資料快照', nodes: ['snapshot'],
    description: '通過資料檢查後，以內容雜湊識別快照。後續四組決策讀取同一份資料，避免各組資訊不一致。',
    output: '示意輸出：一份已鎖定的四域資料快照；此播放器不寫入資料庫。'},
  {act: 1, title: '研究代理人解讀四域證據', nodes: DOMAINS.map(d => `ra-${d}`),
    description: '研究代理人依證據編號提出摘要、風險與資訊缺口，讓後續決策能追溯每個論點的依據。',
    output: '示意摘要：趨勢與營收支持看多，但合成資料無法代表真實市場風險。'},
  {act: 1, title: '建立並鎖定中立研究報告', nodes: ['report'],
    description: '合併四域研究內容，在決策分流前鎖定中立報告，讓各組比較建立在相同研究輸入上。',
    output: '示意輸出：共同報告＋引用證據＋風險清單，尚未作投資決策。'},
  {act: 1, title: '四組決策機制各自判斷', nodes: ['g-A', 'g-B', 'g-C', 'g-D'],
    description: 'A 單次判斷、B 七次獨立投票；C 固定立場辯論，D 在辯論中交換立場。C／D 各有六次辯論發言與一次裁決。此處展示 RQ1 的基礎流程。',
    output: '示意輸出：各組產生 Buy／Hold／Sell 候選決策、信心與引用；實際差異須經實驗檢驗。'},
  {act: 2, title: '守門員檢查決策', nodes: ['gate'],
    description: '檢查引用是否有效、證據是否足夠及風險限制。候選決策通過檢核後，才交由回測；被擋下時會保留原因。',
    output: '示意檢核：證據編號存在、分析日前可得；缺證據的候選決策不能直接採用。'},
  {act: 2, title: '同期間回測並扣除成本', nodes: ['backtest'],
    description: '依守門員處理後的決策，在相同持有期間計算報酬、交易成本與風險，再和同案同期間的基準比較。',
    output: '示意輸出：60 個交易日的成本後報酬序列；播放器不計算或宣稱真實績效。'},
  {act: 2, title: '彙整統計與研究限制', nodes: ['stats'],
    description: '完整研究會以配對案例比較方向準確率與 Sharpe，處理時間相依性及多重檢定。單一示範案例無法證明某組較好，未顯著也不代表等效。',
    output: '示範完成：已走完資料 → 研究與決策 → 檢核與結果。可展開下方紀錄回看每一步。'},
];

let initialized = false;
export function initDemoPlayer() {
  if (initialized) return;
  initialized = true;
  let index = 0, playing = false, timer = null;
  const panel = $('demo-player');
  const clearTimer = () => { clearTimeout(timer); timer = null; };
  function highlight() {
    const active = new Set(panel.hidden ? [] : STEPS[index].nodes);
    document.querySelectorAll('[data-flow-node]').forEach(node => {
      node.toggleAttribute('data-demo-active', active.has(node.dataset.flowNode));
    });
  }
  // Live polling can rebuild the map when the selected research design changes.
  new MutationObserver(highlight).observe($('flow-canvas'), {childList: true, subtree: true});
  function schedule() {
    clearTimer();
    if (!playing) return;
    timer = setTimeout(() => {
      if (index < STEPS.length - 1) { index += 1; render(); schedule(); }
      else {
        playing = false;
        $('demo-pause').disabled = true;
        $('demo-step-count').textContent = '播放完成 · 9 / 9 步';
        clearTimer();
      }
    }, 6000 / Number($('demo-speed').value));
  }
  function render() {
    const step = STEPS[index];
    $('demo-step-count').textContent = `第 ${step.act + 1} 幕 · ${index + 1} / ${STEPS.length} 步`;
    $('demo-step-title').textContent = step.title;
    $('demo-step-description').textContent = step.description;
    $('demo-step-output').textContent = step.output;
    $('demo-progress').value = index + 1;
    [...$('demo-acts').children].forEach((item, act) => {
      if (act === step.act) item.setAttribute('aria-current', 'step');
      else item.removeAttribute('aria-current');
    });
    $('demo-history').replaceChildren(...STEPS.slice(0, index + 1).map(item => {
      const li = document.createElement('li');
      const title = document.createElement('strong'); title.textContent = item.title;
      const description = document.createElement('p'); description.textContent = item.description;
      const output = document.createElement('p'); output.textContent = item.output;
      li.append(title, description, output); return li;
    }));
    highlight();
  }
  function start() {
    clearTimer(); index = 0; playing = true; panel.hidden = false;
    $('demo-pause').disabled = false;
    $('demo-pause').textContent = '暫停';
    render(); schedule();
    panel.scrollIntoView({behavior: 'instant', block: 'nearest'});
  }
  $('play-demo').disabled = false;
  $('play-demo').addEventListener('click', start);
  $('demo-restart').addEventListener('click', start);
  $('demo-pause').addEventListener('click', () => {
    playing = !playing;
    $('demo-pause').textContent = playing ? '暫停' : '繼續播放';
    schedule();
  });
  $('demo-speed').addEventListener('change', schedule);
  $('demo-close').addEventListener('click', () => {
    playing = false; clearTimer(); panel.hidden = true; highlight(); $('play-demo').focus();
  });
}
