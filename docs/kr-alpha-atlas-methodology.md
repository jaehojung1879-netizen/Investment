# kr-alpha-atlas — KR Alpha Research Completion Program: methodology

Status: `RESEARCH_CONTRACT_DRAFT`. This is the design of ONE bounded program, written before any of its outcomes exist. It computes nothing, reads no
label and authorizes no execution. The machine-readable inventory is `research_specs/kr-alpha-atlas-registry-v1.json` (validated by
`pipeline/kr_alpha_atlas_registry.py`; human view `docs/kr-alpha-atlas-information-map.md`). The phase sequence and the stopping rules are in
`docs/kr-alpha-atlas-execution-roadmap.md`.

Every Korean date through 2026-09-14 is outcome-exposed, and several prior studies on it have been read. So everything Phase C can produce is
**DEVELOPMENT evidence**. Splitting reused history into "train" and "test" does not change that, and this program never labels such a split as
untouched validation. Confirmation can only come from prospective receipts.

## 1. The question

Across every economically meaningful kind of information this repository can actually obtain, which information families carry **independent,
stable, actionable** information about future returns relative to 069500.KS, after costs and risk? For any candidate the program must be able to say:

1. why a stock is attractive, and which observable information says so;
2. whether that information predicts benchmark-relative returns at its registered horizon;
3. whether it adds anything beyond simpler information (Level 2);
4. whether it holds across years, regimes, industries and liquidity tiers;
5. whether the expected increment survives costs, capacity and uncertainty (Level 4);
6. when the right answer is to own no individual stock.

H2 (value with business confirmation, `docs/kr-alpha-signal-v2-design.md`) is one `CANDIDATE_SIGNAL_FAMILY` evaluated here as interaction X1. It is
not the program.

## 2. What is measured: the alpha decomposition

All returns are the repository's `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS` basis over the same sessions, from the execution
session (the KR session after the signal) for H sessions. Arithmetic decomposition of one name's excess:

```
stock - market  =  (stock - LOO industry)  +  (LOO industry - market)
                    C: stock selection        B: industry allocation
```

The leave-one-out (LOO) industry is cap-weighted at the signal date and excludes the stock itself, which is the within-industry anatomy's
construction. A portfolio's excess is the weighted sum of these terms plus:

| Term | What it is | Never credited to |
|---|---|---|
| A. Market exposure | beta x market, and any invested fraction other than 100% | stock selection |
| B. Industry allocation | industry return minus market, weighted | stock selection |
| C. Stock selection | stock minus its LOO industry | — this is the only term a stock-selection claim may cite |
| D. Risk-factor exposure | Level 4 regression of the book's excess on the B4 baseline factors (value, momentum, size/liquidity, volatility) | stock selection |
| E. Trading costs | dated KR schedule (`config.json`: commission 5bp, half of the 12bp spread, 20bp sell tax) plus 15bp each way on the 069500.KS leg (an assumption) | netted invisibly anywhere |
| F. Cash / passive allocation | weight held in the declared fallback (passive 069500.KS or cash, which are separate policies) | stock selection |
| G. Residual | what is left after A-F | anything, until it survives Levels 2-4 |

Arithmetic attribution is reported per block and then averaged. A compounded headline is reported only beside its split into an arithmetic
selection term and a compounding term (`selection_value.decompose_edge`), because a book less volatile than its benchmark earns the compounding term
without picking a single better name. The cross terms of compounding are reported, never assigned to a component.

**Benchmark limitation, carried as a blocker.** The 069500.KS series accrues +4.53%/yr over the KS200 price index in 2017-2024 against +1.85%/yr for
a same-data constituent total-return reference (`INTERNAL_CONSTRUCTION_ANOMALY_FOUND`, `BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED`). The benchmark
is not changed. Before any **real-world** performance claim (as opposed to a development association), one bounded reconciliation check must pass:
compare the repository's 069500.KS adjusted return with an authoritative, definition-compatible series (KODEX 200's published NAV total return, or
KRX's KOSPI 200 total-return index) over the same sessions, year by year. PASS requires every calendar-year difference within 0.50pp, the sealed
market model's own return band. FAIL keeps every Phase C result a relative-ranking statement only. BLOCKED (source unreachable) is reported as
blocked and has the same effect as FAIL. Ranking and within-date contrasts are unaffected, because the benchmark is a same-date constant for every
name.

## 3. Universe and horizons

- **Reference universe:** PIT KRX top-120 (`krx_universe.members_on_date`), comparable with every prior KR study. Preferred shares are excluded from
  accounting-based features (issue-cap proxy distortion), never silently from price features.
- **Broader universe:** a liquidity-qualified KOSPI universe is `DATA_BUILD_REQUIRED`. Membership is point-in-time from `sto/stk_bydd_trd` (930
  issues on 2013-01-02), but price panels, DART fundamentals and terminal economics exist only for the 260 ever-top-120 names. KOSDAQ is
  `SOURCE_BLOCKED`. Phase B reports feasibility only. It is never silently added to Phase C.
