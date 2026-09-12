"""Open-to-open, point-in-time backtesting with explicit abstention accounting."""
import math

import numpy as np


def spread(previous, current):
    beta = math.log(previous["high"] / previous["low"])**2 + math.log(current["high"] / current["low"])**2
    gamma = math.log(max(previous["high"], current["high"]) / min(previous["low"], current["low"]))**2
    denominator = 3 - 2 * math.sqrt(2)
    alpha = max(0., (math.sqrt(2 * beta) - math.sqrt(beta)) / denominator - math.sqrt(gamma / denominator))
    return 2 * math.tanh(alpha / 2)


def rolling_spread(bars, window=20):
    """Median of the last ``window`` two-day Corwin--Schultz estimates."""
    pairs = [spread(previous, current) for previous, current in zip(bars[:-1], bars[1:])]
    if not pairs:
        return 0.
    return float(np.median(pairs[-window:]))


def _spread_basis(bars, window):
    if len(bars) < 2:
        return "insufficient_bars"
    return "rolling_median" if len(bars) >= window + 1 else "available_pairs_median"


def evaluate(prices, analysis_date, decisions, protocol):
    """Evaluate candidate and Gatekeeper actions using only the stored protocol."""
    future = [price for price in prices if price["date"] > analysis_date]
    past = [price for price in prices if price["date"] < analysis_date]
    rows, daily = [], []
    for horizon in protocol.horizons:
        for group, decision in decisions.items():
            for decision_layer, action_key in (("candidate", "candidate_action"), ("gated", "action")):
                action = decision[action_key]
                for cost_model in protocol.cost_models:
                    base = {"group": group, "horizon": horizon,
                            "endpoint": "primary" if horizon == protocol.primary_horizon else "robustness",
                            "cost_model": cost_model, "decision_layer": decision_layer, "action": action,
                            "candidate_action": decision["candidate_action"], "gated_action": decision["action"]}
                    if len(future) < horizon + 1:
                        rows.append({**base, "status": "pending", "available_sessions": len(future)})
                        continue
                    selected = future[:horizon + 1]
                    entry, exit_price = selected[0]["open"], selected[horizon]["open"]
                    direction = {"Buy": 1, "Sell": -1}.get(action, 0)
                    entry_spread = rolling_spread(past, protocol.spread_window)
                    # The exit occurs at the final bar's open. Its high/low
                    # are not known at that instant, so never include that
                    # bar in the rolling spread estimate.
                    exit_spread = rolling_spread(selected[:horizon], protocol.spread_window)
                    entry_cost = entry_spread / 2 if cost_model == "corwin_schultz" else 0.
                    exit_cost = exit_spread / 2 if cost_model == "corwin_schultz" else 0.
                    gross = direction * (exit_price / entry - 1)
                    cost = entry_cost + exit_cost * exit_price / entry if direction else 0.
                    equity, previous_equity, previous_mark = 1., 1., entry
                    insolvent, insolvent_date = False, None
                    for index in range(1, horizon + 1):
                        bar = selected[index]
                        mark_price = exit_price if index == horizon else bar["close"]
                        if insolvent:
                            equity = 0.
                        else:
                            marked_cost = entry_cost + (exit_cost * mark_price / entry if index == horizon else 0.) if direction else 0.
                            equity = max(0., 1 + direction * (mark_price / entry - 1) - marked_cost)
                            if equity == 0.:
                                insolvent, insolvent_date = True, bar["date"]
                        daily.append({**base, "date": bar["date"],
                                      "return": equity / previous_equity - 1 if previous_equity > 0 else 0.,
                                      "benchmark_return": mark_price / previous_mark - 1})
                        previous_equity, previous_mark = equity, mark_price
                    realized_move_pct = (exit_price / entry - 1) * 100
                    hold_band_pct = float(decision.get("hold_band_pct", 0.))
                    is_hold = direction == 0
                    rows.append({**base, "status": "complete", "entry_date": selected[0]["date"],
                                 "maturity_date": selected[horizon]["date"], "entry_price": entry, "exit_price": exit_price,
                                 "entry_spread": entry_spread, "exit_spread": exit_spread,
                                 "spread_window": protocol.spread_window,
                                 "spread_basis": {"entry": _spread_basis(past, protocol.spread_window),
                                                   "exit": _spread_basis(selected[:horizon], protocol.spread_window)},
                                 "gross_return": gross, "cost": cost, "net_return": -1. if insolvent else gross - cost,
                                 "benchmark_return": exit_price / entry - 1,
                                 "correct": (direction * (exit_price - entry) > 0) if direction else None,
                                 "insolvent": insolvent, "insolvent_date": insolvent_date,
                                 "realized_move_pct": realized_move_pct,
                                 "hold_band_pct": hold_band_pct,
                                 "hold_was_justified": abs(realized_move_pct) <= hold_band_pct if is_hold else None,
                                 "hold_opportunity_cost": max(0., abs(realized_move_pct) - hold_band_pct) if is_hold else 0.})
    return rows, daily


def metrics(returns):
    values = np.asarray(returns, dtype=float)
    if not len(values) or not np.isfinite(values).all() or np.any(values < -1):
        return {"status": "insufficient_or_invalid", "n": len(values)}
    equity = np.cumprod(1 + values)
    peaks = np.maximum.accumulate(np.r_[1., equity])[1:]
    std = float(values.std(ddof=1)) if len(values) > 1 else 0.
    return {"status": "complete", "n": len(values), "total_return": float(equity[-1] - 1),
            "max_drawdown": float(np.min(equity / peaks - 1)),
            "sharpe": float(values.mean() / std * math.sqrt(252)) if std > 1e-12 else None,
            "risk_free_rate": 0., "risk_free_convention": "explicit zero baseline; not market risk-free adjusted"}
