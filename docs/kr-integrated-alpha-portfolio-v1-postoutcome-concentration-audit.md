# KR integrated alpha portfolio v1 — post-outcome concentration audit

**POST-OUTCOME DESCRIPTIVE DIAGNOSTIC ONLY. It diagnoses an already-exposed result; it is not a new confirmatory experiment, a model rescue, an architecture selection, a promotion decision or prospective evidence, and it cannot alter the formal result or any frozen rule.**

## 1. Scope and scientific status

Status `EXPLORATORY_POST_OUTCOME_DESCRIPTIVE_DIAGNOSTIC`. This audit diagnoses the already-spent formal run `37374530672` of `kr-integrated-alpha-portfolio-v1`. The formal result is not rerun, rewritten or reinterpreted into a new decision; no execution lock, frozen file, factor weight, threshold, portfolio rule or benchmark was changed; the primary formal benchmark remains `069500.KS`. Evidence classes are kept apart: `FORMAL_REPORTED_RESULT` (copied from the sealed artifact), `POST_OUTCOME_DIAGNOSTIC_RECONSTRUCTION` (the frozen code replayed read-only), `POST_OUTCOME_COUNTERFACTUAL_SENSITIVITY` (the one registered sensitivity) and `POST_OUTCOME_DESCRIPTIVE_PROXY` (same-data references). Nothing here is prospective evidence, a model rescue, a selection or a promotion decision. Successor model design is outside the scope of this post-outcome audit.

## 2. Exact provenance

* Formal run `37374530672`, execution commit `33237df6d69e31a396959529378a0f881af9a58e`, frozen spec `eea6128cd55260904c7f74ba78698f67e522626620fd11d757c27de89c758f77`; result artifact `11371812532` (`kr-integrated-alpha-portfolio-v1-results-37374530672`, `sha256:bb29676403068b8330b12808ff30f6a5766fee35d4e66e96594591eaae766722`); raw-input artifact `11157875265` (`kr-model-raw-inputs-36844599518`, `sha256:42eeb18b7a5c88816629036f472a93057b6a9be4768ad47292ba0d2750b4cce7`, run `36844599518`); both execution-lock tags exist and point at the execution commit (checked read-only by the audit run). The formal `seal` job failed at its commit step; that is infrastructure and is not repaired here.
* Audit run `37451761441` (workflow_dispatch, `success`), workflow definition on `main` at `288204683c3a`, audit implementation `audit_ref` `11b0d67a22be8079ef6c33a6f6bdb94e7eaaca64`. Audit artifact `11406929754` (`kr-integrated-alpha-portfolio-v1-postoutcome-audit-37451761441`, archive `sha256:959069da0126b6aeb85f6819d488500016474d9fc7708ed6aa6604cff5397f0a`).
* Full audit file `postoutcome-audit-full.json`: **539,839 bytes, SHA-256 `b316a6ef2ffbf77a0b4ce5646df5b7b6b0bfc079aa3a9e795727d0e7f7e39bbc`** (the value the run printed). It stays an Actions-only artifact; this repository carries the compact record the report is rendered from. How it was read here: the workflow printed the file (gzip + base64) to its job log; the authoring environment cannot download Actions artifacts (blob storage is unreachable), so the file was decoded from the log and its byte count and SHA-256 were recomputed and found equal to the values the run printed itself. Note: an earlier handoff message quoted a different SHA-256 for this file; that was a transcription error, and the run's own value above is authoritative.

## 3. Formal-result reconstruction verification

Status **`RECONSTRUCTION_REPRODUCES_THE_FORMAL_A_AND_D_PATHS`** at tolerance 1e-09. For both architectures: reproduced = True, divergences 0, month-end NAV dates compared 117 each. Metrics compared: `cumulativeNetReturn`, `netAnnualizedReturn`, `excessAnnualizedVsPassive`, `cumulativeGrossReturn`, `maxDrawdown`, `annualizedOneWayTurnover`, `totalOneWayTurnover`, `totalCostFractionOfNav`, `annualizedCostDrag`, `replacements`, `averageHoldings`, `averageCashShare`, `annualizedVolatility`, `calendarYears`, `halves`, `firstDate`, `lastDate`, `sessions`. security_contributions raised on any day whose residual cost differed from the engine's costFraction x pre-trade NAV, and on any whole-path identity miss at 1e-9; neither raised.

