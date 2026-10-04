# kr-industry-opportunity-anatomy-v1 — result seal

**Status: SPENT. `EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY`.** The formal one-shot execution has completed and cannot be rerun or rescued.
This change only seals it: no historical outcome, statistic, feature, taxonomy, horizon or benchmark was recomputed or changed, and the frozen protocol
(`research_specs/kr-industry-opportunity-anatomy-v1.json`, its design note, the harness and the workflow) is byte-identical.

| Item | Value |
|---|---|
| Execution run | 37182657697 (workflow_dispatch on `main`, attempt 1, conclusion success) |
| Execution main SHA | `f830b92efabab6011f9190293f2e060e9b4fe70b` |
| Result artifact | `kr-industry-opportunity-anatomy-v1-results-37182657697`, id 11295658265 |
| Artifact archive digest | `sha256:ee336dc4ff51cbef21f3f8adbb780c5987e93525d677cdc7bdb5a7dd5400f4ba` (verified before extraction) |
| Spec SHA-256 | `98278ce5724b27dd19d253eab6cb1e7854ea432a62098441cdad46d067609f55` |
| Raw input identity | `233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7` |
| Result SHA-256 | `71a960e3c19ce443d058508c4ec66576e3e5fcbd7a45dc851cf8b832bff62a08` (artifact member `industry-anatomy.json`, renamed only) |
| Manifest SHA-256 | `b8814d43f2e592fea0db7b7e4e7d77485f04881140dc46a197610086383621df` |
| Execution marker SHA-256 | `414911b0ebb340332bbfe0340428f40959bc3fbc73b23cb2c2f92a30390f3bfb` (`outcomesReadBeforeThisMarker: 0`) |
| Execution lock | git tags `refs/tags/kr-industry-opportunity-anatomy-v1-execution-lock` and `…-lock-<specSha256>`, both on the execution main SHA |
| Outcome-access counters | 219,600 endpoint reads, 219,600 target and label checks, 1 analysis call, 1 marker write |

Committed: the exact result, manifest and marker; the three industry-date panels (`data/kr-industry-opportunity-anatomy-v1/tables/`, hashes in the
manifest, kept because the Actions artifact expires 2027-01-02); a provenance record with per-file SHA-256 values and the observed lock refs; and a
human-readable report rendered from the committed result by `scripts/render_kr_industry_anatomy_v1_report.py`. Committing the result and marker paths
makes `authorize_execution` refuse any further run, in addition to the git-tag lock that already consumed the study.

The report: `docs/results/kr-industry-opportunity-anatomy-v1-report.md`. The underlying membership result remains `DATA_FOUNDATION_INSUFFICIENT_V4`.
