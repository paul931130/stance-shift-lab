const test = require('node:test');
const assert = require('node:assert/strict');
const { computeExperimentReadiness } = require('../static/readiness-rules.js');

const readyHistoricalDataset = {
  kind: 'historical',
  requested_analysis_date: '2024-12-31',
  coverage: {
    sentiment_quality: { items: 10, passes_quality_gate: true, finbert_complete: true },
    fundamental_quality: { items: 4, passes_quality_gate: true },
  },
};

const baseInput = {
  dataset: readyHistoricalDataset,
  analysisDate: '2024-12-31',
  allowLowQualitySentiment: false,
  allowPointFundamental: false,
  allowSmallModel: false,
  cloudModel: '',
  localModel: 'ollama/qwen3:14b',
  localAvailable: true,
  localParameterSize: '14.8B',
};

test('no dataset selected blocks the run', () => {
  const result = computeExperimentReadiness({ ...baseInput, dataset: null });
  assert.equal(result.ready, false);
  assert.equal(result.reason, 'no_dataset');
});

test('analysis date must match the historical dataset cut', () => {
  const result = computeExperimentReadiness({ ...baseInput, analysisDate: '2024-09-30' });
  assert.equal(result.ready, false);
  assert.equal(result.reason, 'date_mismatch');
});

test('synthetic datasets are exempt from the date-match rule', () => {
  const result = computeExperimentReadiness({
    ...baseInput, analysisDate: 'anything',
    dataset: { ...readyHistoricalDataset, kind: 'synthetic' },
  });
  assert.equal(result.ready, true);
});

test('low-quality sentiment blocks unless explicitly overridden', () => {
  const dataset = { ...readyHistoricalDataset, coverage: { ...readyHistoricalDataset.coverage,
    sentiment_quality: { items: 10, passes_quality_gate: false, finbert_complete: true } } };
  const blocked = computeExperimentReadiness({ ...baseInput, dataset });
  assert.equal(blocked.ready, false);
  assert.equal(blocked.reason, 'sentiment_quality');
  const overridden = computeExperimentReadiness({ ...baseInput, dataset, allowLowQualitySentiment: true });
  assert.equal(overridden.ready, true);
});

test('missing sentiment domain is not blocked by the quality gate', () => {
  const dataset = { ...readyHistoricalDataset,
    coverage: { ...readyHistoricalDataset.coverage, sentiment_quality: { items: 0, passes_quality_gate: false, finbert_complete: false } } };
  const result = computeExperimentReadiness({ ...baseInput, dataset });
  assert.equal(result.ready, true);
});

test('point-only fundamental evidence blocks unless explicitly overridden', () => {
  const dataset = { ...readyHistoricalDataset, coverage: { ...readyHistoricalDataset.coverage,
    fundamental_quality: { items: 4, passes_quality_gate: false } } };
  const blocked = computeExperimentReadiness({ ...baseInput, dataset });
  assert.equal(blocked.ready, false);
  assert.equal(blocked.reason, 'fundamental_quality');
  const overridden = computeExperimentReadiness({ ...baseInput, dataset, allowPointFundamental: true });
  assert.equal(overridden.ready, true);
});

test('an uninstalled local model blocks the run', () => {
  const result = computeExperimentReadiness({ ...baseInput, localAvailable: false });
  assert.equal(result.ready, false);
  assert.equal(result.reason, 'model_not_installed');
});

test('a sub-14B local model blocks unless the smoke-test box is checked', () => {
  const blocked = computeExperimentReadiness({ ...baseInput, localParameterSize: '8B' });
  assert.equal(blocked.ready, false);
  assert.equal(blocked.reason, 'model_too_small');
  const overridden = computeExperimentReadiness({ ...baseInput, localParameterSize: '8B', allowSmallModel: true });
  assert.equal(overridden.ready, true);
});

test('a cloud model bypasses local install and size checks entirely', () => {
  const result = computeExperimentReadiness({
    ...baseInput, cloudModel: 'openrouter/openai/gpt-4.1-mini',
    localAvailable: false, localParameterSize: '1B',
  });
  assert.equal(result.ready, true);
});

test('everything satisfied yields ready', () => {
  const result = computeExperimentReadiness(baseInput);
  assert.equal(result.ready, true);
  assert.equal(result.reason, 'ready');
});
