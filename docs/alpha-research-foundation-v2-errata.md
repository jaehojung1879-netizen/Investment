# Errata — `regional-alpha-model-v1` execution status

> Filed as part of `alpha-research-foundation-v2`. This corrects a factual
> error in `alpha-information-inventory-v1` and its companion documents.
> Nothing in this correction changes any production behavior, factor
> weight, CHAMPION, selector, Kelly parameter, or historical ledger entry.

## What was wrong

`alpha-information-inventory-v1.md`, `-research-map.md`, `-gaps.md`,
`-next-hypotheses.md`, `docs/results/alpha-information-inventory-v1.json`,
and `AGENTS.md`'s "Alpha-information-inventory invariants (v2.23)" section
all stated that `regional-alpha-model-v1` had a frozen spec and runnable
code but had **never been executed** — `PENDING_EXECUTION`, "no published
result exists," "has simply never been run." Based on that belief, several
of those documents recommended running it as the highest-priority,
zero-new-data next action.

That was factually wrong.

## What the primary source actually shows

GitHub Actions run
[`35826122755`](https://github.com/jaehojung1879-netizen/Investment/actions/runs/35826122755)
("Regional alpha model v1", job `discovery`, triggered by the push that
opened PR #149 on 2026-09-23, `conclusion: success`) was read directly —
the job log, not a secondhand description — and shows:

1. The workflow ran the frozen study **twice**, per its own design (`Run
   the frozen study twice` step), specifically to verify determinism.
2. Stage -1 loaded source-verified frozen inputs, audited raw filing
   visibility, and constructed the feature matrix **without forward
   labels** first (`constructing feature matrix WITHOUT forward labels`),
   sweeping US and KR feature construction year by year (2013-2026).
3. This produced a frozen manifest of **381,899 rows**, content-hashed as
   `6261031bf59e725ca58342e4f320a8ed62e5d4e797dc6f580c2d372a830543b7`,
   logged identically on both runs (`FROZEN manifest
   6261031b...; 381899 rows; now constructing labels`).
4. Only after that freeze were labels constructed and independent annual
   US/KR models fit — training-row counts logged per year: US 44,456
   (2016) growing to 267,171 (2026); KR 15,294 (2016) growing to 75,743
   (2026).
5. Both runs produced the **byte-identical** final classification:
   ```json
   {"US": "NO_MODEL_EVIDENCE", "KR": "NO_MODEL_EVIDENCE"}
   ```
6. The full report (`study-a/regional-alpha-model-v1-report.{json,md}`)
   was uploaded as a CI artifact named `regional-alpha-model-v1-discovery-only`
   (179,126,687 bytes, SHA-256
   `0d12076f7fd875dfdf25f6c8588e8f54a0d01a5884680b6589504608cf5e85d1`,
   retained until 2026-12-22) — **but was never committed to
   `docs/results/`**. The workflow's own "verify checked-in result" step is
   conditional on that file existing (`if test -f
   docs/results/regional-alpha-model-v1-report.json`) and silently does
   nothing when it does not, which is exactly why the inventory read this
   as "no published result" and, from there, incorrectly inferred
   non-execution rather than under-publication.

An attempt to download the full 179MB artifact for its complete numeric
detail was blocked by this session's own sandbox network policy (the
signed Azure blob-storage URL returned `403` at the proxy). Nothing beyond
what is quoted above from the job log is claimed as verified; no number was
invented to fill in what the artifact would have shown.

## The corrected status

| Field | Corrected value |
|---|---|
| Execution status | `EXECUTED` (2026-09-23, run `35826122755`, twice for determinism) |
| Classification — US | `NO_MODEL_EVIDENCE` |
| Classification — KR | `NO_MODEL_EVIDENCE` |
| Discovery-phase status | `HISTORICAL_DISCOVERY_CLOSED_ON_EXISTING_FEATURE_SET` |
| Re-research | Must **not** be re-run on the same 31-feature matrix — the one-shot historical-discovery budget for both regions is spent |

## How the result should be read

The task that raised this correction was explicit that the closure applies
to a specific, limited feature set, not to "public information in general."
That is the correct reading, and it is restated here plainly: the 31
features in `regional_alpha_features.feature_manifest()` are, by
construction, different representations of exactly three information
families — price/trend/risk (21 features), fundamental level (5), and
fundamental change (4 delta features), plus one region-specific extra field
each. `NO_MODEL_EVIDENCE` on that matrix says an ML re-ranking over THOSE
representations, in THAT construction, found nothing — it says nothing
about investor flow, ownership behavior, accounting-quality ratios beyond
profitability levels, corporate events, or any macro interaction, because
none of those were in the matrix at all. `alpha-research-foundation-v2`'s
own data-foundation work is aimed exactly at that gap, and none of it
re-uses `regional-alpha-model-v1`'s spent discovery budget, because none of
it is the same matrix.

## Documents corrected by this errata

Each carries an inline correction note pointing back here:

- `docs/alpha-information-inventory-v1.md` (top-of-document note, Korean
  summary §다음 모델링 전에 반드시 해결할 데이터 공백/다음 단계 추천,
  and the English Decision Gate §6)
- `docs/alpha-information-inventory-v1-research-map.md` (§1 table row and
  the paragraph following the table)
- `docs/alpha-information-inventory-v1-gaps.md` (§8 closing paragraph)
- `docs/alpha-information-inventory-v1-next-hypotheses.md` (opening note)
- `docs/results/alpha-information-inventory-v1.json`
  (`decisionGateNotes`, `researchHistory.pendingExecution` /
  `researchHistory.concluded`)
- `AGENTS.md` — "Alpha-information-inventory invariants (v2.23)" (two
  bullets corrected in place, with a pointer to this errata) and a new
  "Alpha-research-foundation-v2 invariants (v2.24)" section carrying the
  full correction and its evidence.

No other conclusion in `alpha-information-inventory-v1` or its companions
is affected by this correction — everything else in those documents was
about information that has NOT been used in any study, which this
correction does not touch.
