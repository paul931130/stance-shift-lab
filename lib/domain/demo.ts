// @ts-expect-error Node's native type-strip runner requires explicit .ts specifiers.
import { runBacktest } from "./backtest.ts";
// @ts-expect-error Node's native type-strip runner requires explicit .ts specifiers.
import { buildLogicalCallPlan, countLogicalCalls } from "./call-plan.ts";
// @ts-expect-error Node's native type-strip runner requires explicit .ts specifiers.
import { runGatekeeper } from "./gatekeeper.ts";
// @ts-expect-error Node's native type-strip runner requires explicit .ts specifiers.
import { createDeterministicResearchSnapshots, flattenSnapshotEvidence } from "./research.ts";
import type { LockedDecision } from "./types.ts";

export interface DomainDemoResult {
  ticker: string;
  analysisDate: string;
  researchDomains: readonly string[];
  evidenceCount: number;
  logicalCallCounts: Record<"A" | "B" | "C" | "D", number>;
  logicalCallTotal: number;
  groupDRound2: readonly { participant: string; role: string }[];
  gatekeeper: ReturnType<typeof runGatekeeper>;
  backtest: ReturnType<typeof runBacktest>;
}

/**
 * Runs the complete deterministic domain demonstration without network, LLM,
 * database, or clock dependencies. It is safe for smoke tests and UI previews.
 */
export function runDomainDemo(
  ticker = "AAPL",
  analysisDate = "2024-06-30",
): DomainDemoResult {
  const snapshots = createDeterministicResearchSnapshots(ticker, analysisDate);
  const evidence = flattenSnapshotEvidence(snapshots);
  const callPlan = buildLogicalCallPlan();
  const gatekeeper = runGatekeeper({
    candidate: {
      action: "Buy",
      confidence: 0.67,
      rationale: "Deterministic demonstration decision; not investment advice.",
    },
    evidence,
    analysisDate,
    marketRisk: { volatility60d: 0.32, maxDrawdown: -0.14 },
    history: { approvedResolvedCases: 0, accuracy: 0 },
  });
  const lockedDecision: LockedDecision = {
    action: gatekeeper.finalAction,
    confidence: gatekeeper.confidence,
    rationale: "Gatekeeper-approved deterministic demonstration.",
    locked: true,
    lockedAt: `${analysisDate}T23:59:59.000Z`,
  };
  const backtest = runBacktest({
    analysisDate,
    decision: lockedDecision,
    futurePrices: [
      { date: "2024-07-01", close: 100 },
      { date: "2024-07-30", close: 103 },
      { date: "2024-08-29", close: 101 },
      { date: "2024-09-30", close: 106 },
    ],
  });

  return {
    ticker: snapshots[0]?.ticker ?? ticker,
    analysisDate,
    researchDomains: snapshots.map((snapshot) => snapshot.domain),
    evidenceCount: evidence.length,
    logicalCallCounts: countLogicalCalls(callPlan),
    logicalCallTotal: callPlan.length,
    groupDRound2: callPlan
      .filter((call) => call.group === "D" && call.round === 2)
      .map((call) => ({ participant: call.participant, role: call.role ?? "" })),
    gatekeeper,
    backtest,
  };
}
