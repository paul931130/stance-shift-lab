/* eslint-disable @typescript-eslint/ban-ts-comment */
import assert from "node:assert/strict";
import test from "node:test";

import {
  BACKTEST_HORIZONS,
  LOGICAL_CALL_COUNTS,
  QUARTERLY_ANALYSIS_DATES,
  RESEARCH_DOMAINS,
  SUPPORTED_TICKERS,
  FutureLeakageError,
  assertEvidenceAvailable,
  buildLogicalCallPlan,
  countLogicalCalls,
  createDeterministicResearchSnapshots,
  flattenSnapshotEvidence,
  runBacktest,
  runDomainDemo,
  runGatekeeper,
  type EvidenceItem,
// @ts-ignore -- Node's native TypeScript test runner requires this explicit suffix.
} from "../lib/domain/index.ts";

function validEvidence(): EvidenceItem[] {
  return flattenSnapshotEvidence(
    createDeterministicResearchSnapshots("AAPL", "2024-06-30"),
  ).map((item) => ({ ...item }));
}

test("fixes the 10-ticker universe and all 2021-2025 quarter anchors", () => {
  assert.deepEqual(SUPPORTED_TICKERS, [
    "AAPL", "NVDA", "GOOGL", "MSFT", "AMZN", "JPM", "MCD", "LLY", "ASTS", "GE",
  ]);
  assert.equal(QUARTERLY_ANALYSIS_DATES.length, 20);
  for (const year of [2021, 2022, 2023, 2024, 2025]) {
    assert.equal(
      QUARTERLY_ANALYSIS_DATES.filter((date) => date.startsWith(`${year}-`)).length,
      4,
    );
  }
});

test("produces four byte-stable deterministic research snapshots", () => {
  const first = createDeterministicResearchSnapshots("nvda", "2023-09-30");
  const second = createDeterministicResearchSnapshots("NVDA", "2023-09-30");
  assert.deepEqual(first, second);
  assert.deepEqual(first.map((snapshot) => snapshot.domain), RESEARCH_DOMAINS);
  assert.equal(flattenSnapshotEvidence(first).length, 12);
  assert.doesNotThrow(() =>
    assertEvidenceAvailable(flattenSnapshotEvidence(first), "2023-09-30"),
  );
  assert.throws(
    () => createDeterministicResearchSnapshots("TSM", "2023-09-30"),
    /Unsupported ticker/,
  );
});

test("rejects evidence that was unavailable at the decision boundary", () => {
  const evidence = validEvidence();
  evidence[0] = { ...evidence[0], availableAt: "2024-07-01" };
  assert.throws(
    () => assertEvidenceAvailable(evidence, "2024-06-30"),
    FutureLeakageError,
  );

  const gate = runGatekeeper({
    candidate: { action: "Buy", confidence: 0.8 },
    evidence,
    analysisDate: "2024-06-30",
  });
  assert.equal(gate.finalAction, "NoTrade");
  assert.equal(gate.evidenceAudit.hasFutureLeakage, true);
  assert.ok(gate.reasons.some((reason) => reason.code === "evidence_metadata"));
});

test("builds exactly 1/5/7/7 calls and switches only D round 2", () => {
  const plan = buildLogicalCallPlan();
  assert.equal(plan.length, 20);
  assert.deepEqual(countLogicalCalls(plan), LOGICAL_CALL_COUNTS);

  const cTurns = plan.filter((call) => call.group === "C" && call.kind === "debate");
  assert.equal(cTurns.length, 6);
  assert.ok(cTurns.every((call) => call.roleSwitched === false));
  assert.deepEqual(
    cTurns.filter((call) => call.participant === "Agent-A").map((call) => call.role),
    ["Bull", "Bull", "Bull"],
  );

  const dTurns = plan.filter((call) => call.group === "D" && call.kind === "debate");
  assert.deepEqual(
    dTurns.map((call) => [call.round, call.participant, call.role, call.roleSwitched]),
    [
      [1, "Agent-A", "Bull", false],
      [1, "Agent-B", "Bear", false],
      [2, "Agent-A", "Bear", true],
      [2, "Agent-B", "Bull", true],
      [3, "Agent-A", "Bull", false],
      [3, "Agent-B", "Bear", false],
    ],
  );
  const dCalls = plan.filter((call) => call.group === "D");
  assert.equal(dCalls.at(-1)?.kind, "adjudication");
});

