# KR integrated alpha portfolio v1 — post-outcome concentration audit

**POST-OUTCOME DESCRIPTIVE DIAGNOSTIC ONLY. It diagnoses an already-exposed result; it is not a new confirmatory experiment, a model rescue, an architecture selection, a promotion decision or prospective evidence, and it cannot alter the formal result or any frozen rule.**

Scientific status: `EXPLORATORY_POST_OUTCOME_DESCRIPTIVE_DIAGNOSTIC`. Formal execution run `37374530672` at `33237df6d69e` (spec `eea6128cd552…`). The formal result is not rerun, rewritten or reinterpreted here; the locks were not touched; the primary formal benchmark remains `069500.KS`.

**What this report could and could not do.** The formal result artifact and the 336 MB raw-input snapshot sit on GitHub's Azure blob storage, which the authoring environment cannot reach, and no official KODEX 200 source (Samsung Asset Management, KRX) was reachable either. So every number below comes from frozen, repository-resident inputs and is labelled as a reconstruction or a proxy; every section that needs the artifacts is marked `NOT_RUN_IN_THIS_ENVIRONMENT` and is runnable through the read-only audit workflow added with this report.

## 1. Executive conclusion

* **The ~20.24% passive figure is dominated by the last 20 months.** The frozen benchmark reproduces +20.24% a year over the full window (+493.29% cumulative). Only the first span (2017-2024) is a multi-year regime: it annualizes +6.89%. 2025 alone returned +98.72% and 2026 to the cutoff +75.73%; together they carry 70.2% of the window's log wealth and 85.8% of its terminal gain.
* **Samsung Electronics and SK Hynix became a very large part of the market.** Inside the PIT Top120 their combined market-cap share has a median of 28.5% in the formal window, peaked at 57.2% (2026-07-01) and was 52.6% on 2026-09-01. This is a market-cap proxy, not the KODEX 200 weight.
* **They account for a large share of the recent gain in a broad cap-weighted reference.** In the cap-weighted Top120 reference they contributed 65.4% of the 2025 plus 2026-to-cutoff gain (approximate; monthly proxy weights).
* **The benchmark's internal cross-check raises a question that needs official data.** Over 2017-2024 the frozen benchmark earned +4.53% a year above the committed KS200 price index, against +1.85% for the same-data constituent reference. In every full calendar year 2018-2025 the benchmark's excess over the index sat between +3.87% and +5.25%, including 2025 when the index itself rose +90.67%. Whether that gap is real distribution income or an overstatement of the applied events cannot be settled here; it is classified `BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED`.
* **The statement "Industry was strongly supported" cannot be re-examined here.** It rests on the formal A and D paths and their calendar-year chronology, which this environment could not read or reconstruct. Nothing in the locally computable evidence supports or contradicts narrowing it; the chronology of D versus A, the direct Samsung/SK Hynix exposure of D and the D_EXCLUDE_SAMSUNG_HYNIX sensitivity are the evidence that decides it, and they are `NOT_RUN_IN_THIS_ENVIRONMENT`.

## 2. Is the 20.24% benchmark CAGR misleading without period decomposition?

Frozen benchmark (`069500.KS`, total-return basis). Fixed spans; no breakpoint was optimised. Evidence class: POST_OUTCOME_DIAGNOSTIC_RECONSTRUCTION.

| Span | From → to | Start level | End level | Cumulative | Annualized | Daily steps | Share of log wealth | Share of terminal gain |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A_2017_to_2024 | 2017-01-16 → 2024-12-30 | 24,456.2 | 41,550.1 | +69.90% | +6.89% | 1953 | 29.8% | 14.2% |
| B_2025 | 2024-12-30 → 2025-12-30 | 41,550.1 | 82,567.4 | +98.72% | +98.81% | 242 | 38.6% | 34.0% |
| C_2026_to_cutoff | 2025-12-30 → 2026-09-14 | 82,567.4 | 145,096.1 | +75.73% | n/a | 172 | 31.7% | 51.8% |
| D_full_window | 2017-01-16 → 2026-09-14 | 24,456.2 | 145,096.1 | +493.29% | +20.24% | 2367 | 100.0% | 100.0% |