|  | Annualized | Cumulative | Max drawdown | One-way turnover / yr | Cost drag / yr | Replacements |
|---|---:|---:|---:|---:|---:|---:|
| A Stock only (formal) | +5.7911% | +72.25% | -58.67% | 2.942x | +0.99% | 136 |
| D Industry + Stock (formal) | +15.0086% | +286.02% | -57.86% | 5.752x | +1.09% | 270 |
| Passive 069500.KS (formal) | +20.2413% | +493.29% | -40.69% | — | — | — |

Facts quoted from the earlier read-only audit, compared with the reconstruction rather than trusted: anchors with both books available 108 (expected 108), identical selections 0 (expected 0), mean differing names 3.2407 of 5 (expected 3.2407); agrees = True. Side-effect counters of the audit's own bundle build: cashSensitivityCalls=0, decisionCalls=0, featureBuilds=1, markerWrites=0, marketStateComputations=0, marketValueReads=0, metricCalls=0, replayCalls=0 (one past-only feature build; no marker, lock, permit, market-value read or formal replay).

D materially improved on A in the frozen development study, **but D did not beat the passive benchmark over the full formal window after costs, and its drawdown (-57.86%) is deeper than the passive path's (-40.69%)**. Nothing in this audit describes the study as having found benchmark-beating alpha.

## 4. Q1–Q10 matrix

The classification says how well the audit's evidence answers the question, not whether the answer favours the model.

| Question | Classification | Evidence basis |
|---|---|---|
| Q1. Was the ~20.24% benchmark CAGR a broad decade-long phenomenon or driven by the recent regime? | `SUPPORTED_BY_AUDIT` | frozen benchmark series, fixed spans |
| Q2. Is the frozen benchmark internally reproducible and internally consistent? | `PARTIALLY_SUPPORTED` | internal evidence only |
| Q3. Is the frozen benchmark externally reconciled to an authoritative, definition-compatible KODEX 200 / KRX series? | `UNRESOLVED_DATA_LIMITATION` | BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED |
| Q4. How concentrated did Samsung Electronics + SK Hynix become? | `PARTIALLY_SUPPORTED` | PROXY_NOT_OFFICIAL_WEIGHT |
| Q5. How much of the recent benchmark proxy gain did they explain? | `PARTIALLY_SUPPORTED` | APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS |
| Q6. What did A and D actually hold? | `SUPPORTED_BY_AUDIT` | reconstructed paths, reproduced at 1e-9 |
| Q7. Why did D outperform A? | `PARTIALLY_SUPPORTED` | reconstructed attribution, descriptive |
| Q8. Was D's performance broad through time, or concentrated in 2025-2026 and a few industries / names? | `SUPPORTED_BY_AUDIT` | reconstructed attribution, fixed spans |
| Q9. How much of D's realised result came directly from Samsung Electronics / SK Hynix and their PIT industry? | `SUPPORTED_BY_AUDIT` | reconstructed D holdings |
| Q10. What does the pre-registered D_EXCLUDE_SAMSUNG_HYNIX descriptive sensitivity show? | `SUPPORTED_BY_AUDIT` | single registered counterfactual |

