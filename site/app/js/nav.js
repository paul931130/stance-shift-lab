// Step navigation: one inspector panel at a time, mirrored on the flow map
// and in the URL (?tab=…&selected=…) so a refresh restores the same view.
import { state, emit } from './store.js';
import { flow } from './flow.js';

export const TABS = ['data', 'experiment', 'runs', 'stats'];

export function syncUrl() {
  const params = new URLSearchParams();
  if (state.currentTab) params.set('tab', state.currentTab);
  if (state.selectedJob) params.set('selected', state.selectedJob);
  const query = params.toString();
  const url = location.pathname + (query ? `?${query}` : '');
  if (location.pathname + location.search !== url) history.replaceState(null, '', url);
}

export function setTab(tab, opts = {}) {
  if (!TABS.includes(tab)) tab = 'data';
  const changed = state.currentTab !== tab;
  state.currentTab = tab;
  for (const panel of document.querySelectorAll('[data-panel]')) {
    const active = panel.dataset.panel === tab;
    if (active && panel.hidden) {
      panel.hidden = false;
      panel.classList.remove('panel-enter'); void panel.offsetWidth; panel.classList.add('panel-enter');
    } else if (!active) panel.hidden = true;
  }
  const index = TABS.indexOf(tab);
  for (const btn of document.querySelectorAll('.tabs [data-tab-button]')) {
    const own = TABS.indexOf(btn.dataset.tabButton);
    btn.classList.toggle('active', own === index);
    btn.classList.toggle('passed', own < index);
    btn.setAttribute('aria-selected', own === index ? 'true' : 'false');
    btn.tabIndex = own === index ? 0 : -1;
  }
  flow.focus(tab);
  // On narrow screens the inspector sits below the map; bring it into view
  // when the user navigates from the map or a "next step" action.
  if (opts.reveal) document.getElementById('inspector')?.scrollIntoView({behavior: 'smooth', block: 'start'});
  if (!opts.skipUrl) syncUrl();
  if (changed || opts.force) emit('tab:changed', tab);
}

document.addEventListener('click', e => {
  const button = e.target.closest('[data-tab-button], [data-goto]');
  if (button) setTab(button.dataset.tabButton || button.dataset.goto);
});
// Arrow / Home / End keys move between steps, as expected for a tablist.
document.addEventListener('keydown', e => {
  const button = e.target.closest?.('[data-tab-button]');
  if (!button || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
  e.preventDefault();
  const here = TABS.indexOf(button.dataset.tabButton);
  const next = e.key === 'Home' ? TABS[0] : e.key === 'End' ? TABS.at(-1)
    : TABS[(here + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length];
  setTab(next);
  document.querySelector(`[data-tab-button="${next}"]`)?.focus();
});
flow.onNavigate(tab => setTab(tab, {reveal: window.matchMedia('(max-width: 1080px)').matches}));
