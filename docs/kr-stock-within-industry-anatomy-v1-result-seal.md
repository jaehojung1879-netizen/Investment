# kr-stock-within-industry-anatomy-v1 — result seal

**Status: SPENT. `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`.** The formal one-shot execution has completed and cannot be rerun or rescued.
This change only seals it: no historical outcome, statistic, feature, taxonomy, horizon, sample or interpretation rule was recomputed or changed, and the
frozen protocol (`research_specs/kr-stock-within-industry-anatomy-v1.json`, its design note, the harness and the workflow) is byte-identical.

| Item | Value |
|---|---|
| Execution run | 37196246044 (workflow_dispatch on `main`) |
| Execution main SHA | `76c5b48d95806f7e27d3602ac205103d3c0c4ee6` |
| Result artifact | `kr-stock-within-industry-anatomy-v1-results-37196246044`, id 11300998906 |
| Artifact archive digest | `sha256:98b51e1d0fe6746d06dae49aad694ab341ffb12dbf2c4161f98d057bda06da8c` (verified before extraction) |
| Spec SHA-256 | `cfcec648194e25a8914056266443e241528a68352054a10d75cb6889225e5073` |
| Raw input identity | `233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7` |
| Result SHA-256 | `3862c390a52f6f19abaa7849e41620858cd154735136647ee36c958624c2739f` (artifact member `stock-within-industry-anatomy.json`, renamed only) |
| Manifest SHA-256 | `b458ca96c4db70dc6b9ae01d4d9181f238e1a63ffb95e98179e83bb1941cf30b` |
| Execution marker SHA-256 | `81e81c1e8b060bd5c3cf6b83e07523352bbfd48cdb8cbd422e8b12978b96a5b1` (`outcomesReadBeforeThisMarker: 0`) |
| Execution lock | git tags `refs/tags/kr-stock-within-industry-anatomy-v1-execution-lock` and `…-lock-<specSha256>`, both on the execution main SHA |
| Outcome-access counters | 219,600 endpoint reads, 219,600 target and label checks, 1 analysis call, 1 marker write, 1 sealed-reference read |

Committed: the exact result, manifest and marker; the two stock-date panels (`data/kr-stock-within-industry-anatomy-v1/tables/`, hashes in the manifest, kept
because the Actions artifact expires); a provenance record with per-file SHA-256 values and the observed lock refs; and a human-readable report rendered from
the committed result by `scripts/render_kr_stock_within_industry_anatomy_v1_report.py`. Committing the result and marker paths makes `authorize_execution`
refuse any further run, in addition to the git-tag lock that already consumed the study.

The report: `docs/results/kr-stock-within-industry-anatomy-v1-report.md`. It reports all eleven registered features, both sensitivities, both weight lenses,
all three horizons, the outcome-window slices, the market states, the secondary statistics, the five registered questions and the comparison of the sealed
stock − market reading with this study's stock − leave-one-out-industry reading. The underlying membership result remains `DATA_FOUNDATION_INSUFFICIENT_V4`.