* **Q1. Was the ~20.24% benchmark CAGR a broad decade-long phenomenon or driven by the recent regime?** `SUPPORTED_BY_AUDIT` — Frozen benchmark: +6.89% a year over 2017-01-16 → 2024, +98.72% in 2025 and +75.73% in 2026 to the cutoff; those last two spans carry 70.2% of the window's log wealth. The full-window +20.24% a year (+493.29%) is not a normal long-run KOSPI 200 return; it is a recent-regime figure. The years are kept and the benchmark is unchanged.
* **Q2. Is the frozen benchmark internally reproducible and internally consistent?** `PARTIALLY_SUPPORTED` — Reproducible: hash-verified series, complete against the registered calendar, and the completed audit reproduced both A and D (which carry the benchmark path) at 1e-9 over 117 month-end NAVs; the formal passive path reads +20.24% a year / +493.29% / MDD -40.69%. Not consistent: its excess over the committed price index is +4.53% a year over 2017-2024 against +1.85% for the same-data constituent reference, and it accrues on 15 single days. Status `INTERNAL_CONSTRUCTION_ANOMALY_FOUND`; the cause is not determinable from stored data.
* **Q3. Is the frozen benchmark externally reconciled to an authoritative, definition-compatible KODEX 200 / KRX series?** `UNRESOLVED_DATA_LIMITATION` — No official source was reachable; no official number is quoted. The frozen values to reconcile are recorded for five fixed checkpoints.
* **Q4. How concentrated did Samsung Electronics + SK Hynix become?** `PARTIALLY_SUPPORTED` — Inside the PIT Top120 their combined market-cap share has a median of 28.5%, a maximum of 57.2% (2026-07-01) and 52.6% on 2026-09-01. A same-data market-cap proxy, not the KODEX 200 weight.
* **Q5. How much of the recent benchmark proxy gain did they explain?** `PARTIALLY_SUPPORTED` — In the cap-weighted Top120 reference they contributed 65.4% of the 2025 plus 2026-to-cutoff gain (monthly proxy weights). Not exact for KODEX 200.
* **Q6. What did A and D actually hold?** `SUPPORTED_BY_AUDIT` — A (Stock only): 43 distinct names in 141 holding spells, 110 valid decisions; D (Industry + Stock): 80 names in 275 spells, 108 valid decisions. D's mean top-industry share of invested weight is 62.6% against 44.0% for A, and D held three or more names of one industry on 76.3% of held sessions (A 10.0%).
* **Q7. Why did D outperform A?** `PARTIALLY_SUPPORTED` — Full window D +286.02% vs A +72.25%. By fixed span D − A in cumulative return is -4.77pp (2017-2024), +80.47pp (2025) and +71.27pp (2026): D trailed A before 2025 and led only after. The books differ on every one of the 108 shared anchors (identical selections 0, mean 3.2407 of 5 names differ) and the gap is largely carried by a few names in one industry, not by costs (D paid +0.205 more NAV units). The decomposition is direct; why the Industry layer chose those names is not tested.
* **Q8. Was D's performance broad through time, or concentrated in 2025-2026 and a few industries / names?** `SUPPORTED_BY_AUDIT` — Concentrated. 98.2% of D's gross contribution (NAV units) falls in the 2025 and 2026 spans (A 99.8%); the top security is 29.1%, top two 47.0%, top five 87.1%; the top industry (ELECTRONICS_ELECTRICAL) is 59.5%. NAV-unit contributions weigh late periods more because NAV had compounded, so the percentage return by span (D -17.34% / +132.28% / +101.04%) is read beside them.
* **Q9. How much of D's realised result came directly from Samsung Electronics / SK Hynix and their PIT industry?** `SUPPORTED_BY_AUDIT` — Directly little: the two names contributed +0.296 of +3.229 gross NAV units (9.2%); Samsung Electronics +0.531, SK Hynix -0.236 (a net detractor). Through their PIT industry a great deal: ELECTRONICS_ELECTRICAL contributed 59.5% of D's gross.
* **Q10. What does the pre-registered D_EXCLUDE_SAMSUNG_HYNIX descriptive sensitivity show?** `SUPPORTED_BY_AUDIT` — With the two securities unavailable, D reads +15.49% a year / +301.85% / MDD -58.02% against +15.01% / +286.02% / -57.86% for D: +15.82pp cumulative, turnover 5.85x vs 5.75x. POST_OUTCOME_DESCRIPTIVE_SENSITIVITY, NOT_CONFIRMATORY, NOT_ELIGIBLE_FOR_MODEL_SELECTION.

## 5. Benchmark audit

### 5.1 Period decomposition (Q1)

| Span | From → to | Cumulative | Annualized | Share of log wealth | Share of terminal gain |
|---|---:|---:|---:|---:|---:|
| A_2017_to_2024 | 2017-01-16 → 2024-12-30 | +69.90% | +6.89% | 29.8% | 14.2% |
| B_2025 | 2024-12-30 → 2025-12-30 | +98.72% | +98.81% | 38.6% | 34.0% |
| C_2026_to_cutoff | 2025-12-30 → 2026-09-14 | +75.73% | n/a | 31.7% | 51.8% |
| D_full_window | 2017-01-16 → 2026-09-14 | +493.29% | +20.24% | 100.0% | 100.0% |

Annualized is shown only for spans of a full year or more. The formal ~20.24% a year is not a normal long-run expected KOSPI 200 return: 2017–2024 annualizes +6.89%, while 2025 (+98.72%) and 2026 to the cutoff (+75.73%) carry 70.2% of the log wealth. The years are not removed and the benchmark is not changed.

### 5.2 Construction and the suspicious observations (Q2)

