// Ticker x analysis-date checkbox grid shared by batch data collection and
// batch experiments. Defaults to the whole study (9 tickers x 20 quarter-ends).
import { escape } from './ui.js';

export function mountCasePicker(root, config, {name}) {
  const tickers = config.tickers || [], dates = config.dates || [];
  const years = [...new Set(dates.map(d => d.slice(0, 4)))];
  root.innerHTML = `
    <fieldset class="picker"><legend>股票 <small data-count="tickers"></small></legend>
      <div class="picker-actions"><button type="button" class="chip-action" data-all="tickers">全選</button><button type="button" class="chip-action" data-none="tickers">清除</button></div>
      <div class="chips">${tickers.map(t => `<label class="chip"><input type="checkbox" name="${name}-ticker" value="${escape(t)}" checked>${escape(t)}</label>`).join('')}</div>
    </fieldset>
    <fieldset class="picker"><legend>分析日 <small data-count="dates"></small></legend>
      <div class="picker-actions"><button type="button" class="chip-action" data-all="dates">全選</button><button type="button" class="chip-action" data-none="dates">清除</button>${years.map(y => `<button type="button" class="chip-action" data-year="${y}">只選 ${y}</button>`).join('')}</div>
      <div class="chips">${dates.map(d => `<label class="chip"><input type="checkbox" name="${name}-date" value="${escape(d)}" checked>${escape(d)}</label>`).join('')}</div>
    </fieldset>
    <p class="hint picker-total" data-count="total"></p>`;
  const boxes = kind => [...root.querySelectorAll(`input[name="${name}-${kind === 'tickers' ? 'ticker' : 'date'}"]`)];
  const selected = kind => boxes(kind).filter(b => b.checked).map(b => b.value);
  const update = () => {
    const t = selected('tickers').length, d = selected('dates').length;
    root.querySelector('[data-count="tickers"]').textContent = `${t}/${tickers.length}`;
    root.querySelector('[data-count="dates"]').textContent = `${d}/${dates.length}`;
    root.querySelector('[data-count="total"]').textContent = `共 ${t} × ${d} ＝ ${t * d} 個案例`;
    root.dispatchEvent(new CustomEvent('picker:change', {bubbles: true}));
  };
  root.addEventListener('change', update);
  root.addEventListener('click', e => {
    const b = e.target.closest('.chip-action');
    if (!b) return;
    if (b.dataset.all) boxes(b.dataset.all).forEach(x => { x.checked = true; });
    if (b.dataset.none) boxes(b.dataset.none).forEach(x => { x.checked = false; });
    if (b.dataset.year) boxes('dates').forEach(x => { x.checked = x.value.startsWith(b.dataset.year); });
    update();
  });
  update();
  return {tickers: () => selected('tickers'), dates: () => selected('dates')};
}
