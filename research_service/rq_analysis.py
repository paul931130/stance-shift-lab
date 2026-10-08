"""RQ2/RQ3 inference helpers built on the RQ1 paired-study conventions.

RQ2 (model heterogeneity) estimates an interaction contrast

    Delta = (Acc_D,hetero - Acc_C,hetero) - (Acc_D,homo - Acc_C,homo)

and the matching Sharpe interaction.  The heterogeneous condition may be run in
two balanced assignments (AB: Bull=A/Bear=B, BA: Bull=B/Bear=A).  Both share the
same case and outcome, so they are *not* independent observations: this module
never stacks them into 2n cases or concatenates their daily returns into a
double-length series.  The two pre-specifiable options are

* ``"separate"``: report the AB and BA contrasts side by side;
* ``"mean"`` (accuracy) / ``"pooled_half_weight"`` (Sharpe): average the two
  assignments *within* each case (accuracy) or each trading day (returns,
  i.e. a portfolio holding each case sleeve at half weight per assignment).

RQ3 (domain specialisation) uses the same paired machinery for rule-matched
contrasts and adds a performance--cost table and the 4:0/3:1/2:2 agreement
distribution of domain views, which are intermediate outputs of one case.

Accuracy inference resamples whole analysis dates (every case on a date, every
arm and assignment together) with circular blocks of consecutive dates.  Sharpe
inference generalises the Ledoit--Wolf studentized circular block bootstrap in
``statistics.py`` to a linear combination of Sharpe ratios, recomputing every
arm's Sharpe from the resampled aligned daily panel in each replicate.

Nothing here reads study results or calls a model.  The power helper is a
planning tool only.
"""
from __future__ import annotations

import math
from collections import Counter

import numpy as np
from scipy.stats import t as student_t

from .statistics import circular_block_indices, holm_adjust, mcnemar

RQ2_ACCURACY_ARMS = ("C_homo", "D_homo", "C_hetero_AB", "D_hetero_AB", "C_hetero_BA", "D_hetero_BA")
HETERO_OPTIONS = ("separate", "mean")
SHARPE_HETERO_OPTIONS = ("separate", "pooled_half_weight")
BINARY_DIRECTIONS = ("Buy", "Sell")


# ---------------------------------------------------------------------------
# Date-block bootstrap for case-level linear contrasts
# ---------------------------------------------------------------------------

def _boolean_vector(name, values, n=None):
    array = np.asarray(values)
    if array.ndim != 1 or len(array) == 0:
        raise ValueError(f"{name} must be a nonempty 1-D array")
    if array.dtype != np.bool_:
        raise ValueError(f"{name} must contain explicit booleans without missing observations")
    if n is not None and len(array) != n:
        raise ValueError(f"{name} is not aligned with the other arms")
    return array


def _date_groups(date_ids, n):
    dates = np.asarray(date_ids)
    if dates.ndim != 1 or len(dates) != n:
        raise ValueError("date_ids must label every case")
    labels, inverse = np.unique(dates, return_inverse=True)
    return labels, inverse


def date_block_indices(n_dates: int, block_length: int, rng) -> np.ndarray:
    """Circular blocks of consecutive (sorted) analysis dates, truncated to ``n_dates``.

    ``block_length=1`` is the ordinary date-cluster bootstrap.  Longer blocks
    keep adjacent quarters together, which matters when holding periods or
    market regimes overlap neighbouring analysis dates.
    """
    if block_length < 1 or n_dates < 3 * block_length:
        # Same minimum as statistics.date_cluster_block_accuracy.
        raise ValueError("At least three date blocks are required")
    blocks = math.ceil(n_dates / block_length)
    starts = rng.integers(0, n_dates, size=blocks)
    return ((starts[:, None] + np.arange(block_length)) % n_dates).reshape(-1)[:n_dates]


