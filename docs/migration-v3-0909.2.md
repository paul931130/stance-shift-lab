# v3-0909.2 migration

`v3-0909.2` changes the model-only prompt view for bounded local Ollama
contexts. It keeps every original snapshot, report, citation and export item
unchanged, but sends an inference model a compact calibration, all hard
fundamental/technical/macro facts, and four representative direct headlines.
Adjudicators receive an aggregate of mature prior results instead of raw
database rows. The output budget is 512 tokens because the JSON response is
limited to a concise rationale and four risks.

This changes the inference input, so `v3-0909.1` jobs remain readable and
exportable but cannot resume under `v3-0909.2`. Use **複製至新版重新執行** to
start an immutable replacement with a new protocol hash. Do not pool results
from the two protocol versions.
