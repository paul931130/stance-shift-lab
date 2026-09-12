# v3-0909.4 migration

`v3-0909.4` makes the current fundamental domain a **source-locked SEC
extractor**. The frozen input only has point-in-time XBRL fields, so the system
lists every cited claim exactly and states the missing comparison context rather
than asking a language model to infer strength, loss, growth or price impact.
The other three research domains and all A/B/C/D decisions still use the chosen
model. The report records `mode: source_locked` and an input hash for the
fundamental domain.

This changes report construction. `v3-0909.3` jobs remain readable and
exportable but cannot resume under `v3-0909.4`; use **複製至新版重新執行** and
do not pool protocol versions in statistics.