def date_block_bootstrap(case_contrasts, date_ids, *, block_length=1, replicates=1999,
                         seed=905, alpha=.05) -> dict:
    """Bootstrap the mean of one or more per-case contrasts by resampling dates.

    ``case_contrasts`` is ``n`` (one contrast) or ``n x k`` (k contrasts that
    must share the same resampling indices, e.g. the AB and BA interactions).
    The estimate in each replicate is the ratio of resampled date sums to
    resampled case counts, so dates with exclusions keep their real weight.
    The interval is the percentile interval; the two-sided p-value is the share
    of centred replicates at least as extreme as the estimate.
    """
    values = np.asarray(case_contrasts, dtype=float)
    single = values.ndim == 1
    values = values[:, None] if single else values
    if values.ndim != 2 or not len(values) or not np.isfinite(values).all():
        raise ValueError("Case contrasts must be a complete finite n or n x k array")
    if not 0 < alpha < 1 or replicates < 199:
        raise ValueError("Invalid bootstrap configuration")
    labels, inverse = _date_groups(date_ids, len(values))
    n_dates = len(labels)
    sums = np.zeros((n_dates, values.shape[1]))
    np.add.at(sums, inverse, values)
    counts = np.bincount(inverse, minlength=n_dates).astype(float)
    estimate = sums.sum(axis=0) / counts.sum()
    rng = np.random.default_rng(seed)
    draws = np.empty((replicates, values.shape[1]))
    for index in range(replicates):
        chosen = date_block_indices(n_dates, block_length, rng)
        draws[index] = sums[chosen].sum(axis=0) / counts[chosen].sum()
    lower = np.quantile(draws, alpha / 2, axis=0, method="lower")
    upper = np.quantile(draws, 1 - alpha / 2, axis=0, method="higher")
    extreme = (np.abs(draws - estimate) >= np.abs(estimate) - 1e-15).sum(axis=0)
    pvalues = (1 + extreme) / (replicates + 1)
    rows = [{"estimate": float(estimate[j]), "bootstrap_se": float(draws[:, j].std(ddof=1)),
             "confidence_interval": [float(lower[j]), float(upper[j])],
             "pvalue": float(pvalues[j])} for j in range(values.shape[1])]
    meta = {"method": "date_block_bootstrap_percentile", "n_cases": len(values), "n_dates": n_dates,
            "block_length_dates": block_length, "replicates": replicates, "seed": seed,
            "confidence_level": 1 - alpha,
            "resampling_unit": "whole analysis dates (all cases, arms and assignments jointly)"}
    return {**meta, **rows[0]} if single else {**meta, "contrasts": rows}


def block_length_sensitivity(case_contrasts, date_ids, *, block_lengths=(1, 2, 4), **kwargs) -> dict:
    """Repeat :func:`date_block_bootstrap` for several date-block lengths (same seed)."""
    results = {}
    for length in block_lengths:
        try:
            results[int(length)] = date_block_bootstrap(case_contrasts, date_ids, block_length=int(length), **kwargs)
        except ValueError as error:
            results[int(length)] = {"status": "not_estimable", "reason": str(error)}
    return {"status": "sensitivity", "block_lengths_dates": [int(x) for x in block_lengths], "results": results}


# ---------------------------------------------------------------------------
# RQ2 accuracy interaction
# ---------------------------------------------------------------------------

def rq2_case_contrasts(correct: dict, hetero: str = "mean") -> dict:
    """Per-case interaction contributions for the chosen AB/BA handling.

    ``correct`` maps each name in :data:`RQ2_ACCURACY_ARMS` to an aligned boolean
    array (one entry per stock--date case, identical case order).  For
    ``"mean"`` the hetero correctness is the per-case mean over AB and BA (values
    0, 0.5, 1 -- not binary).  For ``"separate"`` two columns (AB, BA) are
    returned and must be reported together, never pooled into 2n rows.
    """
    if hetero not in HETERO_OPTIONS:
        raise ValueError(f"hetero must be one of {HETERO_OPTIONS}")
    missing = [arm for arm in RQ2_ACCURACY_ARMS if arm not in correct]
    if missing:
        raise ValueError(f"Missing arms: {missing}")
    n = len(np.asarray(correct["C_homo"]))
    arms = {arm: _boolean_vector(arm, correct[arm], n).astype(float) for arm in RQ2_ACCURACY_ARMS}
    homo = arms["D_homo"] - arms["C_homo"]
    ab = arms["D_hetero_AB"] - arms["C_hetero_AB"]
    ba = arms["D_hetero_BA"] - arms["C_hetero_BA"]
    if hetero == "mean":
        return {"hetero": hetero, "labels": ["interaction_mean_AB_BA"],
                "contrasts": (ab + ba) / 2 - homo, "arms": arms}
    return {"hetero": hetero, "labels": ["interaction_AB", "interaction_BA"],
            "contrasts": np.column_stack((ab - homo, ba - homo)), "arms": arms}


