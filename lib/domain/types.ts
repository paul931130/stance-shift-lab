import type { QuarterlyAnalysisDate, SupportedTicker } from "./catalog.ts";

export type ResearchDomain =
  | "technical"
  | "fundamental"
  | "sentiment"
  | "macro";

export type EvidenceDirection = "bullish" | "neutral" | "bearish";
export type DecisionAction = "Buy" | "Hold" | "Sell" | "NoTrade";
export type ExperimentGroup = "A" | "B" | "C" | "D";
export type DebateRole = "Bull" | "Bear";

export interface EvidenceItem {
  evidenceId: string;
  domain: ResearchDomain;
  source: string;
  sourceUrl: string;
  license: string;
  publishedAt: string;
  availableAt: string;
  analysisDate: string;
  claim: string;
  value: number | string;
  direction: EvidenceDirection;
  /** 0 means highly certain; 1 means maximally uncertain. */
  uncertainty: number;
  checksum: string;
  synthetic?: boolean;
}

export interface ResearchSignal {
  key: string;
  label: string;
  value: number;
  unit: "ratio" | "percent" | "score";
  direction: EvidenceDirection;
  uncertainty: number;
}

export interface ResearchSnapshot {
  snapshotId: string;
  ticker: SupportedTicker;
  analysisDate: QuarterlyAnalysisDate;
  domain: ResearchDomain;
  modelVersion: "deterministic-demo-v1";
  generatedAt: string;
  signals: readonly ResearchSignal[];
  evidence: readonly EvidenceItem[];
}

export interface CandidateDecision {
  action: DecisionAction;
  confidence: number;
  rationale?: string;
}

export interface LockedDecision extends CandidateDecision {
  locked: true;
  lockedAt: string;
}
