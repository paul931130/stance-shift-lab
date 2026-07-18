// @ts-expect-error Node's native type-strip runner requires explicit .ts specifiers.
import { addCalendarDays, compareIsoDates, parseIsoDate } from "./date.ts";
import type { DecisionAction, LockedDecision } from "./types.ts";

export const BACKTEST_HORIZONS = [30, 60, 90] as const;
export type BacktestHorizon = (typeof BACKTEST_HORIZONS)[number];

export interface FuturePriceObservation {
  date: string;
  close: number;
}

export interface HorizonBacktestResult {
  horizonDays: BacktestHorizon;
  targetDate: string;
  status: "complete" | "unavailable";
  entryDate?: string;
  entryPrice?: number;
  exitDate?: string;
  exitPrice?: number;
  marketReturn?: number;
  strategyReturn?: number;
  realizedLabel?: Exclude<DecisionAction, "NoTrade">;
}

export interface BacktestResult {
  analysisDate: string;
  decisionAction: DecisionAction;
  position: "long" | "cash";
  transactionCostBps: number;
  horizons: readonly HorizonBacktestResult[];
}

export interface BacktestInput {
  analysisDate: string;
  decision: LockedDecision | (Omit<LockedDecision, "locked"> & { locked: boolean });
  /** Kept separate from research inputs and read only after the lock check. */
  futurePrices: readonly FuturePriceObservation[];
  /** Fixed round-trip cost in basis points. */
  transactionCostBps?: number;
}

function round(value: number): number {
  return Number(value.toFixed(6));
}

function realizedLabel(marketReturn: number): "Buy" | "Hold" | "Sell" {
  if (marketReturn > 0.015) return "Buy";
  if (marketReturn < -0.015) return "Sell";
  return "Hold";
}

export function runBacktest(input: BacktestInput): BacktestResult {
  // This guard intentionally precedes any iteration or read of futurePrices.
  if (input.decision.locked !== true) {
    throw new Error("Future prices are inaccessible until the decision is locked.");
  }
  parseIsoDate(input.analysisDate);
  const transactionCostBps = input.transactionCostBps ?? 10;
  if (!Number.isFinite(transactionCostBps) || transactionCostBps < 0) {
    throw new RangeError("transactionCostBps must be a non-negative number.");
  }

  const futurePrices = [...input.futurePrices]
    .map((observation) => {
      parseIsoDate(observation.date);
      if (!Number.isFinite(observation.close) || observation.close <= 0) {
        throw new RangeError(`Invalid close price on ${observation.date}.`);
      }
      return observation;
    })
    .filter((observation) => compareIsoDates(observation.date, input.analysisDate) > 0)
    .sort((left, right) => compareIsoDates(left.date, right.date));

  const entry = futurePrices[0];
  const isLong = input.decision.action === "Buy";
  const cost = transactionCostBps / 10_000;

  const horizons = BACKTEST_HORIZONS.map<HorizonBacktestResult>((horizonDays) => {
    const targetDate = addCalendarDays(input.analysisDate, horizonDays);
    const exit = futurePrices.find(
      (observation) => compareIsoDates(observation.date, targetDate) >= 0,
    );
    if (!entry || !exit) {
      return { horizonDays, targetDate, status: "unavailable" };
    }

    const marketReturn = exit.close / entry.close - 1;
    const strategyReturn = isLong ? marketReturn - cost : 0;
    return {
      horizonDays,
      targetDate,
      status: "complete",
      entryDate: entry.date,
      entryPrice: entry.close,
      exitDate: exit.date,
      exitPrice: exit.close,
      marketReturn: round(marketReturn),
      strategyReturn: round(strategyReturn),
      realizedLabel: realizedLabel(marketReturn),
    };
  });

  return {
    analysisDate: input.analysisDate,
    decisionAction: input.decision.action,
    position: isLong ? "long" : "cash",
    transactionCostBps,
    horizons,
  };
}