Annualized is shown only for spans of a full year or more (calendar 2025 between its two year-end sessions counts; 2026 to the cutoff is 0.7 years and is not annualized). Calendar years (frozen benchmark vs the committed KS200 price index):

| Year | Benchmark | KS200 price index |
|---|---:|---:|
| 2017 (from 2017-01-16) | +26.92% | +22.01% |
| 2018 | -15.37% | -19.33% |
| 2019 | +17.31% | +12.13% |
| 2020 | +38.96% | +32.52% |
| 2021 | +5.34% | +1.26% |
| 2022 | -22.27% | -26.15% |
| 2023 | +27.73% | +22.98% |
| 2024 | -7.22% | -11.22% |
| 2025 | +98.72% | +90.67% |
| 2026 (to 2026-09-14) | +75.73% | +73.41% |

A and D strategy decomposition: `NOT_RUN_IN_THIS_ENVIRONMENT` (needs the formal month-end NAV and calendar-year returns).

## 3. Benchmark integrity and official reconciliation

* Series: 3860 sessions, 2011-01-03 to 2026-09-14; registered KR calendar 3860; missing 0, not in calendar 0; non-positive or non-finite levels 0.
* Passive path reproduced from the frozen series: +20.24% a year, +493.29% cumulative over 2017-01-16 → 2026-09-14; matches the ~20.24% quoted for the formal result to four decimals: True. The artifact's own value could not be read, so the exact comparison is not run.
* Daily moves of at least 10% inside the window: 5 (largest +24.17% on 2026-07-31). They are reported, not edited; each should be confirmed against an official source.
* The snapshot stores the benchmark only as a total-return close. Its distribution and split events were applied upstream and are not a separate component, so a from-events reconstruction is impossible from the snapshot; this is a data limitation, not a mismatch (`BENCHMARK_RECONSTRUCTION_MISMATCH` was not triggered).

Tracking cross-check (evidence class POST_OUTCOME_DESCRIPTIVE_PROXY): the benchmark's excess over the committed price index.

| Year | Benchmark | KS200 price index | Benchmark over index | Cap-weighted Top120 reference | Reference over index |
|---|---:|---:|---:|---:|---:|
| 2017 | +26.92% | +22.01% | +4.02% | +24.11% | +1.72% |
| 2018 | -15.37% | -19.33% | +4.91% | -17.22% | +2.61% |
| 2019 | +17.31% | +12.13% | +4.61% | +13.18% | +0.93% |
| 2020 | +38.96% | +32.52% | +4.86% | +36.11% | +2.71% |
| 2021 | +5.34% | +1.26% | +4.03% | +2.55% | +1.28% |
| 2022 | -22.27% | -26.15% | +5.25% | -23.81% | +3.17% |
| 2023 | +27.73% | +22.98% | +3.87% | +22.07% | -0.74% |
| 2024 | -7.22% | -11.22% | +4.50% | -8.44% | +3.13% |
| 2025 | +98.72% | +90.67% | +4.22% | +86.88% | -1.99% |
| 2026 | +75.73% | +73.41% | +1.34% | +65.14% | -4.77% |

2017-2024 as one span: benchmark +69.90%, price index +19.41%, cap-weighted reference +38.19%; the benchmark's annual excess over the index is +4.53% and the reference's is +1.85%. After 2024 the reference differs from the index by composition (the two names), so only the 2017-2024 span is like-for-like.

**External reconciliation: `BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED`.** samsungfund.com, kodex.com and data.krx.co.kr are not reachable from the authoring sandbox (outbound HTTPS is allow-listed); no official value was retrieved, so no number below is an official number. The frozen values to reconcile against Samsung Asset Management / KRX at fixed checkpoints:

| Checkpoint | Session | Level | Year-to-date total return (frozen) |
|---|---|---:|---:|
| 2024-12-30 | 2024-12-30 | 41,550.1 | -7.22% |
| 2025-12-30 | 2025-12-30 | 82,567.4 | +98.72% |
| 2026-01-30 | 2026-01-30 | 105,039.0 | +27.22% |
| 2026-04-30 | 2026-04-30 | 136,961.0 | +65.88% |
| 2026-09-14 | 2026-09-14 | 145,096.1 | +75.73% |