* Series: 3860 sessions 2011-01-03 → 2026-09-14, registered calendar 3860, missing 0, not in calendar 0, non-positive or non-finite 0; hash-verified inputs. Return basis: `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS` (an as-traded close with forward-accumulated distributions where the vendor served them — neither a price return nor a complete shareholder return).
* pipeline.price_adjustment.to_total_return: the as-traded close times a forward-accumulated factor 1 / (1 - dividend / previous close) per distribution event, joined to KRX / FinanceDataReader sessions through the krx-total-return route (pipeline.benchmark_source); one factor per event, applied from the event date forward, no back-adjustment. Read from the code; no event was observed.
* Daily moves of at least 10% in the window: 2026-03-04 (-12.46%), 2026-03-05 (+10.10%), 2026-06-23 (-10.47%), 2026-07-28 (-11.19%), 2026-07-31 (+24.17%). The committed KS200 price index, an independent route to the same market, moved in the same direction on 5 of 5 of those days (index returns -11.94%, +9.83%, -10.53%, -11.55%, +19.98%; for 2026-07-31 benchmark +24.17% vs index +19.98%), so those sessions are market moves, not a source anomaly in the benchmark's own price path.
* Excess over the price index accrues in steps. 15 sessions differ from the index by at least 1% in a day: 2017-04-27 +2.02%; 2018-04-27 +1.79%; 2018-12-27 +1.40%; 2019-04-29 +2.03%; 2019-12-27 +1.07%; 2020-04-28 +1.90%; 2020-12-29 +1.34%; 2021-04-29 +1.70%; 2022-04-28 +1.43%; 2022-12-28 +1.19%; 2023-04-27 +1.47%; 2024-04-29 +1.30%; 2025-04-29 +1.40%; 2026-07-31 +3.50%; 2026-08-03 -3.38%. 13 of them fall in late April or late December and are the size of a distribution; the other two (2026-07-31 +3.50% and 2026-08-03 -3.38%) are a jump that reverses on the next session, which looks like a quote-timing difference between the ETF close and the index rather than an applied event.

| Year | Total excess over index | Event days | On event days | On all other days |
|---|---:|---:|---:|---:|
| 2017 | +4.02% | 1 | +2.02% | +1.96% |
| 2018 | +4.91% | 2 | +3.21% | +1.64% |
| 2019 | +4.61% | 2 | +3.12% | +1.45% |
| 2020 | +4.86% | 2 | +3.27% | +1.54% |
| 2021 | +4.03% | 1 | +1.70% | +2.29% |
| 2022 | +5.25% | 2 | +2.63% | +2.55% |
| 2023 | +3.87% | 1 | +1.47% | +2.36% |
| 2024 | +4.50% | 1 | +1.30% | +3.16% |
| 2025 | +4.22% | 1 | +1.40% | +2.78% |
| 2026 | +1.34% | 2 | -0.00% | +1.34% |

Over 2017-2024 the benchmark earned +4.53% a year above the index, against +1.85% for the same-data constituent reference; the gap is +2.68% a year, above the +1% descriptive flag, so the internal reading is **`INTERNAL_CONSTRUCTION_ANOMALY_FOUND`**: the series is reproducible, but its accrual over the price index is larger than the same-data constituents' own dividends explain, in steps and on both a late-April and a late-December schedule. The stored series carries no event list, so whether any distribution or split was applied twice, on the wrong date or at the wrong size is NOT testable from it; an unexplained accrual is reported as unexplained, not as an error and not as income. If the accrual were overstated, the passive path would be overstated and every architecture's excess understated; the size is not settled and no corrected benchmark is built.

### 5.3 External reconciliation (Q3)

**`BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED`.** samsungfund.com, kodex.com and data.krx.co.kr are not reachable from the authoring sandbox (outbound HTTPS is allow-listed); no official value was retrieved, so no number below is an official number. Internal reproducibility (A) is established; external economic truth (B) is not. The frozen values to reconcile with Samsung Asset Management / KRX at fixed checkpoints, comparing only definition-compatible series (KODEX 200 distribution-reinvested market-price or NAV return; KOSPI 200 total-return index; never a price-only index):

| Checkpoint | Session | Level | Year-to-date return (frozen) |
|---|---:|---:|---:|
| 2024-12-30 | 2024-12-30 | 41,550.1 | -7.22% |
| 2025-12-30 | 2025-12-30 | 82,567.4 | +98.72% |
| 2026-01-30 | 2026-01-30 | 105,039.0 | +27.22% |
| 2026-04-30 | 2026-04-30 | 136,961.0 | +65.88% |
| 2026-09-14 | 2026-09-14 | 145,096.1 | +75.73% |


