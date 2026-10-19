// Single shared state object plus a tiny event bus, so step modules can react
// to each other ("a dataset was selected") without importing one another.
export const state = {
  selectedJob: null,
  selectedProtocol: null,
  busy: false,
  datasetRows: [],
  allJobs: [],
  parallelWorkers: 1,
  currentProtocolVersion: '',
  demoMode: false,
  currentTab: 'data',
  autoStatsJob: null,
  submitting: false,
  scoring: false,
  hasActiveJobs: false,
  finbertReady: false,
};

const listeners = new Map();
export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
  return () => listeners.get(event).delete(fn);
}
export function emit(event, payload) {
  for (const fn of listeners.get(event) || []) {
    try { fn(payload); } catch (error) { console.error(`[${event}]`, error); }
  }
}

export const selectedDataset = () => state.datasetRows.find(row => row.id === document.getElementById('dataset')?.value) || null;