test("applies confidence, Buy-risk, and mature-history Gatekeeper rules", () => {
  const evidence = validEvidence();
  const lowConfidence = runGatekeeper({
    candidate: { action: "Sell", confidence: 0.52 },
    evidence,
    analysisDate: "2024-06-30",
  });
  assert.equal(lowConfidence.finalAction, "Hold");
  assert.deepEqual(lowConfidence.reasons.map((reason) => reason.code), ["directional_confidence"]);

  const riskyBuy = runGatekeeper({
    candidate: { action: "Buy", confidence: 0.8 },
    evidence,
    analysisDate: "2024-06-30",
    marketRisk: { volatility60d: 0.59, maxDrawdown: -0.23 },
  });
  assert.equal(riskyBuy.finalAction, "Hold");
  assert.ok(riskyBuy.reasons.some((reason) => reason.code === "buy_volatility"));
  assert.ok(riskyBuy.reasons.some((reason) => reason.code === "buy_drawdown"));

  const immatureHistory = runGatekeeper({
    candidate: { action: "Buy", confidence: 0.8 },
    evidence,
    analysisDate: "2024-06-30",
    history: { approvedResolvedCases: 19, accuracy: 0.1 },
  });
  assert.equal(immatureHistory.finalAction, "Buy");

  const matureHistory = runGatekeeper({
    candidate: { action: "Buy", confidence: 0.8 },
    evidence,
    analysisDate: "2024-06-30",
    history: { approvedResolvedCases: 20, accuracy: 0.44 },
  });
  assert.equal(matureHistory.finalAction, "Hold");
  assert.ok(matureHistory.reasons.some((reason) => reason.code === "historical_accuracy"));
});

test("does not touch future prices until the decision is locked", () => {
  let touched = false;
  const guardedPrices = new Proxy([], {
    get(target, property, receiver) {
      touched = true;
      return Reflect.get(target, property, receiver);
    },
  });
  assert.throws(
    () =>
      runBacktest({
        analysisDate: "2024-06-30",
        decision: { action: "Buy", confidence: 0.8, locked: false, lockedAt: "" },
        futurePrices: guardedPrices,
      }),
    /inaccessible until the decision is locked/,
  );
  assert.equal(touched, false);
});

test("uses the next session and first session on/after 30/60/90 calendar days", () => {
  const result = runBacktest({
    analysisDate: "2024-06-30",
    decision: {
      action: "Buy",
      confidence: 0.8,
      locked: true,
      lockedAt: "2024-06-30T23:59:59.000Z",
    },
    futurePrices: [
      { date: "2024-06-28", close: 98 },
      { date: "2024-07-01", close: 100 },
      { date: "2024-07-31", close: 102 },
      { date: "2024-08-30", close: 99 },
      { date: "2024-09-30", close: 104 },
    ],
  });
  assert.deepEqual(BACKTEST_HORIZONS, [30, 60, 90]);
  assert.deepEqual(
    result.horizons.map((horizon) => horizon.targetDate),
    ["2024-07-30", "2024-08-29", "2024-09-28"],
  );
  assert.deepEqual(
    result.horizons.map((horizon) => horizon.exitDate),
    ["2024-07-31", "2024-08-30", "2024-09-30"],
  );
  assert.ok(result.horizons.every((horizon) => horizon.entryDate === "2024-07-01"));
  assert.equal(result.horizons[0]?.marketReturn, 0.02);
  assert.equal(result.horizons[0]?.strategyReturn, 0.019);
  assert.deepEqual(
    result.horizons.map((horizon) => horizon.realizedLabel),
    ["Buy", "Hold", "Buy"],
  );
});

test("runs a complete offline domain demo", () => {
  const demo = runDomainDemo();
  assert.equal(demo.ticker, "AAPL");
  assert.equal(demo.evidenceCount, 12);
  assert.equal(demo.logicalCallTotal, 20);
  assert.deepEqual(demo.logicalCallCounts, { A: 1, B: 5, C: 7, D: 7 });
  assert.deepEqual(demo.groupDRound2, [
    { participant: "Agent-A", role: "Bear" },
    { participant: "Agent-B", role: "Bull" },
  ]);
  assert.equal(demo.gatekeeper.finalAction, "Buy");
  assert.equal(demo.backtest.horizons.length, 3);
});
