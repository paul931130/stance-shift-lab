/* Pure decision logic for "can this dataset/model combination start an
 * experiment", extracted out of app.js so it can be unit tested without a
 * DOM. No document/window references belong in this file. */
function computeExperimentReadiness(input) {
  const { dataset, analysisDate, allowLowQualitySentiment, allowPointFundamental,
    allowSmallModel, cloudModel, localModel, localAvailable, localParameterSize } = input;
  if (!dataset) return { ready: false, reason: 'no_dataset' };
  const cut = dataset.requested_analysis_date || (dataset.used_analysis_dates || []).slice(-1)[0] || null;
  const dateReady = dataset.kind !== 'historical' || cut === analysisDate;
  if (!dateReady) return { ready: false, reason: 'date_mismatch' };
  const quality = dataset.coverage?.sentiment_quality;
  const fundamental = dataset.coverage?.fundamental_quality;
  const hasNews = Boolean(quality?.items);
  const qualityReady = !hasNews || (quality.passes_quality_gate && quality.finbert_complete);
  const qualityAllowed = qualityReady || allowLowQualitySentiment || dataset.kind !== 'historical';
  if (!qualityAllowed) return { ready: false, reason: 'sentiment_quality', quality };
  const fundamentalReady = !fundamental?.items || fundamental.passes_quality_gate;
  const fundamentalAllowed = fundamentalReady || allowPointFundamental || dataset.kind !== 'historical';
  if (!fundamentalAllowed) return { ready: false, reason: 'fundamental_quality', fundamental };
  const trimmedCloud = (cloudModel || '').trim();
  if (!trimmedCloud) {
    if (!localAvailable) return { ready: false, reason: 'model_not_installed', localModel };
    const size = Number.parseFloat(localParameterSize);
    if (!(size >= 14) && !allowSmallModel) {
      return { ready: false, reason: 'model_too_small', localModel, localParameterSize };
    }
  }
  return { ready: true, reason: 'ready' };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { computeExperimentReadiness };
}