No official number is quoted anywhere in this report. the frozen series is an as-traded-close total return with forward-accumulated Yahoo distributions: compare with Samsung AM's DISTRIBUTION-REINVESTED market-price or NAV return, never with a price-only return or a different date window

## 4. Samsung Electronics + SK Hynix concentration (proxy)

Share of the total market capitalisation of the PIT Top120 (monthly snapshots; not free-float; not the KOSPI 200 weight).

| Snapshot on or before | Samsung Electronics | SK Hynix | Combined |
|---|---:|---:|---:|
| 2016-12-31 (2016-12-01) | 22.9% | 3.0% | 25.9% |
| 2017-12-31 (2017-12-01) | 23.9% | 4.1% | 28.0% |
| 2018-12-31 (2018-12-03) | 23.0% | 4.2% | 27.2% |
| 2019-12-31 (2019-12-02) | 25.2% | 4.9% | 30.1% |
| 2020-12-31 (2020-12-01) | 26.0% | 4.7% | 30.7% |
| 2021-12-31 (2021-12-01) | 24.4% | 4.7% | 29.1% |
| 2022-12-31 (2022-12-01) | 22.5% | 3.7% | 26.2% |
| 2023-12-31 (2023-12-01) | 25.1% | 5.6% | 30.7% |
| 2024-12-31 (2024-12-02) | 18.5% | 6.7% | 25.2% |
| 2025-12-31 (2025-12-01) | 20.9% | 13.7% | 34.6% |
| 2026-09-14 (2026-09-01) | 29.0% | 23.5% | 52.6% |

Formal window: maximum 57.2% (2026-07-01), median 28.5%, minimum 24.7% (2019-01-02). Snapshots above each descriptive round number:

| Threshold | Snapshots above | First | Last | Runs |
|---:|---:|---|---|---|
| 30% | 42 of 116 | 2017-11-01 | 2026-09-01 | 2022-01-03→2022-01-03; 2023-11-01→2024-09-02; 2025-10-01→2026-09-01 |
| 40% | 8 of 116 | 2026-02-02 | 2026-09-01 | 2026-02-02→2026-09-01 |
| 50% | 4 of 116 | 2026-06-01 | 2026-09-01 | 2026-06-01→2026-09-01 |
| 60% | 0 of 116 | — | — | none |

## 5. Benchmark return contribution (approximate, proxy weights)

Label: `APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS`. Contribution of Samsung Electronics and SK Hynix to the return of the CAP-WEIGHTED TOP120 reference (monthly market-cap weights, buy-and-hold between snapshots, chained daily as nav_{t-1} * w_{t-1} * r_t). It is NOT the contribution to the KODEX 200 benchmark: the weights are proxy weights and the reference is a different portfolio. Official PIT KODEX 200 / KOSPI 200 constituent weights were unreachable.

| Span | Reference gain | Samsung Electronics | SK Hynix | Combined | Residual | Combined share of gain |
|---|---:|---:|---:|---:|---:|---:|
| A_2017_to_2024 | +0.382 | +0.174 | +0.085 | +0.259 | +0.123 | 67.8% |
| B_2025 | +1.201 | +0.336 | +0.290 | +0.626 | +0.575 | 52.1% |
| C_2026_to_cutoff | +1.682 | +0.637 | +0.621 | +1.258 | +0.424 | 74.8% |
| D_full_window | +3.265 | +1.147 | +0.996 | +2.143 | +1.122 | 65.6% |

Contributions are in units of the reference's NAV (1.0 at the window start). Same-data reference portfolios (descriptive lenses, not the benchmark):