## 6. Benchmark mega-cap concentration (Q4, Q5)

Same-data PROXY: share of total (not free-float) market capitalisation of the PIT Top120 from monthly snapshots; it is not the KOSPI 200 or KODEX 200 weight, and no exact official weight was obtained.

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

Formal window: median 28.5%, maximum 57.2% (2026-07-01), minimum 24.7% (2019-01-02). Snapshots above round descriptive numbers:

| Threshold | Snapshots above | First | Last |
|---|---:|---:|---:|
| 30% | 42 of 116 | 2017-11-01 | 2026-09-01 |
| 40% | 8 of 116 | 2026-02-02 | 2026-09-01 |
| 50% | 4 of 116 | 2026-06-01 | 2026-09-01 |
| 60% | 0 of 116 | — | — |

Contribution to the cap-weighted Top120 reference (`APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS`, NAV units):

| Span | Reference gain | Samsung Electronics | SK Hynix | Combined | Combined share |
|---|---:|---:|---:|---:|---:|
| A_2017_to_2024 | +0.382 | +0.174 | +0.085 | +0.259 | 67.8% |
| B_2025 | +1.201 | +0.336 | +0.290 | +0.626 | 52.1% |
| C_2026_to_cutoff | +1.682 | +0.637 | +0.621 | +1.258 | 74.8% |
| D_full_window | +3.265 | +1.147 | +0.996 | +2.143 | 65.6% |

| Reference | Full window | 2017-2024 | 2025 | 2026 to cutoff |
|---|---:|---:|---:|---:|
| REF_TOP120_CAP_WEIGHTED | +326.48% | +38.19% | +86.88% | +65.14% |
| REF_TOP120_CAP_WEIGHTED_EX_SAMSUNG_HYNIX | +131.83% | +17.05% | +56.42% | +26.62% |
| REF_TOP120_EQUAL_WEIGHT | +196.75% | +35.01% | +67.44% | +31.27% |

These are descriptions of reference portfolios; the formal benchmark stays `069500.KS`, concentration included, and "the model beats the benchmark once the two names are removed" is outcome-selected reasoning that this audit does not make.

## 7. A and D actual holdings (Q6)

|  | A Stock only | D Industry + Stock |
|---|---:|---:|
| Valid decisions / scheduled anchors | 110 / 113 | 108 / 113 |
| Signal-unavailable anchors (no-trade) | 3 | 5 |
| Holding spells (entries) / exits | 141 / 136 | 275 / 270 |
| Distinct names / held in more than one spell | 43 / 29 | 80 / 61 |
| Median spell (sessions) | 42 | 21 |
| Replacements / one-way turnover per year | 136 / 2.94x | 270 / 5.75x |
| Gross contribution / cost (NAV units) | +0.886 / +0.163 | +3.229 / +0.368 |
| Mean holdings / mean cash share | 4.87 / 2.7% | 4.87 / 2.7% |
| Largest single-name weight (mean / max) | 26.8% / 33.5% | 26.3% / 33.5% |
| Mean top-industry share of invested weight (max) | 44.0% (78.3%) | 62.6% (100.0%) |
| Held sessions with 3+ names in one industry | 10.0% | 76.3% |

Cost is each day's engine cost; per-name cost is a descriptive allocation in proportion to traded notional, not a per-name measurement. Largest contributors and detractors by security (gross NAV units, full window):

* **A top:** 066570.KS +0.274, 030200.KS +0.173, 078930.KS +0.116, 024110.KS +0.104, 028260.KS +0.103, 028050.KS +0.100. **bottom:** 034220.KS -0.100, 000120.KS -0.070, 000720.KS -0.053, 012450.KS -0.044, 011780.KS -0.039, 006360.KS -0.035.
* **D top:** 011070.KS +0.940, 066570.KS +0.578, 005930.KS +0.531, 009150.KS +0.458, 010140.KS +0.304, 034020.KS +0.263. **bottom:** 000660.KS -0.236, 000720.KS -0.095, 034220.KS -0.088, 018880.KS -0.080, 103590.KS -0.076, 000120.KS -0.072.

D by PIT industry (the industry the strategy itself used at the decision date; holding frequency = share of name-sessions, weight = mean share of NAV over all sessions):