- **Horizons:** one primary and at most one secondary per family, declared in the registry with its justification (A 126/21, B 126/252, C 126/252,
  D 21/63, E 126/21, F 126, G 21/63, H 126/63, I 126, J 21/63). Confirmatory inference exists only at H21 and H126, the two horizons the calendar-time
  interval was calibrated for (`alpha-inference-calibration-v4/v5`). H63 and H252 readings are descriptive. No feature-horizon search.

## 4. Level 1 — individual relationships

For each feature whose readiness is READY or DERIVABLE at Phase C's frozen data identity, at its registered horizon, per signal date first and then
date-equal-weighted:

| Statistic | Role |
|---|---|
| Top-minus-bottom tercile spread (raw and within-industry) | primary; linear in returns, so the calibrated `calendar_time_sn_interval` applies |
| Top-tercile excess over 069500.KS | long-only relevance: a significant spread made of a collapsing bottom is not an edge a long-only book can collect |
| Spearman rank IC, raw and within-industry | descriptive; Newey-West HAC with bandwidth in observations of the weekly series |
| Coverage and date counts | measured denominator published with every share; a date with fewer than 30 measured names is not evaluable |
| Stability | sign by calendar year (years with at least 13 dates), first versus second half, and by `I01` market state |

`ALREADY_TESTED` features are **not re-measured**. Their sealed readings are reused, and they enter Level 2 only as baselines or controls. Re-running a
descriptive map on the same history would spend outcome access for nothing new.

## 5. Level 2 — incremental information

Baselines are fixed in the registry: B0 market/industry and price reference, B1 value and profitability, B2 momentum, B3 volume and liquidity, B4
their combination. Every reference model is a date-balanced pooled cross-sectional linear regression on within-date percentiles with missingness
indicators: a regularised Fama-MacBeth. It has no hyperparameter search (one ridge penalty fixed in the spec), expanding annual refits, and trains only
on targets that exit before the first signal date of the evaluation year.

| Test | Question | Primary reading |
|---|---|---|
| Add-one-family to B4 | does family X add to the simple baseline? | paired out-of-sample prediction-error improvement and rank-weighted spread improvement, calibrated interval at H21/H126 |
| Leave-one-family-out from the full READY set | is family X needed given all the others? | same statistics |
| Residualised signal | per date, regress X's percentile on the B4 features and use the residual | Level 1 statistics on the residual |
| Fama-MacBeth slope of X with B4 controls | conditional association | NW standard error, descriptive where assumptions fail (overlap, clustering) |
| Redundancy map | Spearman correlations and family-level clustering, computed on training years only | no verdict label; explains why an ablation is near zero |

Both orderings (add-one and leave-one-out) are always reported. A sequence of additions is never read as an order-independent importance ranking.

## 6. Level 3 — limited conditional hypotheses

Six interactions, each with a stated economic argument and a negative control, and no others (`levelThreeInteractions`, `maxInteractions: 6`):

| ID | Interaction | Negative control |
|---|---|---|
| X1 | value x business confirmation (H2) | the same confirmation contrast among expensive names |
| X2 | momentum x turnover (Lee-Swaminathan) | turnover against a permuted momentum rank |
| X3 | industry leadership x stock strength inside it | stock strength inside lagging industries |
| X4 | price leadership x investor accumulation | **BLOCKED** (investor flow `SOURCE_BLOCKED`); its OHLCV proxy control is never a substitute |
| X5 | volatility x liquidity | volatility against a permuted liquidity rank |
| X6 | market regime x relative momentum | the same split on a one-year-lagged regime label |

Each interaction is a 2x2 contrast on within-date terciles, compared with its own negative control. It is never a product term searched across
features.

## 7. Level 4 — economic and investment relevance

Only features or families that pass Levels 1-3 by the rules in §9 reach Level 4. They are evaluated with:

- an equal-weight diagnostic basket of the top group, and the 0-5 name slot policy of `kr_alpha_signal_v2.decide` (20% per slot, at most 2 per
  industry, unused slots to the declared fallback). No Kelly, covariance optimiser or leverage; this PR designs no allocator;
- net excess over 069500.KS after the dated costs, decomposed as in §2 (A-G), with arithmetic and compounding reported apart;
- capacity: each order at most 1% of the name's median 60-session traded value; turnover reported as names replaced and weights retargeted separately;
- risk: downside volatility, maximum drawdown, concentration by name and industry, and the share of sessions with zero names held;
- liquidity tiers: the same statistics within the top and bottom halves of median traded value, so that an edge living only in untradeable names is
  visible.

Liquidity has two roles that never overlap. As an expected-return characteristic (`E01`, `E02`) it is an alpha candidate. As a cost or capacity
constraint (`E03`, `E05`, `E04`) it only filters or prices trades. The registry validator refuses a cost or eligibility quantity inside any baseline,
so the same liquidity measure cannot both earn alpha and be counted as a cost saving.

