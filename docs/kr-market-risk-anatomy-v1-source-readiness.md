# kr-market-risk-anatomy-v1 — source inventory and readiness (outcome-free)

**Decision: `DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY`.** Scientific label: `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`. Computed from observation DATES and metadata only: no price, rate, return, drawdown, episode or future label was parsed or computed (counters all zero).

Blockers: `PRIMARY_REFERENCE_NOT_SELECTED`. 2008 covered by a selected primary reference: **False**. Snapshot acquired on 2026-10-04.

## Primary reference candidates (frozen rule: first KOSPI 200 route that passes every test; the composite only if none does)

| candidate | family | first | last | stale days | invalid-row share | 2007-2009 coverage | 2019H2-2020 coverage | longest missing run | eligible | reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| KRX_OPENAPI_KOSPI200 | - | - | - | - | - | - | - | - | no | service history starts 2010-01-04 (docs/kr-industry-membership-foundation-v1-openapi.md), so it cannot cover 2007-2009; the KRX data portal answered LOGOUT/400 from Actions (AGENTS.md workflow hygiene) |
| YAHOO_KS200 | KOSPI200 | 2026-10-02 | 2026-10-02 | 2 (limit 10) | 0.0000 (limit 0.005) | 0.00% | 0.00% | 5116 | no | HISTORY_STARTS_AFTER_2005-12-31; COVERAGE_BELOW_0.99_IN_GFC_2007_2009; COVERAGE_BELOW_0.99_IN_COVID_2019H2_2020; FULL_RANGE_COVERAGE_BELOW_THRESHOLD; MISSING_RUN_TOO_LONG |
| FDR_KS200 | KOSPI200 | 1990-01-03 | 2026-09-17 | 17 (limit 10) | 0.0000 (limit 0.005) | 100.00% | 100.00% | 0 | no | STALE_LAST_DATE |
| YAHOO_KS11 | KOSPI_COMPOSITE | 1996-12-11 | 2026-10-02 | 2 (limit 10) | 0.0199 (limit 0.005) | 99.87% | 100.00% | 1 | no | TOO_MANY_INVALID_ROWS |
| YAHOO_069500 | KODEX200_ETF | 2007-01-29 | 2026-10-02 | 2 (limit 10) | 0.1190 (limit 0.005) | 25.17% | 99.46% | 540 | no | ROBUSTNESS_REFERENCE_ONLY_NEVER_PRIMARY |

No candidate was selected, nothing was spliced, nothing was substituted and no frozen limit was changed after the metadata was seen.

## Source inventory (acquired snapshot)

| source | status | first | last | valid rows | dropped | identity as recorded | identity by registered function | vintage class |
|---|---|---|---|---:|---:|---|---|---|
| FDR_KS200 | ACQUIRED | 1990-01-03 | 2026-09-17 | 9470 | 0 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| FRED_BAMLC0A0CM | ACQUIRED | 2023-10-03 | 2026-10-01 | 785 | 9 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| FRED_BAMLH0A0HYM2 | ACQUIRED | 2023-10-03 | 2026-10-01 | 786 | 8 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| FRED_DEXKOUS | ACQUIRED | 1990-01-03 | 2026-09-25 | 9184 | 401 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| FRED_DFF | ACQUIRED | 1990-01-01 | 2026-10-01 | 13423 | 0 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| FRED_DGS10 | ACQUIRED | 1990-01-02 | 2026-10-01 | 9194 | 395 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| FRED_DGS2 | ACQUIRED | 1990-01-02 | 2026-10-01 | 9194 | 395 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| FRED_DGS3MO | ACQUIRED | 1990-01-02 | 2026-10-01 | 9194 | 395 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| FRED_VIXCLS | ACQUIRED | 1990-01-02 | 2026-10-01 | 9286 | 302 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| YAHOO_069500 | ACQUIRED | 2007-01-29 | 2026-10-02 | 4279 | 578 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| YAHOO_KRWX | ACQUIRED | 2003-12-01 | 2026-10-04 | 5925 | 36 | False | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| YAHOO_KS11 | ACQUIRED | 1996-12-11 | 2026-10-02 | 7337 | 149 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| YAHOO_KS200 | ACQUIRED | 2026-10-02 | 2026-10-02 | 1 | 0 | True | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |
| YAHOO_VIX | ACQUIRED | 1990-01-02 | 2026-10-02 | 9258 | 331 | False | True | MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY |

## Family coverage in the core windows (known, non-stale observations on the cadence grid; dates only)

| family / window | feature | coverage |
|---|---|---:|
| (not computed: the gates stop at the unselected primary reference) | - | - |

## Role sources

VIX -> `FRED_VIXCLS`; USD/KRW -> `FRED_DEXKOUS` (primary routes pass the weekly known-coverage gate in 2007-2009; secondaries are never spliced).

## Excluded: revised history or not built

| input | class | reason |
|---|---|---|
| ECOS_BASE_RATE | REVISED_HISTORY | item and cycle unresolved (AMBIGUOUS_SOURCE) and ECOS is REVISED_HISTORY |
| ECOS_KTB_3Y | REVISED_HISTORY | ECOS is REVISED_HISTORY; a KR term spread also lacks a comparable validated short leg |
| ECOS_LEADING_INDEX | REVISED_HISTORY | ECOS is REVISED_HISTORY by the repository contract; not a primary historical predictor |
| EXCESS_BOND_PREMIUM | NOT_AVAILABLE | a modern revised series; no historical vintage semantics are defensible, so it is never called PIT exact and is not acquired |
| FRED_ANFCI | REVISED_HISTORY | adjusted index re-estimated with every release (revised history) |
| FRED_NFCI | REVISED_HISTORY | weekly index re-estimated with every release (revised history); no retained vintage evidence in this repository |
| FRED_OECD_KR_10Y | REVISED_HISTORY | monthly OECD series; observation date is not publication date; revised history |
| FRED_OECD_KR_3M | REVISED_HISTORY | monthly OECD interbank rate, not a Treasury bill yield; revised history |
| KR_TERM_SPREAD | NOT_AVAILABLE | needs exactly comparable KR long and short rate definitions; the only candidates are ECOS or OECD (revised history) |
| NEAR_TERM_FORWARD_SPREAD | NOT_AVAILABLE | exact source and construction (forward rate from the fitted Treasury curve) are not verified in this repository |

## EXTENDED_KR_INTERNALS (not part of the decision)

PIT Top120 signal dates: 610 (2015-01-02 to 2026-09-11); raw-input artifact kr-model-raw-inputs-36844599518 (id 11157875265). Status: structurally ready; value coverage is measured at execution; an internals statistic is missing whenever any PIT member lacks its input.

