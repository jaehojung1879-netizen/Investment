# kr-factor-anatomy-v1 — design and protocol (exploratory market map)

> **EXPLORATORY PROTOCOL ONLY — NO NEW FACTOR OUTCOMES COMPUTED.**
> `scientificStatus: EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`.
> This document, the frozen spec (`research_specs/kr-factor-anatomy-v1.json`), the harness and the workflow were
> written and tested on synthetic data only. No decile, quintile, factor return, winner/loser ranking, KEPCO
> realised case or factor correlation with future returns has been computed or inspected.

This note is written for two readers: a quantitative reviewer who wants to know exactly what is frozen, and a
serious individual investor who wants to know what the study will and will not be able to say.

## 1. What question this answers, and what it cannot

`kr-model-overlay-portfolio-v1` tested **one combined system**: eleven raw features entered one linear model with 22
other terms, the model's predictions drove a five-name portfolio, and the whole thing was compared with the KODEX 200
ETF. The sealed answer is `DEVELOPMENT_REJECT`. That answer is about the *system*. It cannot tell us whether
cheapness, profitability, momentum or liquidity were individually related to later returns, in which years, or in
which kinds of company, because a combined model mixes them and a rejected portfolio hides them.

This study asks the descriptive question instead:

> What characteristics have historically been associated with subsequent benchmark-relative returns in the Korean
> equity market, in which periods, subgroups and structural company types?

It produces a **market map**, not a strategy. Every Korean date through the development cutoff (2026-09-14) is already
outcome-exposed, so every result is permanently **exploratory, development-only and hypothesis-generating**. It can
suggest hypotheses for a future independent, preregistered study. It can never validate, rescue, promote or alter
anything — in particular it cannot change the sealed v1 result. There is no PASS or FAIL, no "best factor", no
production weight, no recommended portfolio, and no single table, year, subgroup or case study counts as validation.

## 2. What exactly is frozen

* The historical input: the preserved raw artifact `kr-model-raw-inputs-36844599518` (run 36844599518, artifact id
  11157875265, archive digest `42eeb18b…cce7`), checked by input identity `233df37e…66a7`. KRX is never collected
  again and the snapshot is never silently replaced.
* The eleven raw features of v1 (value, quality, catalyst, risk), their orientation, the weekly signal calendar, the
  benchmark (069500.KS), the horizons (126 and 252 sessions) and the cutoff.
* Every threshold, cutoff, block length and seed (see the spec). Nothing is tuned after any result.

The spec is pinned by a SHA-256 sidecar and by the hashes of the harness code, the workflow, this document, the runner
and the sealed v1 inputs it reads. Outcome execution is only possible from merged `main`, by a manual dispatch.

## 3. The return definition — an audit that corrects the premise

The task brief expected the v1 outcome to be a close-to-close **price** return that excludes dividends. Reading the
code shows something more careful, and the repository evidence overrides the brief:

* The v1 outcome is `Close[exit]/Close[entry] − 1` for the stock minus the same ratio for 069500.KS, with entry the
  next KR session close after the signal date and exit H sessions later, exact endpoints only
  (`alpha_opportunity_v2_evaluation.target_from_sessions`).
* The `Close` it reads is **not** a raw price. `price_adjustment.to_total_return` rebases each vendor frame to the
  as-traded close multiplied by a forward-accumulated factor `1/(1 − dividend/previous close)` wherever a distribution
  event exists; the replay seals this as `AS_TRADED_CLOSE_WITH_FORWARD_ACCUMULATED_TOTAL_RETURN`. The benchmark ETF
  gets the identical treatment. Korean sessions come from FinanceDataReader and distributions from Yahoo.
* But distributions are included **only where the vendor served them**. Yahoo serves none for delisted Korean tickers
  (0 of 22 audited terminated securities carry one, against 215 of 238 continuing names), and per-name, per-year
  completeness for continuing names is unaudited. v1's own data audit says: *"Includes distributions only where vendor
  event inputs existed … Not unqualified full shareholder total return."*

So the outcome is **neither a pure price return nor a complete total shareholder return**. It is a
`BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS`. That label is used everywhere. The study never says
"total return" or "total shareholder return", and the primary analysis keeps this exact definition so it is
comparable with v1.

**Banks and other high-dividend stocks.** Because distributions are partial, a high-dividend stock can be economically
misrepresented: where a payment was not served, its ex-dividend price drop appears as a loss without the cash received.
Banks and financials are the obvious cases. Nothing in this study may be read as showing that bank or financial
characteristics fail economically. No dividend adjustment is improvised from incomplete data; `TOTAL_RETURN_ANALYSIS`
is `DATA_FOUNDATION_REQUIRED`, and any total-return extension must be separately sourced, audited and preregistered.

## 4. Two analysis universes

Both start from the v1 point-in-time membership: the strictly previous monthly KRX top-120 by market capitalisation
(no current-member union, no survivorship backfill). Every member is a large cap, so this study says nothing about
small caps.

