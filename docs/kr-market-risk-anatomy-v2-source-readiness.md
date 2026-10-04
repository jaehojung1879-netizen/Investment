# kr-market-risk-anatomy-v2 — source readiness (outcome-free)

**Decision: `READY_FOR_MARKET_RISK_ANATOMY_V2_EXECUTION`.** Scientific label: `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`. Computed from observation DATES, the XKRX session calendar and metadata only: no price, rate, return, drawdown, episode or future label was parsed or computed (counters all zero). No new external acquisition occurred: the inputs are the exact immutable bytes retained by `kr-market-risk-anatomy-v1`, which stays `DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY` and unchanged.

Blockers: none. Snapshot acquired on 2026-10-04.

## Selected primary reference: `FDR_KS200` (KOSPI200, PRICE_INDEX_LEVEL)

- Identity: vendor `FINANCEDATAREADER`, symbol `KS200`, host `FinanceDataReader 0.9.110`, fetched 2026-10-04T16:38:34.032270+00:00; identity check by the registered function: True.
- Retained bytes (sha256): `normalized.csv` `729a94b81dd45d1c5d1ab2ff692ec249bd5c9c4f24598d648d7f88010f193478`, `raw_fdr.csv` `49731bdbdfcf9fda103f9d5b17f6e21a790b3748b004b9eb6f4073941bf5aadf`.
- Vintage class: `MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY` (unrevised market observation, approximate availability; never PIT_EXACT). Spliced: **False**.
- First / last usable date: 1990-01-03 / 2026-09-17. **Frozen analysis end: 2026-09-17** (the source's own last completed XKRX session; nothing forward-filled or synthesized).
- Session accounting over 2006-01-01 to 2026-09-17: expected XKRX sessions 5108, valid 5108, missing (no vendor row) 0, invalid expected-session rows 0, bad-session share 0.000000 (limit 0.005).
- Reported separately and NOT counted against the source: non-session vendor rows 0, surplus duplicate raw rows 0, duplicate dates in the valid series 0.
- Coverage: 2007-2009 100.00%; 2019H2-2020 100.00%; full range 100.00%; longest missing run 0.
- Live operational freshness (INFORMATIONAL, a separate future deployment question, never a historical gate): stale 17 days against a 10-day live limit -> meets live freshness: False; live-ready: **False**.

## Candidates (frozen v2 rule: first KOSPI 200 route that passes every test; the composite only if none does)

| candidate | family | first | last | analysis end | expected sessions | missing | invalid | non-session rows | dup raw | bad share | 2007-09 | 2019H2-20 | eligible | v2 reasons | v1 reasons |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| KRX_OPENAPI_KOSPI200 | - | - | - | - | - | - | - | - | - | - | - | - | no | DOCUMENTED_BLOCKER: service history starts 2010-01-04 (docs/kr-industry-membership-foundation-v1-openapi.md), so it cannot cover 2007-2009; the KRX data portal answered LOGOUT/400 from Actions (AGENTS.md workflow hygiene) | DOCUMENTED_BLOCKER: service history starts 2010-01-04 (docs/kr-industry-membership-foundation-v1-openapi.md), so it cannot cover 2007-2009; the KRX data portal answered LOGOUT/400 from Actions (AGENTS.md workflow hygiene) |
| FDR_KS200 | KOSPI200 | 1990-01-03 | 2026-09-17 | 2026-09-17 | 5108 | 0 | 0 | 0 | 0 | 0.000000 | 100.00% | 100.00% | yes | - | STALE_LAST_DATE |
| YAHOO_KS200 | KOSPI200 | 2026-10-02 | 2026-10-02 | 2026-10-02 | 5117 | 5116 | 0 | 0 | 0 | 0.999805 | 0.00% | 0.00% | no | HISTORY_STARTS_AFTER_2005-12-31; TOO_MANY_BAD_EXPECTED_SESSIONS; COVERAGE_BELOW_0.99_IN_GFC_2007_2009; COVERAGE_BELOW_0.99_IN_COVID_2019H2_2020; FULL_RANGE_COVERAGE_BELOW_THRESHOLD; MISSING_RUN_TOO_LONG | HISTORY_STARTS_AFTER_2005-12-31; COVERAGE_BELOW_0.99_IN_GFC_2007_2009; COVERAGE_BELOW_0.99_IN_COVID_2019H2_2020; FULL_RANGE_COVERAGE_BELOW_THRESHOLD; MISSING_RUN_TOO_LONG |

No candidate was selected on outcomes, nothing was spliced, nothing was substituted, and no coverage, continuity or identity threshold was changed from v1.

## Gates

| gate | pass | detail |
|---|---|---|
| FAST_COVID_2019H2_2020 | True | coverage=1.0, firstSessionWithFullFeatureWarmup=1990-11-10 |
| FAST_GFC_2007_2009 | True | coverage=1.0, firstSessionWithFullFeatureWarmup=1990-11-10 |
| PRIMARY_REFERENCE_SELECTED | True | detail=PRIMARY_REFERENCE_SELECTED |
| REFERENCE_COVID_2019H2_2020 | True | coverage=1.0 |
| REFERENCE_GFC_2007_2009 | True | coverage=1.0 |
| SLOW_COVID_2019H2_2020 | True | bestCoverage=1.0 |
| SLOW_GFC_2007_2009 | True | bestCoverage=1.0 |
| TRANSITION_COVID_2019H2_2020 | True | bestCoverage=1.0 |
| TRANSITION_GFC_2007_2009 | True | bestCoverage=1.0 |

## Family coverage in the core windows (known, non-stale observations on the cadence grid; dates only)

| family / window | feature | coverage |
|---|---|---:|
| SLOW_COVID_2019H2_2020 | slow_fed_funds_change_126 | 100.00% |
| SLOW_COVID_2019H2_2020 | slow_fed_funds_level | 100.00% |
| SLOW_COVID_2019H2_2020 | slow_inversion_duration_10y3m | 100.00% |
| SLOW_COVID_2019H2_2020 | slow_resteepening_flag_10y3m | 100.00% |
| SLOW_COVID_2019H2_2020 | slow_us_10y2y_flatness | 100.00% |
| SLOW_COVID_2019H2_2020 | slow_us_10y3m_flatness | 100.00% |
| SLOW_GFC_2007_2009 | slow_fed_funds_change_126 | 100.00% |
| SLOW_GFC_2007_2009 | slow_fed_funds_level | 100.00% |
| SLOW_GFC_2007_2009 | slow_inversion_duration_10y3m | 100.00% |
| SLOW_GFC_2007_2009 | slow_resteepening_flag_10y3m | 100.00% |
| SLOW_GFC_2007_2009 | slow_us_10y2y_flatness | 100.00% |
| SLOW_GFC_2007_2009 | slow_us_10y3m_flatness | 100.00% |
| TRANSITION_COVID_2019H2_2020 | trans_hy_oas_change_21 | 0.00% |
| TRANSITION_COVID_2019H2_2020 | trans_hy_oas_change_63 | 0.00% |
| TRANSITION_COVID_2019H2_2020 | trans_hy_oas_level | 0.00% |
| TRANSITION_COVID_2019H2_2020 | trans_ig_oas_change_63 | 0.00% |
| TRANSITION_COVID_2019H2_2020 | trans_ig_oas_level | 0.00% |
| TRANSITION_COVID_2019H2_2020 | trans_usdkrw_change_63 | 100.00% |
| TRANSITION_COVID_2019H2_2020 | trans_usdkrw_realized_vol_21 | 100.00% |
| TRANSITION_COVID_2019H2_2020 | trans_vix_change_21 | 100.00% |
| TRANSITION_COVID_2019H2_2020 | trans_vix_change_63 | 100.00% |
| TRANSITION_COVID_2019H2_2020 | trans_vix_level | 100.00% |
| TRANSITION_GFC_2007_2009 | trans_hy_oas_change_21 | 0.00% |
| TRANSITION_GFC_2007_2009 | trans_hy_oas_change_63 | 0.00% |
| TRANSITION_GFC_2007_2009 | trans_hy_oas_level | 0.00% |
| TRANSITION_GFC_2007_2009 | trans_ig_oas_change_63 | 0.00% |
| TRANSITION_GFC_2007_2009 | trans_ig_oas_level | 0.00% |
| TRANSITION_GFC_2007_2009 | trans_usdkrw_change_63 | 100.00% |
| TRANSITION_GFC_2007_2009 | trans_usdkrw_realized_vol_21 | 100.00% |
| TRANSITION_GFC_2007_2009 | trans_vix_change_21 | 100.00% |
| TRANSITION_GFC_2007_2009 | trans_vix_change_63 | 100.00% |
| TRANSITION_GFC_2007_2009 | trans_vix_level | 100.00% |

## Role sources

VIX -> `FRED_VIXCLS`; USD/KRW -> `FRED_DEXKOUS` (secondaries are never spliced).

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

PIT Top120 signal dates: 610 (2015-01-02 to 2026-09-11); raw-input artifact kr-model-raw-inputs-36844599518 (id 11157875265).