def rq2_accuracy_interaction(correct: dict, date_ids, *, hetero="mean", block_length=1,
                             sensitivity_block_lengths=(1, 2, 4), replicates=1999, seed=905,
                             alpha=.05) -> dict:
    """Accuracy interaction contrast with a joint paired date-block bootstrap.

    The primary block length (dates) must be preregistered; the sensitivity
    lengths are reported with the same seed.  Within-condition exact McNemar
    tests are attached only for binary comparisons (homo, AB, BA) as secondary
    descriptions; they are not a test of the interaction, and "significant in
    one condition, not the other" does not establish an interaction.
    """
    built = rq2_case_contrasts(correct, hetero)
    arms = built["arms"]
    config = dict(replicates=replicates, seed=seed, alpha=alpha)
    primary = date_block_bootstrap(built["contrasts"], date_ids, block_length=block_length, **config)
    sensitivity = block_length_sensitivity(built["contrasts"], date_ids,
                                           block_lengths=sensitivity_block_lengths, **config)
    accuracy = {arm: float(values.mean()) for arm, values in arms.items()}
    if hetero == "mean":
        accuracy["C_hetero_mean"] = (accuracy["C_hetero_AB"] + accuracy["C_hetero_BA"]) / 2
        accuracy["D_hetero_mean"] = (accuracy["D_hetero_AB"] + accuracy["D_hetero_BA"]) / 2
    secondary = {}
    for label, (d_arm, c_arm) in {"homo": ("D_homo", "C_homo"), "hetero_AB": ("D_hetero_AB", "C_hetero_AB"),
                                  "hetero_BA": ("D_hetero_BA", "C_hetero_BA")}.items():
        secondary[label] = mcnemar(arms[d_arm].astype(bool), arms[c_arm].astype(bool))
    return {"estimand": "(Acc_D,hetero - Acc_C,hetero) - (Acc_D,homo - Acc_C,homo)",
            "hetero_handling": hetero, "contrast_labels": built["labels"], "arm_accuracy": accuracy,
            "n_cases": len(arms["C_homo"]), "primary": primary, "block_length_sensitivity": sensitivity,
            "secondary_within_condition_mcnemar": secondary,
            "notes": ["AB and BA share each case and outcome; they are never counted as 2n observations.",
                      "Per-case mean correctness over AB/BA is not binary; plain McNemar is not applied to it.",
                      "Interaction of experimental factors, not an observational difference-in-differences."]}


# ---------------------------------------------------------------------------
# Sharpe contrasts (studentized circular block bootstrap, Ledoit--Wolf style)
# ---------------------------------------------------------------------------

def _return_matrix(returns: dict, names):
    columns = []
    for name in names:
        if name not in returns:
            raise ValueError(f"Missing daily returns for {name}")
        columns.append(np.asarray(returns[name], dtype=float))
    lengths = {len(column) for column in columns}
    if len(lengths) != 1 or any(column.ndim != 1 for column in columns):
        raise ValueError("Daily return series must be aligned 1-D arrays of identical length "
                         "(never concatenate assignments into a longer series)")
    values = np.column_stack(columns)
    if len(values) < 5 or not np.isfinite(values).all():
        raise ValueError("At least five complete aligned daily returns are required")
    if np.any(values.std(axis=0) <= 1e-12):
        raise ValueError("Sharpe inference is undefined for zero-variance returns")
    return values