| Reference | Full window | Annualized | 2017-2024 | 2025 | 2026 to cutoff |
|---|---:|---:|---:|---:|---:|
| REF_TOP120_CAP_WEIGHTED | +326.48% | +16.20% | +38.19% | +86.88% | +65.14% |
| REF_TOP120_CAP_WEIGHTED_EX_SAMSUNG_HYNIX | +131.83% | +9.09% | +17.05% | +56.42% | +26.62% |
| REF_TOP120_EQUAL_WEIGHT | +196.75% | +11.92% | +35.01% | +67.44% | +31.27% |
| Frozen benchmark (069500.KS TR) | +493.29% | +20.24% | +69.90% | +98.72% | +75.73% |
| KS200 price index | +294.83% | +15.28% | +19.41% | +90.67% | +73.41% |

Removing the two names leaves a broad Korean large-cap cross-section that returned much less in 2025 and in 2026 to the cutoff than the cap-weighted reference (+56.42% vs +86.88% and +26.62% vs +65.14%); the recent regime is, in this lens, a concentration phenomenon in these two securities as much as a market-wide one. 
This is a description of the reference portfolios, not a statement about what the investor's passive alternative should be: the formal benchmark stays `069500.KS`, concentration included.

## 6. A vs D chronology

`NOT_RUN_IN_THIS_ENVIRONMENT`: `strategyPeriodDecomposition`, `dMinusAChronology`. Not computed, not estimated, not inferred from the proxies above.

## 7. D holdings and industry attribution

`NOT_RUN_IN_THIS_ENVIRONMENT`: `dPathReconstruction`, `dHoldingsAndIndustryAttribution`. Not computed, not estimated, not inferred from the proxies above.

## 8. Samsung Electronics + SK Hynix direct exposure in D

`NOT_RUN_IN_THIS_ENVIRONMENT`: `namedSecurityExposureInD`. Not computed, not estimated, not inferred from the proxies above.

## 9. D_EXCLUDE_SAMSUNG_HYNIX sensitivity

`NOT_RUN_IN_THIS_ENVIRONMENT`: `dExcludeSamsungHynixSensitivity`. Not computed, not estimated, not inferred from the proxies above.

Why: needs the exact formal result artifact and/or the 336 MB raw-input snapshot, both stored on Azure blob storage that the authoring sandbox cannot reach (CONNECT 403); the KRX daily market-value files in that snapshot are not stored in git.

How to run them: dispatch .github/workflows/kr-integrated-alpha-portfolio-v1-postoutcome-audit.yml (workflow_dispatch, read-only, never touches a lock) which downloads the two exact artifacts, verifies their identities, reproduces the formal A and D paths and only then attributes them. The audit-only reconstruction must reproduce the formal A and D metrics and month-end NAVs (tolerance 1e-9) before any attribution is trusted; otherwise it stops with `D_PATH_RECONSTRUCTION_MISMATCH` and reports the first divergence. The only strategy counterfactual is `D_EXCLUDE_SAMSUNG_HYNIX` (the two tickers removed after scoring and before selection, every other frozen rule unchanged); no other exclusion set is run. Also run in that workflow: `formalResultExtraction` (the formal values copied verbatim as FORMAL_REPORTED_RESULT).

## 10. Existing sealed mega-cap anatomy evidence (read, not rerun)

Industry anatomy, CAP_WEIGHTED H126 (IC mean / tercile spread pp):

| Feature | FULL | Leave largest constituent out | Exclude Samsung + SK Hynix |
|---|---:|---:|---:|
| BREADTH_ABOVE_MA_126 | +0.059 / +3.2 | +0.044 / +0.1 | +0.042 / +3.2 |
| REL_MOM_126 | +0.066 / +5.4 | +0.071 / +0.1 | +0.071 / +5.4 |

Stock within-industry anatomy, CAP_WEIGHTED H126 (mean rank correlation):

| Feature | FULL | Exclude Samsung + SK Hynix |
|---|---:|---:|
| bookToMarketProxy | +0.086 | +0.087 |
| earningsYieldProxy | +0.073 | +0.069 |
| negativeDownsideVol126 | +0.062 | +0.062 |
| relative126 | +0.028 | +0.027 |

