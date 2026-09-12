# v3-0909.3 migration

`v3-0909.3` rejects a model output that turns a point-in-time SEC XBRL field
into an unsupported judgement. `NetIncomeLoss` is a taxonomy field, not a
statement that the company made a loss; raw revenue, asset, liability and
cash-flow values do not establish strength, weakness, profitability, growth or
financial pressure without a supplied comparison. The correction is applied to
both the fundamental research summary and a decision that cites fundamental
facts. A rejected output receives one audited retry; if it remains invalid,
the research domain uses a clearly marked source extract instead of a rewritten
claim.

Because this changes report-admission rules, `v3-0909.2` jobs remain readable
and exportable but cannot resume under `v3-0909.3`. Use **複製至新版重新執行**
to start an immutable replacement and do not pool the versions in statistics.