| Industry | Name-session share | Mean NAV weight | Gross contribution, full window |
|---|---:|---:|---:|
| BASIC_MATERIALS | 4.0% | 3.9% | +0.101 |
| CAPITAL_GOODS_DEFENSE | 19.7% | 16.8% | +0.864 |
| CHEMICALS | 9.8% | 9.0% | +0.050 |
| COMMUNICATION_MEDIA_SOFTWARE | 14.9% | 17.7% | -0.067 |
| CONSTRUCTION_ENGINEERING | 4.0% | 3.7% | +0.249 |
| CONSUMER_RETAIL_SERVICES | 5.5% | 5.8% | +0.109 |
| ELECTRONICS_ELECTRICAL | 23.1% | 21.7% | +1.921 |
| ENERGY_UTILITIES | 0.4% | 0.3% | -0.007 |

Industry contribution by span (top three, NAV units):

* 2017-01-16 → 2024: CAPITAL_GOODS_DEFENSE +0.290, CONSTRUCTION_ENGINEERING +0.142, BASIC_MATERIALS +0.101 — negative: ELECTRONICS_ELECTRICAL -0.227, TRANSPORT_LOGISTICS -0.180, FINANCIALS -0.126
* 2025: CAPITAL_GOODS_DEFENSE +0.476, ELECTRONICS_ELECTRICAL +0.445, FINANCIALS +0.108 — negative: FOOD_BEVERAGE_TOBACCO -0.029, COMMUNICATION_MEDIA_SOFTWARE -0.003
* 2026 → cutoff: ELECTRONICS_ELECTRICAL +1.703, FINANCIALS +0.167, CONSTRUCTION_ENGINEERING +0.107 — negative: UNCLASSIFIED -0.043
* full window: ELECTRONICS_ELECTRICAL +1.921, CAPITAL_GOODS_DEFENSE +0.864, CONSTRUCTION_ENGINEERING +0.249 — negative: TRANSPORT_LOGISTICS -0.180, COMMUNICATION_MEDIA_SOFTWARE -0.067, FOOD_BEVERAGE_TOBACCO -0.040

## 8. D − A attribution (Q7, Q8)

| Fixed span | A | D | D − A (cumulative, pp) | Passive | Gross contribution difference (NAV) | Extra cost D (NAV) | Differing names / shared anchors | Sum of one-way turnover, D vs A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2017-01-16 → 2024 | -12.57% | -17.34% | -4.77pp | +69.90% | +0.055 | +0.103 | 3.25 / 89 | 45.67 vs 23.95 |
| 2025 | +51.81% | +132.28% | +80.47pp | +98.72% | +0.664 | +0.024 | 3.09 / 11 | 5.64 vs 3.16 |
| 2026 → cutoff | +29.77% | +101.04% | +71.27pp | +75.73% | +1.624 | +0.079 | 3.38 / 8 | 4.25 vs 1.30 |
| full window | +72.25% | +286.02% | +213.77pp | +493.29% | +2.343 | +0.205 | 3.24 / 108 | 55.56 vs 28.42 |

Fixed spans only; none was chosen from the result. Net of costs D trailed A before 2025 (A -1.67% vs D -2.37% a year while the passive path made +6.89%), then led by +80.47pp in 2025 and +71.27pp in 2026 to the cutoff. D traded 2.0x as much as A and paid +0.205 more NAV units of cost; the gross gap is +2.343, so the advantage is a selection and industry-exposure difference, not a cost difference.

Names adding to and subtracting from D − A (gross NAV units, full window): adds 011070.KS +0.940, 005930.KS +0.462, 009150.KS +0.458, 066570.KS +0.304, 010140.KS +0.304, 034020.KS +0.236; subtracts 030200.KS -0.236, 000660.KS -0.216, 018880.KS -0.080, 103590.KS -0.076, 017670.KS -0.076, 138930.KS -0.065.

Concentration of the gain (Q8):

|  | A | D |
|---|---:|---:|
| Share of gross contribution in the 2025 + 2026 spans | 99.8% | 98.2% |
| Top-1 / top-2 / top-5 securities, share of gross | 31.0% / 50.6% / 87.1% | 29.1% / 47.0% / 87.1% |
| Top industry, share of gross | COMMUNICATION_MEDIA_SOFTWARE 35.9% | ELECTRONICS_ELECTRICAL 59.5% |

Shares are of full-window gross contribution in NAV units; those weigh late periods more because NAV had compounded, so the percentage returns in the table above are the cleaner regime view. A signal-association statistic across the whole cross-section (section 12) is not the same thing as the realised concentrated portfolio, which is what this section measures.

