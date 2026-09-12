# v3-0909.5 migration

`v3-0909.5` keeps the source-locked fundamental claim map byte-for-byte while
formatting only the displayed integer before `USD` with digit grouping. For
example, the SEC raw claim `Revenues = 91166000000 USD` appears in the report
as `Revenues = 91,166,000,000 USD`; the unformatted value remains in
`claim_map` and the immutable dataset. ISO dates are not reformatted.

This affects report display and model input. `v3-0909.4` jobs remain readable
and exportable but cannot resume under `v3-0909.5`; use **複製至新版重新執行**
and keep protocol versions separate in statistics.