| | A. `BROAD_PIT_ANALYSIS_UNIVERSE` (primary) | B. `V1_INVESTABLE_ANALYSIS_UNIVERSE` |
|---|---|---|
| Membership | PIT top-120 | PIT top-120 |
| Factor tested | its own value must be finite | its own value must be finite |
| Other factor families | **not required** | VALUE, QUALITY and CATALYST each need ≥ 1 finite raw feature |
| Traded on the signal date | not required | required |
| 60-session average value traded | not required | ≥ 3,000,000,000 KRW |
| Annualised downside volatility | not required | finite and ≥ 0.01 |
| v1 prediction, cost hurdle, caps, overlay | not used | not used |

The two are never silently switched; B exists as a sensitivity so v1's filters cannot hide market structure. A stock
with a valid book-to-market ratio but no OCF improvement is still part of the book-to-market anatomy in A.

## 5. How a factor is read

For each signal date, names are ranked by the factor using **only that date's information**. A name's percentile and
decile are fixed *before* any outcome is attached; a name whose outcome is later withheld still occupies its rank slot.
Percentiles use average ranks, so tied values share one percentile and nothing depends on row order.

* Deciles are formed on a date only if at least **50** names have a finite value (about five per decile, the smallest
  count at which a decile median is not decided by one or two stocks). Dates with 10–49 names contribute a rank
  correlation only; fewer contribute nothing. Both counts are reported.
* Every statistic is first a per-date number, then averaged over dates with **equal weight per date** (the repository's
  `date_weights` convention), so a date with 120 names never outweighs one with 60.
* Reported for each factor, horizon, universe and terminal treatment: observations and dates; mean and median relative
  return and fraction beating the benchmark per decile; D10 − D1; within-date rank correlation; a calendar-year table;
  the number and fraction of years with positive D10 − D1 (years with at least 13 signal dates); decile monotonicity;
  a leave-best-year-out check; the split by the benchmark's trend/volatility state; and a block-bootstrap interval.
* The interval uses the repository's date-block convention (`block_sample_indices`, blocks of 26 weekly dates for H126
  and 52 for H252, 2,000 replicates, seed 42). It is descriptive: no calibration claim, no multiplicity adjustment, no
  decision role. Weekly signals overlap, so the effective number of independent observations is a small fraction of the
  date count.

`negativeDownsideVol126` is the minus of annualised downside volatility, so **higher means a calmer stock**. All
factors are shown side by side in fixed order and never sorted by result.

Descriptive labels are rule-based and never gate anything: `BROADLY_POSITIVE_HISTORICAL_ASSOCIATION`,
`BROADLY_NEGATIVE_HISTORICAL_ASSOCIATION`, `UNSTABLE_OR_REGIME_DEPENDENT`, `CONCENTRATED_IN_SPECIFIC_STRATA`,
`NO_CLEAR_MONOTONIC_PATTERN`, `DATA_INSUFFICIENT`. Their constants (monotonicity floor 0.5, two-thirds of years, four
fifths of strata) are fixed in the spec now, are not optimisation targets, and the interval is shown beside the label
rather than inside it.

## 6. Families, size and liquidity