* **A — signal association.** In the sealed readings the REL_MOM_126 and BREADTH_ABOVE_MA_126 industry associations keep their sign when only the two names are removed; leaving the single largest constituent out of each industry shrinks the REL_MOM_126 tercile spread to near zero. The four stock features keep their sign and most of their size when the two names are removed.
* **B — implemented portfolio.** NOT ANSWERED by these reports. They measure rank associations over the whole cross-section; they say nothing about whether a five-name book held the two names, how large their weights were, or what they earned. That is what the D reconstruction and the D_EXCLUDE_SAMSUNG_HYNIX sensitivity are for.

## 11. What is actually established

* **Q1. Is the formal passive CAGR a normal long-run Korean equity return, or heavily elevated by the 2025-2026 endpoint regime?** `SUPPORTED_BY_AUDIT` — On the frozen benchmark the last two spans (2025 and 2026 to the cutoff) carry 70.2% of the window's log wealth; 2017-2024 alone annualizes 6.89% against 20.24% for the full window.
* **Q2. Is the frozen KODEX 200 benchmark internally correct?** `PARTIALLY_SUPPORTED` — Hash-verified, complete against the registered calendar, no duplicate or non-positive level, and it reproduces the quoted passive CAGR. But its excess over the committed price index is 4.53% a year over 2017-2024, against 1.85% for a same-data constituent total-return reference over the same span; the distribution events behind it are not stored, so the gap cannot be decomposed from the snapshot.
* **Q4. How much benchmark concentration is explained by Samsung Electronics and SK Hynix?** `PARTIALLY_SUPPORTED` — Inside the PIT Top120 their combined market-cap share has a median of 28.5%, a maximum of 57.2% (2026-07-01) and a latest value of 52.6% (2026-09-01). This is a proxy for, not a measurement of, the KODEX 200 weight.
* **Q5. How much of the benchmark's 2025-2026 return is attributable to them?** `PARTIALLY_SUPPORTED` — In the cap-weighted Top120 reference they contributed 65.4% of its combined 2025 and 2026-to-cutoff gain (APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS). Not exact for KODEX 200.

## 12. What remains uncertain

* **Q3. Does it reconcile with authoritative external KODEX 200 evidence?** `UNRESOLVED_DATA_LIMITATION` — No official source was reachable. The frozen values to reconcile are recorded for five fixed checkpoints.
* **Q6. How much of D's 2025-2026 performance comes from Samsung Electronics and SK Hynix directly?** `UNRESOLVED_DATA_LIMITATION` — Needs the formal result artifact and the raw snapshot; not run in this environment.
* **Q7. How much comes from the broader industry exposure selected by the Industry layer?** `UNRESOLVED_DATA_LIMITATION` — Needs the formal result artifact and the raw snapshot; not run in this environment.
* **Q8. Did Industry help persistently over 2017-2024, or mostly in the recent industry-led regime?** `UNRESOLVED_DATA_LIMITATION` — Needs the formal result artifact and the raw snapshot; not run in this environment.
* **Q9. Does D_EXCLUDE_SAMSUNG_HYNIX materially change the descriptive result?** `UNRESOLVED_DATA_LIMITATION` — Needs the formal result artifact and the raw snapshot; not run in this environment.
* **Q10. Does any benchmark or data-integrity issue require distrusting the formal economic comparison?** `UNRESOLVED_DATA_LIMITATION` — The internal cross-check flags an unexplained excess of the frozen benchmark over both the price index and a same-data reference. If it were an error it would overstate the passive path and therefore understate every architecture's excess; its size and direction cannot be settled without the official distribution history.

## 13. Consequence for the next research step

1. Dispatch the read-only audit workflow once, so the A/D reconstruction, attribution and the single registered sensitivity are computed against the exact artifacts; do not rerun `kr-integrated-alpha-portfolio-v1` (its lock is spent).
2. Obtain Samsung Asset Management's KODEX 200 distribution-reinvested return and KRX's KOSPI 200 total-return index at the five checkpoints and decompose any gap with the listed explanations. Until then the passive path carries an unresolved question.
3. Any narrowing of the Industry conclusion is decided by the D-versus-A chronology and the exposure tables above once they exist, not before. The prospective receipts remain the only route to evidence.

*This is a post-outcome descriptive diagnostic. It does not change the formal result, any frozen rule or any decision, and it is not prospective evidence.*