Investor flow and ownership are a separate family (G). They are `SOURCE_BLOCKED` or historically shallow today, and their slot is kept empty rather
than filled. OHLCV accumulation proxies (`D11`) live in family D and are labelled `OHLCV_PROXY_NOT_INVESTOR_FLOW`. The validator refuses an OHLCV
source in family G.

## 8. Statistical discipline (declared now)

| Concern | Rule |
|---|---|
| Point-in-time | every input `availableFrom <= T`; DART by receipt date; market observations at the signal close; ECOS/FRED revised history is `PIT_UNSAFE` historically |
| Survivorship and delisting | PIT top-120 membership with departed names; a held name that stops trading without a cited terminal consideration makes the outcome `TERMINAL_ECONOMICS_UNRESOLVED`, never a last-price mark; Level 1 group returns drop only the unresolved name-date and count it |
| Corporate actions | the 22 terminations stay unresolved; their share of each statistic's name-dates is published |
| Chronology | features from the past only; models refit annually on targets that exited before the evaluation year; purge and 21-session embargo |
| Cross-sectional dependence | per-date statistics first, then time-series inference across dates |
| Overlapping horizons | calendar-time decomposition with the calibrated SN interval at H21/H126; Newey-West bandwidth in observations of the series; 126-session block bootstrap for portfolio paths |
| Multiple testing | Level 1: Benjamini-Yekutieli FDR q = 0.10 within each family; Level 2: Holm across family ablations (FWER 0.05); Level 3: Holm across the six interactions. The correction is chosen now, not after results |
| Redundancy | the training-only correlation map is published beside every ablation |
| Instability | years, halves and market states reported; a sign flip between halves blocks support |
| Benchmark comparability | §2 reconciliation check |
| Economic vs statistical significance | Level 4 after costs; a significant IC with negative after-cost opportunity is not an investable signal |
| Costs and capacity | §7 |

## 9. Verdicts for Phase C (decided before outcomes)

Per feature or family, mechanically from the frozen statistics:

| Verdict | Condition |
|---|---|
| `BLOCKED` | readiness failure, or required evaluable dates below 80% of scheduled dates |
| `NO_DEVELOPMENT_EVIDENCE` | Level 1 BY-adjusted q > 0.10 on the primary statistic, or the point estimate has the wrong sign |
| `UNSTABLE` | Level 1 passes but the sign differs between chronological halves, or is positive in fewer than 60% of evaluable years |
| `REDUNDANT` | Level 1 passes but the Level 2 add-one increment to B4 is not Holm-significant |
| `NOT_ECONOMIC` | Levels 1-2 pass but the Level 4 net top-group excess after costs is not positive, or it lives only in the bottom liquidity half |
| `INDEPENDENT_DEVELOPMENT_SUPPORT` | all of the above pass |

`INDEPENDENT_DEVELOPMENT_SUPPORT` permits exactly one thing: freezing the candidate for prospective receipts (Phase E). It is never confirmation,
never promotion, and never a production change.

## 10. Literature (motivation, not validation)

These papers motivate which information to look at and which mistakes to guard against. None of them validates a Korean signal.

- Fama, E.F. & French, K.R. (1993), "Common risk factors in the returns on stocks and bonds", *Journal of Financial Economics* 33(1), 3-56.
- Fama, E.F. & French, K.R. (2015), "A five-factor asset pricing model", *Journal of Financial Economics* 116(1), 1-22 (profitability, investment).
- Jegadeesh, N. & Titman, S. (1993), "Returns to buying winners and selling losers", *Journal of Finance* 48(1), 65-91.
- Amihud, Y. (2002), "Illiquidity and stock returns: cross-section and time-series effects", *Journal of Financial Markets* 5(1), 31-56.
- Novy-Marx, R. (2013), "The other side of value: The gross profitability premium", *Journal of Financial Economics* 108(1), 1-28.
- Lee, C.M.C. & Swaminathan, B. (2000), "Price momentum and trading volume", *Journal of Finance* 55(5), 2017-2069.
- Gu, S., Kelly, B. & Xiu, D. (2020), "Empirical asset pricing via machine learning", *Review of Financial Studies* 33(5), 2223-2273.
- Harvey, C.R., Liu, Y. & Zhu, H. (2016), "... and the cross-section of expected returns", *Review of Financial Studies* 29(1), doi:10.1093/rfs/hhv059.
- McLean, R.D. & Pontiff, J. (2016), "Does academic research destroy stock return predictability?", *Journal of Finance* 71(1), 5-32.
- Jensen, T.I., Kelly, B. & Pedersen, L.H. (2023), "Is there a replication crisis in finance?", *Journal of Finance* 78(5), 2465-2518.

What they imply here: the volume, liquidity and volatility families are among the strongest predictors in large machine-learning studies
(Gu-Kelly-Xiu) and are the least-studied families on this ledger. Published anomalies decay after publication (McLean-Pontiff), so a Korean reading of
a famous factor is weaker evidence than its paper. Hundreds of factors have been tried (Harvey-Liu-Zhu), so the correction in §8 is declared before
results. Many factors do replicate internationally (Jensen-Kelly-Pedersen), so an unbiased search is worth finishing rather than abandoning.
