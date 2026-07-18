// @ts-expect-error Node's native type-strip runner requires explicit .ts specifiers.
import { normalizeExperimentSelection, type SupportedTicker, type QuarterlyAnalysisDate } from "./catalog.ts";
// @ts-expect-error Node's native type-strip runner requires explicit .ts specifiers.
import { clamp, stableHash, stableNumber } from "./deterministic.ts";
import type {
  EvidenceDirection,
  EvidenceItem,
  ResearchDomain,
  ResearchSignal,
  ResearchSnapshot,
} from "./types.ts";

interface SignalDefinition {
  key: string;
  label: string;
  minimum: number;
  maximum: number;
  unit: ResearchSignal["unit"];
  positiveWhenHigh: boolean;
}

const SIGNALS: Record<ResearchDomain, readonly SignalDefinition[]> = {
  technical: [
    { key: "momentum_90d", label: "90 日動能", minimum: -0.2, maximum: 0.32, unit: "ratio", positiveWhenHigh: true },
    { key: "trend_strength", label: "趨勢強度", minimum: -1, maximum: 1, unit: "score", positiveWhenHigh: true },
    { key: "volatility_60d", label: "60 日波動率", minimum: 0.12, maximum: 0.68, unit: "ratio", positiveWhenHigh: false },
  ],
  fundamental: [
    { key: "revenue_growth_yoy", label: "營收年增率", minimum: -0.12, maximum: 0.48, unit: "ratio", positiveWhenHigh: true },
    { key: "operating_margin", label: "營業利益率", minimum: -0.06, maximum: 0.42, unit: "ratio", positiveWhenHigh: true },
    { key: "valuation_pressure", label: "估值壓力", minimum: 0, maximum: 1, unit: "score", positiveWhenHigh: false },
  ],
  sentiment: [
    { key: "news_sentiment", label: "新聞情緒", minimum: -1, maximum: 1, unit: "score", positiveWhenHigh: true },
    { key: "attention_change", label: "關注度變化", minimum: -0.6, maximum: 1.2, unit: "ratio", positiveWhenHigh: true },
    { key: "narrative_disagreement", label: "敘事分歧", minimum: 0, maximum: 1, unit: "score", positiveWhenHigh: false },
  ],
  macro: [
    { key: "growth_impulse", label: "成長動能", minimum: -1, maximum: 1, unit: "score", positiveWhenHigh: true },
    { key: "rate_pressure", label: "利率壓力", minimum: 0, maximum: 1, unit: "score", positiveWhenHigh: false },
    { key: "sector_sensitivity", label: "產業景氣敏感度", minimum: 0, maximum: 1, unit: "score", positiveWhenHigh: false },
  ],
};

export const RESEARCH_DOMAINS = [
  "technical",
  "fundamental",
  "sentiment",
  "macro",
] as const satisfies readonly ResearchDomain[];

function directionFor(
  value: number,
  definition: SignalDefinition,
): EvidenceDirection {
  const normalized = (value - definition.minimum) / (definition.maximum - definition.minimum);
  const positiveScore = definition.positiveWhenHigh ? normalized : 1 - normalized;
  if (positiveScore >= 0.62) return "bullish";
  if (positiveScore <= 0.38) return "bearish";
  return "neutral";
}

function createSignal(
  ticker: SupportedTicker,
  analysisDate: QuarterlyAnalysisDate,
  domain: ResearchDomain,
  definition: SignalDefinition,
): ResearchSignal {
  const key = `${ticker}|${analysisDate}|${domain}|${definition.key}`;
  const value = stableNumber(key, definition.minimum, definition.maximum);
  return {
    key: definition.key,
    label: definition.label,
    value,
    unit: definition.unit,
    direction: directionFor(value, definition),
    uncertainty: clamp(stableNumber(`${key}|uncertainty`, 0.12, 0.46), 0, 1),
  };
}

function evidenceFor(
  ticker: SupportedTicker,
  analysisDate: QuarterlyAnalysisDate,
  domain: ResearchDomain,
  signal: ResearchSignal,
): EvidenceItem {
  const raw = `${ticker}|${analysisDate}|${domain}|${signal.key}|${signal.value}`;
  const checksum = stableHash(raw);
  return {
    evidenceId: `ev-${domain.slice(0, 4)}-${checksum}`,
    domain,
    source: "Stance Shift Lab deterministic demo fixture",
    sourceUrl: `https://example.invalid/stance-shift-lab/${ticker}/${analysisDate}/${domain}/${signal.key}`,
    license: "Synthetic demo data; no external dataset",
    publishedAt: analysisDate,
    availableAt: analysisDate,
    analysisDate,
    claim: `${signal.label}的確定性示範值為 ${signal.value}。`,
    value: signal.value,
    direction: signal.direction,
    uncertainty: signal.uncertainty,
    checksum,
    synthetic: true,
  };
}

export function createDeterministicResearchSnapshots(
  ticker: string,
  analysisDate: string,
): readonly ResearchSnapshot[] {
  const selection = normalizeExperimentSelection(ticker, analysisDate);
  return RESEARCH_DOMAINS.map((domain) => {
    const signals = SIGNALS[domain].map((definition) =>
      createSignal(selection.ticker, selection.analysisDate, domain, definition),
    );
    const evidence = signals.map((signal) =>
      evidenceFor(selection.ticker, selection.analysisDate, domain, signal),
    );
    return {
      snapshotId: `snapshot-${domain}-${stableHash(`${selection.ticker}|${selection.analysisDate}|${domain}`)}`,
      ticker: selection.ticker,
      analysisDate: selection.analysisDate,
      domain,
      modelVersion: "deterministic-demo-v1" as const,
      generatedAt: `${selection.analysisDate}T23:59:59.000Z`,
      signals,
      evidence,
    };
  });
}

export function flattenSnapshotEvidence(
  snapshots: readonly ResearchSnapshot[],
): readonly EvidenceItem[] {
  return snapshots.flatMap((snapshot) => [...snapshot.evidence]);
}
