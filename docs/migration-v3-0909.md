# v3-0909.1 migration

`v3-0909.1` is a new immutable protocol. Existing jobs stay readable, exportable, and recoverable as audit records, but cannot resume under the new engine. Use **複製至新版重新執行** to create a new job; the new job receives a new protocol hash and must not be pooled with the old result.

## Protocol fields

| Field | Type | Default | Purpose | Fingerprint |
| --- | --- | --- | --- | --- |
| `model` | string | `ollama/qwen3:14b` | Research model shared by A/B/C/D | Yes |
| `allow_small_model` | bool | `false` | Explicitly permits a sub-14B smoke test only | Yes |
| `voting_temperature` | float | `0.8` | Temperature for B self-consistency calls | Yes |
| `confidence_floor` | float or null | `null` | Optional Gatekeeper confidence threshold | Yes |
| `volatility_ceiling` | float | `0.80` | Annual-volatility risk threshold | Yes |
| `citation_pass_floor` | float | `0.80` | Minimum valid-citation share | Yes |
| `news_relevance_floor` | float | `0.35` | Minimum Alpha Vantage ticker relevance | Yes |
| `target_context_priority` | bool | `true` | Reserve sentiment slots for direct target evidence | Yes |
| `switch_isolation` | bool | `true` | Hide prior debate turns in D round 2 | Yes |
| `hold_band_sigma` | float | `0.5` | Per-asset neutral band width | Yes |
| `action_source` | `model` or `derived` | `derived` | Candidate action source | Yes |
| `spread_window` | integer | `20` | Rolling median Corwin–Schultz window | Yes |

The job configuration also records an explicit `quality_overrides.allow_low_quality_sentiment` value when a researcher intentionally runs a low-relevance news sensitivity case. It is visible in the export manifest.

## Decision fields

1. `model_action` is the action word emitted by the model.
2. `derived_action` is computed from `expected_return_pct` against the frozen per-case `hold_band_pct`.
3. `candidate_action` is the one selected by `action_source` before Gatekeeper checks.
4. `action` is the final Gatekeeper decision.

The main analysis uses `decision_layer=candidate`, `horizon=60`, `cost_model=corwin_schultz`, `portfolio_basis=all`, `action_source=derived`, and `hold_band_sigma=0.5`. Gated rows and active-sleeve returns are sensitivity outputs, not replacements for the mechanism estimate.

## Data, backtest, and storage

Alpha Vantage queries relevance-sorted news, stores the ticker relevance score, and drops unscored or low-score evidence. FNSPID rows are per-ticker source evidence and receive relevance `1.0`. The interface blocks a new job when fewer than half of eligible headlines mention the target ticker or company name, unless the researcher intentionally records the quality override.

The backtest enters at the next session open and exits at the horizon session open. Candidate and gated actions are both evaluated. A short that reaches zero equity remains a complete, flagged `-100%` result. Hold is reported through coverage, conditional accuracy, whether the realized move stayed in the hold band, and opportunity cost.

SQLite now has a narrow `case_results` table:

```text
job_id, protocol_hash, ticker, analysis_date, group, horizon, cost_model,
decision_layer, maturity_date, action, correct, net_return, degraded, created_at
```

On startup, `Store.backfill_case_results()` idempotently indexes existing completed jobs that are not yet in this table. Long-term memory reads this index rather than deserializing every historical job state.

## Pilot gate

Before expanding the research panel, use `/api/studies/{protocol_hash}/pilot`. It blocks a pilot with excessive Hold use, indistinguishable arms, degenerate B voting, collapsed point forecasts, poor out-of-band directional accuracy, or a frequent mismatch between model prose action and its numerical forecast. `/api/studies/{protocol_hash}/hold-band` re-evaluates stored forecasts at sigma 0, 0.25, 0.5, and 1.0 without another model call.