## 9. Samsung Electronics and SK Hynix in the actual books (Q9)

| Book | Security | Decisions selecting it | First entry | Last held | Sessions held | Mean weight held | Max weight | Gross contribution (NAV) | Allocated cost (NAV) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | Samsung Electronics | 51 of 110 (46.4%) | 2017-11-27 | 2025-10-14 | 1050 | 20.0% | 28.2% | +0.069 | +0.0189 |
| A | SK Hynix | 3 of 110 (2.7%) | 2018-11-08 | 2022-11-08 | 63 | 15.5% | 18.3% | -0.019 | +0.0024 |
| D | Samsung Electronics | 40 of 108 (37.0%) | 2017-04-18 | 2026-07-22 | 840 | 22.4% | 30.5% | +0.531 | +0.0218 |
| D | SK Hynix | 14 of 108 (13.0%) | 2017-09-20 | 2026-07-22 | 294 | 16.4% | 20.9% | -0.236 | +0.0109 |

Combined contribution of the two names to D, by span (gross NAV units; share of D's gross in the span):

| Span | Samsung Electronics | SK Hynix | Combined | Share of D's gross | Allocated cost |
|---|---:|---:|---:|---:|---:|
| 2017-01-16 → 2024 | +0.014 | -0.025 | -0.012 | -20.4% | +0.0206 |
| 2025 | +0.195 | +0.000 | +0.195 | 17.1% | +0.0013 |
| 2026 → cutoff | +0.322 | -0.210 | +0.112 | 5.5% | +0.0108 |
| full window | +0.531 | -0.236 | +0.296 | 9.2% | +0.0327 |

Answer: D's result did not depend on these two names directly. Together they are 9.2% of D's gross contribution; Samsung Electronics contributed and SK Hynix subtracted (-0.236, mostly in 2026), and the pair adds +0.246 to D − A. It depends heavily on their PIT industry: `ELECTRONICS_ELECTRICAL` supplied 59.5% of D's gross, through other members of that industry 011070.KS +0.940, 066570.KS +0.578, 009150.KS +0.458, 010140.KS +0.304 (largest contributors, spell totals).

## 10. D_EXCLUDE_SAMSUNG_HYNIX descriptive sensitivity (Q10)

**POST_OUTCOME_DESCRIPTIVE_SENSITIVITY · NOT_CONFIRMATORY · NOT_ELIGIBLE_FOR_MODEL_SELECTION**

Rule: 005930.KS and 000660.KS removed after stock and industry scoring and before selection; every other frozen rule unchanged; next eligible ranked names fill the book. No refit, no factor or parameter change, benchmark unchanged, mean holdings 4.87 (unchanged). Formal decisions unchanged: True. Evidence class `POST_OUTCOME_COUNTERFACTUAL_SENSITIVITY`. Signal availability 108 of 113 anchors, as in D.

|  | Ann. D | Ann. excl. | Cum. D | Cum. excl. | MDD D | MDD excl. | Turnover D | Turnover excl. | Cost D | Cost excl. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full window | +15.01% | +15.49% | +286.02% | +301.85% | -57.86% | -58.02% | 5.75x | 5.85x | 0.3471 | 0.3540 |

| Span | Cum. D | Cum. excl. | MDD D | MDD excl. | Σ one-way turnover D | Σ one-way turnover excl. | Σ cost D | Σ cost excl. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2017-01-16 → 2024 | -17.34% | -16.39% | -57.86% | -58.02% | 45.67 | 45.87 | 0.2846 | 0.2868 |
| 2025 | +132.28% | +120.66% | -7.87% | -7.87% | 5.64 | 6.30 | 0.0357 | 0.0401 |
| 2026 → cutoff | +101.04% | +117.82% | -44.72% | -43.12% | 4.25 | 4.30 | 0.0267 | 0.0271 |
| full window | +286.02% | +301.85% | -57.86% | -58.02% | 55.56 | 56.47 | 0.3471 | 0.3540 |

By span the effect runs in both directions (-11.62pp in 2025, +16.77pp in 2026 to the cutoff), which is the usual look of replacing two names with their neighbours in the ranking rather than a systematic loss or gain.

Descriptively, the exclusion neither removed nor reduced D's full-window result: it reads +15.82pp of cumulative return and +0.48pp a year versus D, with the same drawdown depth and slightly higher turnover. The book moved to other `ELECTRONICS_ELECTRICAL` names (57.5% of gross; top five securities 85.4%), so the sensitivity shows independence from the two securities, not independence from their industry. It informs interpretation only: it is not a result about beating the benchmark, not a rescue and not eligible for model selection, and no other exclusion set was run.

## 11. Formal frozen decisions (unchanged)

* Industry layer: **`INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED`** (pair classes {'marketOff': 'IMPROVES', 'underC0': 'IMPROVES', 'underC1': 'IMPROVES'}).
* Final architecture: **`NO_UNAMBIGUOUS_FINAL_ARCHITECTURE`**, reason `MARKET_LAYER_PARETO_TRADE_OFF`; underlying `I+S`.
* These are the sealed machine decisions of run 37374530672. This audit does not alter, reinterpret into a different decision, or add to them.

## 12. Post-outcome economic interpretation

Kept separate from section 11. The narrowest description the numbers support is **regime-dependent and industry-concentrated development support, not dependent on the two named securities**:

* **Regime-dependent.** D trailed A and the passive path before 2025 (-17.34% vs A -12.57% vs passive +69.90%); 98.2% of its gross contribution arrived in the 2025 and 2026 spans, when it beat passive (+132.28% vs +98.72%; +101.04% vs +75.73%).
* **Industry-concentrated.** The Industry layer made D a concentrated industry book (three or more names of one industry on 76.3% of held sessions, 83.5% top-industry share in 2026), and `ELECTRONICS_ELECTRICAL` supplied 59.5% of its gain; five securities supplied 87.1%.
* **Not dependent on Samsung Electronics / SK Hynix.** 9.2% of the gain directly; the exclusion sensitivity moved the result by +15.82pp cumulative.
* **Not benchmark-beating overall.** D +15.01% vs passive +20.24% a year, +286.02% vs +493.29%, drawdown -57.86% vs -40.69%, at 2.0x A's turnover. The benchmark itself carries the unresolved accrual question of section 5.2.

Context from the sealed anatomy studies (read, never rerun). **Signal association** is a cross-sectional property of the whole universe; **portfolio realisation** is what the five-name D book earned. They are different questions.

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
* **B — implemented portfolio.** NOT ANSWERED by these reports. They measure rank associations over the whole cross-section; they say nothing about whether a five-name book held the two names, how large their weights were, or what they earned. That is what the D reconstruction and the D_EXCLUDE_SAMSUNG_HYNIX sensitivity are for. The completed audit answers B for the integrated D book: it did not depend on the two securities; its gain came from a small number of industries, chiefly `ELECTRONICS_ELECTRICAL`, in 2025 and 2026.

## 13. Remaining limitations

* **External benchmark reconciliation is unresolved** (`BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED`), and the internal anomaly in the benchmark's accrual over the price index (`INTERNAL_CONSTRUCTION_ANOMALY_FOUND`) cannot be explained from stored data because no event list is stored.
* Mega-cap weights are a same-data Top120 market-cap proxy; exact KODEX 200 constituent weights were not obtained.
* All figures are post-outcome descriptions of one outcome-exposed historical sample, with no multiplicity correction; contributions in NAV units weigh late periods more; per-name cost is an allocation, not a measurement.
* The sensitivity removes two named securities only; it says nothing about the industry, a different exclusion, or any other construction, and none was run.
* Korean value/quality coverage and the partial distribution basis (`BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS`) remain as sealed; the total-return basis of high-dividend names is unaudited.
* The full audit file is an Actions artifact (not committed); the repository carries the compact record and the file's byte count and SHA-256.

## 14. Reproducibility / audit run identity

Audit run `37451761441`, artifact `11406929754`, audit implementation `11b0d67a22be8079ef6c33a6f6bdb94e7eaaca64`, full file 539,839 bytes `b316a6ef2ffbf77a0b4ce5646df5b7b6b0bfc079aa3a9e795727d0e7f7e39bbc`. The compact record `docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-completed-audit.json` is a pure function of that file (`scripts/run_kr_integrated_alpha_portfolio_postoutcome_audit.py --mode compact --full-json <file>` refuses any file whose bytes differ); this report and `docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.json` are regenerated deterministically from it and the frozen repository inputs (`--mode local`). The audit workflow is read-only: `contents: read`, `actions: read`, no `execute`, lock, marker, permit or push.

*This is a post-outcome descriptive diagnostic. It does not change the formal result, any frozen rule or any decision, and it is not prospective evidence.*
