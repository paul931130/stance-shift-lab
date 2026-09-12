"""Paired study inference. Inputs must already be aligned by case/date.

Sharpe inference follows Ledoit & Wolf (2008), equations 2, 5–9. We use a
Bartlett HAC estimator for the original-sample studentizer, and the paper's
natural block studentizer in circular bootstrap samples. The kernel and block
length are reported explicitly; this is not an IID/percentile bootstrap.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.stats import binomtest, norm


def mcnemar(correct_a, correct_b) -> dict:
    a, b = np.asarray(correct_a), np.asarray(correct_b)
    if a.ndim != 1 or a.shape != b.shape or len(a) == 0:
        raise ValueError("McNemar requires nonempty aligned paired cases")
    if a.dtype != np.bool_ or b.dtype != np.bool_:
        raise ValueError("Correctness values must be explicit booleans, without missing observations")
    both = int(np.sum(a & b))
    a_only = int(np.sum(a & ~b))
    b_only = int(np.sum(~a & b))
    neither = int(np.sum(~a & ~b))
    discordant = a_only + b_only
    pvalue = float(binomtest(a_only, discordant, .5).pvalue) if discordant else 1.0
    return {"method": "mcnemar_exact_two_sided", "n": len(a), "table": [[both, a_only], [b_only, neither]],
            "discordant": discordant, "pvalue": pvalue,
            "accuracy_difference": float(a.mean() - b.mean()),
            "warning": "Case dependence across stocks/dates is not corrected by the classical McNemar test; interpret with paired cluster/block sensitivity analysis."}


def _paired_returns(a, b) -> np.ndarray:
    values = np.column_stack((np.asarray(a, dtype=float), np.asarray(b, dtype=float)))
    if values.ndim != 2 or values.shape[1] != 2 or len(values) < 5 or not np.isfinite(values).all():
        raise ValueError("At least five complete aligned return pairs are required")
    if np.any(values.std(axis=0) <= 1e-12):
        raise ValueError("Sharpe inference is undefined for zero-variance returns")
    return values


def jobson_korkie_memmel(a, b, periods_per_year: int = 252) -> dict:
    values = _paired_returns(a, b)
    n = len(values)
    sharpe = values.mean(axis=0) / values.std(axis=0, ddof=1)
    rho = float(np.corrcoef(values.T)[0, 1])
    variance = (2 * (1 - rho) + .5 * (sharpe[0] ** 2 + sharpe[1] ** 2 - 2 * sharpe[0] * sharpe[1] * rho ** 2)) / n
    difference = float(sharpe[0] - sharpe[1])
    if variance <= 1e-15:
        return {"method": "jobson_korkie_memmel", "n": n, "status": "degenerate", "pvalue": None, "difference": difference}
    z = difference / math.sqrt(variance)
    return {"method": "jobson_korkie_memmel", "n": n, "status": "ok", "statistic": z,
            "pvalue": float(2 * norm.sf(abs(z))), "difference": difference,
            "annualized_difference": difference * math.sqrt(periods_per_year),
            "warning": "Assumes IID jointly normal excess returns; use the block-bootstrap result for dependent/heavy-tailed data."}


def _moments(values):
    moments = np.column_stack((values, values ** 2))
    mu = moments.mean(axis=0)
    a, b, c, d = mu
    vi, vn = c - a * a, d - b * b
    if min(vi, vn) <= 1e-24:
        raise ValueError("Degenerate return variance")
    delta = a / math.sqrt(vi) - b / math.sqrt(vn)
    gradient = np.array([c / vi ** 1.5, -d / vn ** 1.5, -.5 * a / vi ** 1.5, .5 * b / vn ** 1.5])
    return float(delta), gradient, moments - mu


def _hac_se(centered, gradient, lag):
    n = len(centered)
    covariance = centered.T @ centered / n
    for offset in range(1, lag + 1):
        gamma = centered[offset:].T @ centered[:-offset] / n
        covariance += (1 - offset / (lag + 1)) * (gamma + gamma.T)
    covariance *= n / (n - 4)
    return math.sqrt(max(0., float(gradient @ covariance @ gradient / n)))


def circular_block_indices(n: int, block_length: int, rng) -> np.ndarray:
    if block_length < 2 or n < block_length * 3:
        raise ValueError("At least three blocks and block length >=2 are required")
    starts = rng.integers(0, n, size=n // block_length)
    return ((starts[:, None] + np.arange(block_length)) % n).reshape(-1)


def ledoit_wolf_block(a, b, *, block_length=20, replicates=1999, seed=905, alpha=.05, periods_per_year=252) -> dict:
    values = _paired_returns(a, b)
    n = len(values)
    if not 0 < alpha < 1 or replicates < 199 or block_length < 2 or n < 3 * block_length:
        raise ValueError("Invalid bootstrap configuration or fewer than three date blocks")
    delta, gradient, centered = _moments(values)
    lag = min(block_length - 1, n - 5)
    se = _hac_se(centered, gradient, lag)
    if se <= 1e-12:
        return {"method": "ledoit_wolf_studentized_circular_block", "status": "degenerate", "n": n, "pvalue": None, "confidence_interval": None}
    rng = np.random.default_rng(seed)
    pivots = []
    for _ in range(replicates):
        sampled = values[circular_block_indices(n, block_length, rng)]
        try:
            sampled_delta, sampled_gradient, residuals = _moments(sampled)
        except ValueError:
            continue
        # Eq. (9): block sums preserve the sampled blocks' dependence structure.
        sums = residuals.reshape(-1, block_length, 4).sum(axis=1) / math.sqrt(block_length)
        covariance = sums.T @ sums / len(sums)
        sampled_se = math.sqrt(max(0., float(sampled_gradient @ covariance @ sampled_gradient / len(sampled))))
        if sampled_se > 1e-12:
            pivots.append(abs(sampled_delta - delta) / sampled_se)
    if len(pivots) < .9 * replicates:
        raise ValueError("Too many degenerate bootstrap samples; cannot report reliable inference")
    critical = float(np.quantile(pivots, 1 - alpha, method="higher"))
    scale = math.sqrt(periods_per_year)
    interval = [(delta - critical * se) * scale, (delta + critical * se) * scale]
    pvalue = (1 + sum(pivot >= abs(delta) / se for pivot in pivots)) / (len(pivots) + 1)
    return {"method": "ledoit_wolf_studentized_circular_block", "status": "ok", "n": n,
            "sampled_n": (n // block_length) * block_length,
            "annualized_difference": delta * scale, "confidence_interval": interval,
            "confidence_level": 1 - alpha, "pvalue": pvalue, "seed": seed, "block_length": block_length,
            "replicates": replicates, "valid_replicates": len(pivots),
            "original_studentizer": "Bartlett HAC with n/(n-4) adjustment", "hac_lag": lag,
            "bootstrap_studentizer": "natural non-overlapping sampled block sums",
            "warning": "Requires sufficiently stationary finite-fourth-moment excess returns; not a proof of future performance."}


def aligned_portfolio_returns(panel, weights=None) -> np.ndarray:
    """Convert date × stock × method data to date × method, without stacking stocks.

    Complete same-date panels are required. Equal/fixed weights mean subsequent
    date-block sampling resamples every stock and method together, preserving
    market-wide cross-sectional dependence instead of treating stocks as IID.
    """
    values = np.asarray(panel, dtype=float)
    if values.ndim != 3 or not values.size or not np.isfinite(values).all():
        raise ValueError("Expected a complete finite date × stock × method return panel")
    weights = np.full(values.shape[1], 1 / values.shape[1]) if weights is None else np.asarray(weights, dtype=float)
    if weights.shape != (values.shape[1],) or not np.isfinite(weights).all() or np.any(weights < 0) or not np.isclose(weights.sum(), 1):
        raise ValueError("Fixed nonnegative portfolio weights must sum to one")
    return np.einsum("tsm,s->tm", values, weights)


def holm_adjust(pvalues: list[float]) -> list[float]:
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in pvalues):
        raise ValueError("P-values must be finite values in [0, 1]")
    order = sorted(range(len(pvalues)), key=pvalues.__getitem__)
    result = [0.] * len(pvalues)
    maximum = 0.
    for rank, index in enumerate(order):
        maximum = max(maximum, min(1., (len(pvalues) - rank) * pvalues[index]))
        result[index] = maximum
    return result