def _combination_moments(values, weights):
    """Return sum_j w_j * SR_j, its gradient w.r.t. (means, second moments), and centred moments."""
    k = values.shape[1]
    moments = np.column_stack((values, values ** 2))
    mu = moments.mean(axis=0)
    first, second = mu[:k], mu[k:]
    variance = second - first ** 2
    if np.min(variance) <= 1e-24:
        raise ValueError("Degenerate return variance")
    sharpe = first / np.sqrt(variance)
    gradient = np.concatenate((weights * second / variance ** 1.5, -.5 * weights * first / variance ** 1.5))
    return float(weights @ sharpe), sharpe, gradient, moments - mu


def sharpe_combination_test(values, weights, *, block_length=20, replicates=1999, seed=905, alpha=.05,
                            periods_per_year=252) -> dict:
    """Studentized circular block bootstrap for ``sum_j w_j * Sharpe_j``.

    ``values`` is a T x k aligned daily return matrix.  Every replicate draws one
    set of circular trading-day blocks shared by all k columns and recomputes
    each Sharpe from the resampled panel.  With k=2 and weights (1, -1) this
    reproduces :func:`statistics.ledoit_wolf_block` exactly.
    """
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if values.ndim != 2 or weights.shape != (values.shape[1],):
        raise ValueError("weights must match the number of return columns")
    n, k = values.shape
    if not 0 < alpha < 1 or replicates < 199 or block_length < 2 or n < 3 * block_length or n <= 2 * k + 1:
        raise ValueError("Invalid bootstrap configuration or fewer than three date blocks")
    estimate, sharpe, gradient, centered = _combination_moments(values, weights)
    lag = min(block_length - 1, n - 5)
    covariance = centered.T @ centered / n
    for offset in range(1, lag + 1):
        gamma = centered[offset:].T @ centered[:-offset] / n
        covariance += (1 - offset / (lag + 1)) * (gamma + gamma.T)
    covariance *= n / (n - 2 * k)
    se = math.sqrt(max(0., float(gradient @ covariance @ gradient / n)))
    scale = math.sqrt(periods_per_year)
    base = {"method": "studentized_circular_block_sharpe_combination", "n_days": n, "weights": weights.tolist(),
            "annualized_sharpe": (sharpe * scale).tolist(), "annualized_estimate": estimate * scale,
            "block_length_days": block_length, "replicates": replicates, "seed": seed}
    if se <= 1e-12:
        return {**base, "status": "degenerate", "pvalue": None, "confidence_interval": None}
    rng = np.random.default_rng(seed)
    pivots, raw = [], []
    for _ in range(replicates):
        sampled = values[circular_block_indices(n, block_length, rng)]
        try:
            sampled_estimate, _, sampled_gradient, residuals = _combination_moments(sampled, weights)
        except ValueError:
            continue
        sums = residuals.reshape(-1, block_length, 2 * k).sum(axis=1) / math.sqrt(block_length)
        sampled_cov = sums.T @ sums / len(sums)
        sampled_se = math.sqrt(max(0., float(sampled_gradient @ sampled_cov @ sampled_gradient / len(sampled))))
        if sampled_se > 1e-12:
            pivots.append(abs(sampled_estimate - estimate) / sampled_se)
            raw.append(sampled_estimate)
    if len(pivots) < .9 * replicates:
        raise ValueError("Too many degenerate bootstrap samples; cannot report reliable inference")
    critical = float(np.quantile(pivots, 1 - alpha, method="higher"))
    pvalue = (1 + sum(pivot >= abs(estimate) / se for pivot in pivots)) / (len(pivots) + 1)
    return {**base, "status": "ok", "sampled_n": (n // block_length) * block_length,
            "confidence_interval": [(estimate - critical * se) * scale, (estimate + critical * se) * scale],
            "confidence_level": 1 - alpha, "pvalue": pvalue, "valid_replicates": len(pivots),
            "bootstrap_sd_annualized": float(np.std(raw, ddof=1) * scale), "hac_lag": lag,
            "original_studentizer": f"Bartlett HAC with n/(n-{2 * k}) adjustment",
            "bootstrap_studentizer": "natural non-overlapping sampled block sums"}


def pooled_assignment_returns(ab, ba) -> np.ndarray:
    """Daily returns of a portfolio holding every case sleeve half in AB and half in BA.

    This is the explicit "pooled at half weight" construction: same T as each
    assignment, never a 2T concatenation, and its Sharpe is not the mean of the
    two assignment Sharpes.
    """
    first, second = np.asarray(ab, dtype=float), np.asarray(ba, dtype=float)
    if first.ndim != 1 or first.shape != second.shape:
        raise ValueError("AB and BA daily returns must be aligned on the same trading days")
    return .5 * first + .5 * second


def rq2_sharpe_interaction(returns: dict, *, hetero="separate", block_length=20, replicates=1999, seed=905,
                           alpha=.05, periods_per_year=252) -> dict:
    """Sharpe interaction (SR_D,het - SR_C,het) - (SR_D,homo - SR_C,homo).

    ``returns`` maps ``C_homo``, ``D_homo``, ``C_hetero_AB``, ``D_hetero_AB``,
    ``C_hetero_BA``, ``D_hetero_BA`` to aligned daily portfolio returns (e.g.
    from ``statistics.aligned_portfolio_returns``).  ``"separate"`` tests the AB
    and BA interactions individually (same seed, shared indices);
    ``"pooled_half_weight"`` builds one hetero series per arm with
    :func:`pooled_assignment_returns` before computing any Sharpe.
    """
    if hetero not in SHARPE_HETERO_OPTIONS:
        raise ValueError(f"hetero must be one of {SHARPE_HETERO_OPTIONS}")
    config = dict(block_length=block_length, replicates=replicates, seed=seed, alpha=alpha,
                  periods_per_year=periods_per_year)
    weights = (1., -1., -1., 1.)  # D_het, C_het, D_homo, C_homo
    if hetero == "pooled_half_weight":
        _return_matrix(returns, RQ2_ACCURACY_ARMS)  # validates alignment of all six series
        panel = {"D_hetero": pooled_assignment_returns(returns["D_hetero_AB"], returns["D_hetero_BA"]),
                 "C_hetero": pooled_assignment_returns(returns["C_hetero_AB"], returns["C_hetero_BA"]),
                 "D_homo": returns["D_homo"], "C_homo": returns["C_homo"]}
        names = ("D_hetero", "C_hetero", "D_homo", "C_homo")
        results = {"interaction_pooled_half_weight": sharpe_combination_test(
            _return_matrix(panel, names), weights, **config) | {"columns": list(names)}}
    else:
        results = {}
        for tag in ("AB", "BA"):
            names = (f"D_hetero_{tag}", f"C_hetero_{tag}", "D_homo", "C_homo")
            results[f"interaction_{tag}"] = sharpe_combination_test(
                _return_matrix(returns, names), weights, **config) | {"columns": list(names)}
    return {"estimand": "(SR_D,hetero - SR_C,hetero) - (SR_D,homo - SR_C,homo), annualized",
            "hetero_handling": hetero, "results": results,
            "notes": ["Each replicate recomputes every arm's Sharpe from the resampled aligned daily panel.",
                      "Two Sharpes are never averaged, and AB/BA are never concatenated into a 2T series."]}


def sharpe_block_sensitivity(returns: dict, names, weights, *, block_lengths=(10, 20, 40), **kwargs) -> dict:
    """Run :func:`sharpe_combination_test` for several trading-day block lengths."""
    values = _return_matrix(returns, names)
    results = {}
    for length in block_lengths:
        try:
            results[int(length)] = sharpe_combination_test(values, weights, block_length=int(length), **kwargs)
        except ValueError as error:
            results[int(length)] = {"status": "not_estimable", "reason": str(error)}
    return {"status": "sensitivity", "columns": list(names), "results": results}


# ---------------------------------------------------------------------------
# RQ3 domain specialisation
# ---------------------------------------------------------------------------

def rq3_rule_matched_contrasts(correct: dict, date_ids, *, returns: dict | None = None, rules=("C", "D"),
                               block_length=1, sensitivity_block_lengths=(1, 2, 4),
                               sharpe_block_length=20, replicates=1999, seed=905, alpha=.05,
                               holm_family: tuple[str, ...] | None = None) -> dict:
    """Domain minus generalist within each debate rule (``C_domain - C_generalist`` etc.).

    ``correct`` maps ``{rule}_domain`` / ``{rule}_generalist`` to aligned boolean
    case-level correctness of the *final* decision; ``returns`` optionally maps
    the same names to aligned daily portfolio returns.  Domain views feed one
    final decision per case and are never counted as separate samples.  Holm is
    applied only over an explicitly named, preregistered ``holm_family`` of
    result keys (e.g. ``("C:accuracy", "D:accuracy")``).
    """
    output, pvalues = {}, {}
    for rule in rules:
        domain, generalist = f"{rule}_domain", f"{rule}_generalist"
        if domain not in correct or generalist not in correct:
            raise ValueError(f"Missing correctness for {domain}/{generalist}")
        first = _boolean_vector(domain, correct[domain])
        second = _boolean_vector(generalist, correct[generalist], len(first))
        difference = first.astype(float) - second.astype(float)
        config = dict(replicates=replicates, seed=seed, alpha=alpha)
        entry = {"accuracy": {"domain": float(first.mean()), "generalist": float(second.mean()),
                              "date_block_bootstrap": date_block_bootstrap(difference, date_ids,
                                                                           block_length=block_length, **config),
                              "block_length_sensitivity": block_length_sensitivity(
                                  difference, date_ids, block_lengths=sensitivity_block_lengths, **config),
                              "mcnemar": mcnemar(first, second)}}
        pvalues[f"{rule}:accuracy"] = entry["accuracy"]["date_block_bootstrap"]["pvalue"]
        if returns is not None:
            try:
                entry["sharpe"] = sharpe_combination_test(_return_matrix(returns, (domain, generalist)), (1., -1.),
                                                          block_length=sharpe_block_length, **config)
            except ValueError as error:
                entry["sharpe"] = {"status": "not_estimable", "reason": str(error), "pvalue": None}
            pvalues[f"{rule}:sharpe"] = entry["sharpe"].get("pvalue")
        output[rule] = entry
    result = {"contrasts": {f"{rule}_domain - {rule}_generalist": output[rule] for rule in rules},
              "raw_pvalues": pvalues,
              "notes": ["Domain views are intermediate outputs of one case, not independent samples.",
                        "Architecture contrasts also change call budget; read with the performance-cost table."]}
    if holm_family:
        selected = [pvalues.get(key) for key in holm_family]
        if any(value is None for value in selected):
            raise ValueError("Every Holm family member must have a finite p-value")
        result["holm"] = dict(zip(holm_family, holm_adjust(selected)))
    return result


COST_FIELDS = ("calls", "retries", "prompt_tokens", "completion_tokens", "wall_seconds", "latency_seconds")


def performance_cost_table(usage_records, performance: dict | None = None) -> list[dict]:
    """Per-arm totals and per-case means of compute usage, joined to performance.

    ``usage_records`` holds one dict per (arm, case) with ``arm``, ``case_id`` and
    any of :data:`COST_FIELDS`.  Missing fields are counted as missing, never as
    zero.  ``performance`` optionally maps arm -> {"accuracy": ..., "sharpe": ...}.
    """
    by_arm: dict[str, list[dict]] = {}
    for record in usage_records:
        if "arm" not in record or "case_id" not in record:
            raise ValueError("Each usage record needs arm and case_id")
        by_arm.setdefault(record["arm"], []).append(record)
    rows = []
    for arm in sorted(by_arm):
        records = by_arm[arm]
        cases = {record["case_id"] for record in records}
        if len(cases) != len(records):
            raise ValueError(f"Duplicate case usage rows for arm {arm}")
        row = {"arm": arm, "cases": len(cases)}
        for field in COST_FIELDS:
            values = [float(r[field]) for r in records
                      if isinstance(r.get(field), (int, float)) and math.isfinite(float(r[field]))]
            row[f"{field}_total"] = float(sum(values)) if values else None
            row[f"{field}_per_case_mean"] = float(np.mean(values)) if values else None
            row[f"{field}_per_case_median"] = float(np.median(values)) if values else None
            row[f"{field}_missing_cases"] = len(records) - len(values)
        prompt, completion = row["prompt_tokens_total"], row["completion_tokens_total"]
        row["total_tokens"] = None if prompt is None or completion is None else prompt + completion
        for key, value in (performance or {}).get(arm, {}).items():
            row[key] = value
        rows.append(row)
    return rows


def domain_agreement_distribution(views, *, final_correct=None,
                                  domains=("technical", "fundamental", "sentiment", "macro")) -> dict:
    """4:0 / 3:1 / 2:2 split over cases whose four domain views are all valid Buy/Sell.

    Any non-binary view (abstain, insufficient information, missing) moves the
    case to a separate ``with_abstention`` bucket keyed by the number of valid
    views; such cases are never forced into 2:2.  Counts are per case.  If
    ``final_correct`` (aligned booleans) is given, the final-decision accuracy
    per pattern is attached as an exploratory diagnostic.
    """
    patterns, labels = Counter(), []
    abstentions = Counter()
    for view in views:
        stances = [view.get(domain) for domain in domains]
        valid = [stance for stance in stances if stance in BINARY_DIRECTIONS]
        if len(valid) == len(domains):
            buys = valid.count("Buy")
            majority = max(buys, len(valid) - buys)
            label = f"{majority}:{len(valid) - majority}"
            patterns[label] += 1
        else:
            label = f"valid_{len(valid)}_of_{len(domains)}"
            abstentions[label] += 1
        labels.append(label)
    complete = sum(patterns.values())
    distribution = {key: {"cases": patterns.get(key, 0),
                          "share_of_complete": patterns.get(key, 0) / complete if complete else None}
                    for key in ("4:0", "3:1", "2:2")}
    result = {"cases": len(labels), "complete_binary_cases": complete, "distribution": distribution,
              "with_abstention": dict(sorted(abstentions.items())),
              "note": "Domain views are intermediate outputs of one case; counts are cases, not views."}
    if final_correct is not None:
        correct = _boolean_vector("final_correct", final_correct, len(labels))
        by_label = {}
        for label, value in zip(labels, correct):
            by_label.setdefault(label, []).append(bool(value))
        result["exploratory_accuracy_by_pattern"] = {
            label: {"cases": len(values), "accuracy": sum(values) / len(values)}
            for label, values in sorted(by_label.items())}
    return result


# ---------------------------------------------------------------------------
# Planning-only power / MDE simulation for the accuracy interaction
# ---------------------------------------------------------------------------

def _paired_differences(rng, size, effect, discordance):
    """D-C correctness differences in {-1, 0, 1} with P(+1)-P(-1)=effect, P(+-1)=discordance."""
    probabilities = np.array([(discordance - effect) / 2, 1 - discordance, (discordance + effect) / 2])
    return rng.choice(np.array([-1., 0., 1.]), size=size, p=probabilities)


def simulate_interaction_power(*, n_dates=20, cases_per_date=9, interaction=.10, homo_effect=0.,
                               discordance_rate=.30, assignment_agreement=.5, date_effect_sd=0.,
                               hetero="mean", alpha=.05, replicates=1000, seed=905) -> dict:
    """PLANNING ONLY: Monte Carlo power for the RQ2 accuracy interaction.

    Each case gets a homo D-C difference and AB/BA hetero D-C differences drawn
    with the assumed discordance rate.  ``assignment_agreement`` is the chance
    BA copies AB's difference (1 = duplicate assignment, 0 = independent).
    ``date_effect_sd`` perturbs the hetero effect per date to mimic shared
    market conditions.  The test is a date-cluster-robust t (G-1 df), a cheap
    stand-in for the bootstrap used on real data; the result is an assumption-
    driven design number, never evidence about the study.
    """
    if hetero not in HETERO_OPTIONS:
        raise ValueError(f"hetero must be one of {HETERO_OPTIONS}")
    hetero_effect = homo_effect + interaction
    if not 0 < discordance_rate <= 1 or max(abs(homo_effect), abs(hetero_effect)) + 3 * date_effect_sd > discordance_rate:
        raise ValueError("Effects (plus 3 date SDs) must not exceed the discordance rate")
    if not 0 <= assignment_agreement <= 1 or n_dates < 3 or cases_per_date < 1 or replicates < 1:
        raise ValueError("Invalid planning configuration")
    rng = np.random.default_rng(seed)
    n = n_dates * cases_per_date
    date_index = np.repeat(np.arange(n_dates), cases_per_date)
    critical = float(student_t.ppf(1 - alpha / 2, n_dates - 1))
    rejected, estimates = 0, []
    for _ in range(int(replicates)):
        homo = _paired_differences(rng, n, homo_effect, discordance_rate)
        shifts = rng.normal(0, date_effect_sd, n_dates) if date_effect_sd else np.zeros(n_dates)
        ab = np.empty(n)
        ba = np.empty(n)
        for date in range(n_dates):
            mask = date_index == date
            ab[mask] = _paired_differences(rng, cases_per_date, hetero_effect + shifts[date], discordance_rate)
            fresh = _paired_differences(rng, cases_per_date, hetero_effect + shifts[date], discordance_rate)
            copy = rng.random(cases_per_date) < assignment_agreement
            ba[mask] = np.where(copy, ab[mask], fresh)
        contrast = ((ab + ba) / 2 if hetero == "mean" else ab) - homo
        estimate = contrast.mean()
        residual_sums = np.bincount(date_index, weights=contrast - estimate, minlength=n_dates)
        se = math.sqrt(n_dates / (n_dates - 1) * float(residual_sums @ residual_sums)) / n
        rejected += int(se > 0 and abs(estimate) / se > critical)
        estimates.append(estimate)
    return {"status": "planning_only", "method": "monte_carlo_cluster_robust_t",
            "interaction": interaction, "homo_effect": homo_effect, "discordance_rate": discordance_rate,
            "assignment_agreement": assignment_agreement, "date_effect_sd": date_effect_sd,
            "hetero_handling": hetero if hetero == "mean" else "AB only (one of the separate contrasts)",
            "n_dates": n_dates, "cases_per_date": cases_per_date, "alpha": alpha,
            "replicates": int(replicates), "seed": seed, "estimated_power": rejected / int(replicates),
            "mean_estimate": float(np.mean(estimates)),
            "note": "模擬規劃值，僅反映假設的不一致率與相依結構，不是正式資料的檢定或效果估計。"}


def interaction_mde(*, target_power=.80, interactions=(.05, .10, .15, .20, .25), **kwargs) -> dict:
    """PLANNING ONLY: smallest interaction on a grid reaching ``target_power``."""
    grid = []
    for value in interactions:
        try:
            grid.append(simulate_interaction_power(interaction=value, **kwargs))
        except ValueError as error:
            grid.append({"interaction": value, "status": "not_simulable", "reason": str(error)})
    reached = [row["interaction"] for row in grid if row.get("estimated_power", 0) >= target_power]
    return {"status": "planning_only", "target_power": target_power,
            "minimum_detectable_interaction": min(reached) if reached else None, "grid": grid,
            "note": "Grid-based MDE under stated assumptions only; report the whole grid, not one number."}