VALUE, QUALITY, CATALYST and RISK are examined two ways: a full-history rank-mean score (equal weight over the
constituents a name has — v1's own rule, no new weighting), and the exact archived v1 family scores where v1 produced
them (evaluation dates only, fold-standardised and median-imputed, horizon-specific).

`logAdv60` carried weight in v1 and large, liquid names were frequent at the top. We need to separate genuine liquidity
from being a large, institutional, index-heavy company. KRX market capitalisation is in the snapshot, so for every factor
we report behaviour overall and within each within-date **market-cap quintile** and **ADV60 quintile**, and for
liquidity specifically: raw ADV rank versus later return; the ADV effect within market-cap strata; the market-cap effect
within ADV strata. Association only; no causality.

## 7. Fundamentals up, price down

Four descriptive states: fundamentals up/down × relative price up/down. Two flavours are kept apart:

* **Signal-time**: `ocfImprovementToAssets > 0` (and, where derivable, `netIncomeImprovementToAssets > 0`). The
  net-income version is built by the same filing-visibility, stage, TTM roll-forward and statement-basis rules as v1's
  prior-year OCF chain, and stricter: all links must share one statement basis (CFS or OFS), else it is missing.
* **Window-realised (H126)**: book growth and multiple expansion from v1's existing `valuation_convergence`, which is
  price-mechanical, not a complete return decomposition, and uses exit-date information by construction.

Reported by year and by terciles of prior relative run-up, book-to-market, market cap and ADV60. The question is whether
"fundamentals improved but the stock lagged" cases are over-represented in a prior run-up, in valuation compression, in
particular sizes or liquidity, or (later) in structural company types. It is descriptive; nothing is causal.

## 8. Value is not one thing

Fixed interaction tables with frozen terciles (1/3, 2/3 of within-date percentile) or the sign rule `> 0`: cheap ×
profitability, cheap × OCF improvement, cheap × prior momentum, OCF improvement × prior relative126, profitability × OCF
improvement. Book-to-market is the primary valuation axis; earnings yield and OCF yield are shown separately. The aim is
to tell *cheap because bad* from *cheap but improving*.

## 9. Why structure matters: KEPCO, banks and historical classification

Identical accounting ratios can mean different things in different company types. KEPCO (한국전력, `015760.KS`) is a
regulated public enterprise: its profit depends materially on administered tariffs, fuel costs and government policy,
not on ordinary pricing power — a useful stress case. Financial companies have balance-sheet economics unlike
industrials, and their dividends matter more than price alone (section 3).

Sector or structural subgroup analysis needs **historical, point-in-time** classification. Today's sector label is not
history, and the repository has none: v1 records `DEFERRED_BY_PIT_SECTOR_HISTORY`, the KRX snapshots carry no sector,
and a retroactive Korean sector history is graded NOT_RESEARCHABLE_NOW (KRX is replacing its classification). So
`STRUCTURAL_CLASSIFICATION_STATUS = DATA_FOUNDATION_REQUIRED`: the primary factor anatomy proceeds, and every
sector/structural subgroup table is marked `DATA_FOUNDATION_REQUIRED` and is not computed. KEPCO is **not** removed from
any primary table. Instead: the full-universe result includes it; a one-ticker leave-out sensitivity (a fixed list of
one, defined now, not a classification claim) is reported separately; and KEPCO is a mandatory case study.

### Missing-data task: structural classification

A classification may enter only through a separate data-foundation change that supplies, per firm, an authoritative
source and validity dates, with the list frozen and digest-pinned in a **new** preregistered version before any anatomy
outcome table exists. Needed lists: `REGULATED_OR_PUBLIC_ENTERPRISE`, `FINANCIAL`, and
`ORDINARY_NON_FINANCIAL_PRIVATE` (the complement). The harness refuses a classification file the spec does not pin and
refuses a pinned file whose digest differs, so a list cannot appear after outcomes exist and no firm can be added or
removed after results.

## 10. Winners, losers and fixed case studies

Mechanical tables for H126 and H252, 20 rows each: largest absolute stock-return windows, largest benchmark-relative
winners, largest losers, largest positive and negative sealed-v1 prediction errors, and the tickers most often in the v1
top five. Rows are chosen by rule (ties by date then ticker) and a window overlapping an already chosen window of the
same ticker is skipped, so one episode cannot fill a table. For each event the report records the raw features,
within-date percentiles, family scores, v1 fold coefficients and the exact linear contribution of every feature and
interaction.

Case studies are fixed now: Samsung Electronics `005930.KS`, SK Hynix `000660.KS`, KEPCO `015760.KS`. For each, the
highest and lowest v1 H126 prediction and the largest positive and negative realised prediction error among cases with a
valid outcome. The "why the model thought this" table is rebuilt exactly from the fold's transform snapshot and checked
against the archived prediction; a decomposition that does not reproduce it is reported as `MISMATCH`, never
approximated. No narrative is attached by the code; dates are matched to disclosures in a later, separate task.

## 11. Survivorship and terminal economics

The inherited terminal-action discipline is kept: a name-date counts only if its target is matured and the v1
eligibility leaves it eligible; otherwise it is **withheld and counted, never zero**. That withholds the 22 audited
terminated securities (about 3.7% of tradable member-dates), a documented survivorship-conditioning limitation. To make
its effect visible, the standalone tables are also produced under `ALL_OBSERVED_ENDPOINTS` (price-return basis for those
names) beside, never merged with, the primary. Denominators — observed valid and withheld outcomes, by year and horizon —
are always reported. No delisted name is dropped as inconvenient, no terminal price is forward-filled, and today's
survivors are never substituted.

## 12. Execution architecture

* `pipeline/kr_factor_anatomy.py` — pure statistics. `pipeline/kr_factor_anatomy_report.py` — table assembly and the
  Markdown report. `pipeline/kr_factor_anatomy_execution.py` — spec identity, authorization and the future data
  assembly. `scripts/run_kr_factor_anatomy_v1.py` — `verify` or `execute`. The sealed v1 machinery is imported
  read-only; its execute path, permit and lock are never called.
* `verify` (the only mode pull-request CI runs) checks spec identity, the import closure and the v1 relationship and
  reads no data and no outcome.
* `execute` refuses before reading a byte unless: `workflow_dispatch`, `refs/heads/main`, the checkout is the
  dispatched commit, this exact spec and sidecar are committed there, the dispatch names the exact artifact and run, the
  Actions API artifact id and archive digest equal the pinned values, and no committed result exists. Then: input
  identity is verified, label-free features are rebuilt, outcomes are attached (and asserted equal to v1's target),
  tables are produced, and deterministic outputs are written to an Actions artifact (large row-level tables stay out of
  git). A later change may seal the result.

## 13. What would count as a real finding

Nothing in this study. A pattern that looks interesting becomes a hypothesis for a new preregistration, evaluated on
prospective or otherwise independent data with the multiplicity of this many views counted. Until then every label,
interval, spread and case study is a description of one outcome-exposed history.
