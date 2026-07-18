// @ts-expect-error Node's native type-strip runner requires explicit .ts specifiers.
import { auditEvidence, type EvidenceAudit } from "./evidence.ts";
import type { CandidateDecision, DecisionAction, EvidenceItem } from "./types.ts";

export const GATEKEEPER_THRESHOLDS = {
  minimumEvidencePassRate: 0.8,
  minimumDomains: 3,
  minimumDirectionalConfidence: 0.53,
  maximumBuyVolatility60d: 0.58,
  minimumBuyDrawdown: -0.22,
  historyMinimumCases: 20,
  historyMinimumAccuracy: 0.45,
} as const;

export type GatekeeperReasonCode =
  | "evidence_pass_rate"
  | "evidence_domain_coverage"
  | "evidence_metadata"
  | "directional_confidence"
  | "buy_volatility"
  | "buy_drawdown"
  | "historical_accuracy";

export interface GatekeeperContext {
  candidate: CandidateDecision;
  evidence: readonly EvidenceItem[];
  analysisDate: string;
  marketRisk?: {
    volatility60d?: number;
    maxDrawdown?: number;
  };
  history?: {
    approvedResolvedCases: number;
    accuracy: number;
  };
}

export interface GatekeeperReason {
  code: GatekeeperReasonCode;
  message: string;
}

export interface GatekeeperResult {
  originalAction: DecisionAction;
  finalAction: DecisionAction;
  confidence: number;
  passed: boolean;
  evidenceAudit: EvidenceAudit;
  reasons: readonly GatekeeperReason[];
}

function assertProbability(value: number, label: string): void {
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    throw new RangeError(`${label} must be between 0 and 1.`);
  }
}

export function runGatekeeper(context: GatekeeperContext): GatekeeperResult {
  assertProbability(context.candidate.confidence, "Decision confidence");
  if (context.history) {
    if (
      !Number.isInteger(context.history.approvedResolvedCases) ||
      context.history.approvedResolvedCases < 0
    ) {
      throw new RangeError("approvedResolvedCases must be a non-negative integer.");
    }
    assertProbability(context.history.accuracy, "Historical accuracy");
  }

  const evidenceAudit = auditEvidence(context.evidence, context.analysisDate);
  const reasons: GatekeeperReason[] = [];
  let finalAction = context.candidate.action;

  if (evidenceAudit.passRate < GATEKEEPER_THRESHOLDS.minimumEvidencePassRate) {
    reasons.push({
      code: "evidence_pass_rate",
      message: `Evidence pass rate ${evidenceAudit.passRate.toFixed(2)} is below 0.80.`,
    });
  }
  if (evidenceAudit.validDomains.length < GATEKEEPER_THRESHOLDS.minimumDomains) {
    reasons.push({
      code: "evidence_domain_coverage",
      message: `Only ${evidenceAudit.validDomains.length} valid research domains are represented.`,
    });
  }
  if (evidenceAudit.hasCriticalMetadataIssue) {
    reasons.push({
      code: "evidence_metadata",
      message: "At least one citation, date boundary, or license field is invalid.",
    });
  }

  const evidenceFailed = reasons.some((reason) =>
    ["evidence_pass_rate", "evidence_domain_coverage", "evidence_metadata"].includes(
      reason.code,
    ),
  );
  if (evidenceFailed) {
    finalAction = "NoTrade";
  } else if (finalAction === "Buy" || finalAction === "Sell") {
    if (
      context.candidate.confidence <
      GATEKEEPER_THRESHOLDS.minimumDirectionalConfidence
    ) {
      reasons.push({
        code: "directional_confidence",
        message: "Directional confidence is below 0.53.",
      });
      finalAction = "Hold";
    }

    if (
      context.candidate.action === "Buy" &&
      context.marketRisk?.volatility60d !== undefined &&
      context.marketRisk.volatility60d >
        GATEKEEPER_THRESHOLDS.maximumBuyVolatility60d
    ) {
      reasons.push({
        code: "buy_volatility",
        message: "60-day volatility exceeds 0.58.",
      });
      finalAction = "Hold";
    }
    if (
      context.candidate.action === "Buy" &&
      context.marketRisk?.maxDrawdown !== undefined &&
      context.marketRisk.maxDrawdown < GATEKEEPER_THRESHOLDS.minimumBuyDrawdown
    ) {
      reasons.push({
        code: "buy_drawdown",
        message: "Maximum drawdown is worse than -0.22.",
      });
      finalAction = "Hold";
    }
    if (
      context.history &&
      context.history.approvedResolvedCases >=
        GATEKEEPER_THRESHOLDS.historyMinimumCases &&
      context.history.accuracy < GATEKEEPER_THRESHOLDS.historyMinimumAccuracy
    ) {
      reasons.push({
        code: "historical_accuracy",
        message: "Accuracy is below 0.45 after at least 20 approved resolved cases.",
      });
      finalAction = "Hold";
    }
  }

  return {
    originalAction: context.candidate.action,
    finalAction,
    confidence: context.candidate.confidence,
    passed: finalAction === context.candidate.action && reasons.length === 0,
    evidenceAudit,
    reasons,
  };
}
