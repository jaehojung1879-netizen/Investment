# Alpha opportunity model v3: sealed preregistration

**Status: `BLOCKED_BY_DATA_INTEGRITY`.** Spec
`research_specs/alpha-opportunity-model-v3.json`, seal in the adjacent
`.sha256`. No historical label, return, IC, calibration table, model fit or
portfolio path was computed for this study. There is deliberately **no v3
workflow**. `scripts/run_alpha_opportunity_model_v3.py --execute` refuses on
the sealed status before it reads any input.

## Lineage

| Version | What it is | Status |
|---|---|---|
| `alpha-opportunity-model-v1` (`e3c699b1…6dd6e`) | first opportunity preregistration | `BLOCKED_PREREGISTRATION`, never executed |
| `alpha-opportunity-model-v2` (`97c3727b…0e19`) | benchmark-as-outside-option redesign | sealed `READY`, **never historically executed** |
| `alpha-opportunity-model-v3` | separates expected value from confidence; audits survivorship in both regions; seals only the computed execution closure | `BLOCKED_BY_DATA_INTEGRITY` |

v1 and v2 are unchanged. v3 verifies both by their own spec digests and
sidecars on every load. It does not verify them through their dependency lists,
so v3 does not inherit v2's oversized seal. v3 exists only to fix three defects
found before any outcome; everything else is carried from v2 unchanged.

## 1. Expected value is the alpha question; probability and confidence are not

v2 labelled a name `ACTIVE_OPPORTUNITY` only if four conditions all held:
expected net alpha > 0, P(net alpha > 0) > 0.5, and both bootstrap lower bounds
above those values. The last three are not the outside-option comparison. They
are hidden hurdles on the existence of expected value.

A payoff with a 40% chance of +30% and a 60% chance of −8% has positive
expectation and a negative median. A positive fitted mean can have an
estimation interval that spans zero. Neither fact changes the sign of expected
value.

v3's alpha layer (`pipeline/alpha_opportunity_v3_decision.py`) has one
existence rule:

```
expectedNetAlpha = E[R_i − R_benchmark(i)] − roundTripCost_i      (benchmark: 0, cost 0)
expectedNetAlpha > 0   → POSITIVE_EXPECTED_ALPHA
expectedNetAlpha ≤ 0   → BENCHMARK_EXPECTED_VALUE_PREFERRED
(+ NOT_TRADABLE / UNMEASURED for the PIT tradability guard and invalid predictions)
```

Two separate descriptive readings are published beside the class. Neither can
change it:

- **Distribution state**, from `probabilityNetOutperform`. Note that P > 0.5
  if and only if the predicted **median** net alpha is positive. The four
  states are:
  - `EXPECTATION_POSITIVE_MEDIAN_POSITIVE`
  - `EXPECTATION_POSITIVE_MEDIAN_NOT_POSITIVE`
  - `EXPECTATION_NOT_POSITIVE_MEDIAN_POSITIVE`
  - `EXPECTATION_NOT_POSITIVE_MEDIAN_NOT_POSITIVE`
- **Uncertainty**, which is two different objects, checked in code:
  - `expectedNetAlphaLower/Upper` and `probabilityLower/Upper` come from
    `alpha_opportunity_model.prediction_uncertainty`: 200 training-only
    moving-block refits, 5th/95th percentiles of the *refitted prediction*.
    That is **fitted-value sampling uncertainty**, not an interval for the
    stock's own return. It is reported as `fittedUncertaintyState`.
  - `predictiveResidualRms` comes from `matured_residual_scale`: the RMS of
    realised minus predicted over past matured out-of-fold predictions. That
    is **predictive outcome dispersion**.

The opportunity surface is every `POSITIVE_EXPECTED_ALPHA` name, ordered by
`expectedNetAlpha` for downstream analysis only. There is no Top-N, no US/KR
quota, no invested fraction, no +X% hurdle, no probability hurdle and no
lower-bound hurdle. The loader refuses a spec that gives any of these a value.
An empty surface is `NO_POSITIVE_EXPECTED_ALPHA`. Risk preference, sizing,
confidence weighting, Kelly, volatility targeting and dependence all belong to
a later portfolio layer, which v3 does not define.

**Carried unchanged from v2:**
- model family: Ridge expected-return head, Logistic net-event probability
  head, fixed shallow HGB used as a complement only; no search
- feature registry
- horizons: 21 and 126 sessions
- transforms, dated costs and the PIT tradability guard
- inference scheme

No feature was found PIT-unsafe. No DART ownership, Guru/13F or macro input is
used.

**Pre-registered evaluation, for a future version with repaired inputs:**

| | What it tests | Requirement |
|---|---|---|
| **A** | Absolute calibration: `realised = a + b·predicted`, date-balanced, pooled, not demeaned within date | b lower bound > 0; MSE improvement over the training mean |
| **B** | Ordering | rank IC and within-date slope |
| **C** | Probability head | Brier, log-loss and pooled ECE |
| **D** | The direct test of the outside option, on names predicted positive | realised net alpha lower bound > 0, AND its spread over non-positive names on the same date > 0 |
| **E** | Stability | as in v2 |

For D, the slope inside the positive region and within-date terciles of the
prediction are also disclosed, without gating. The median-negative and
interval-spanning-zero subsets are disclosed separately. No threshold other
than 0 is ever evaluated.

## 2. Survivorship: both regions audited from sealed identities alone

`docs/results/alpha-opportunity-model-v3-survivorship-audit.json` is produced by
`scripts/audit_alpha_opportunity_v3_survivorship.py` from signal-history commit
`4ea107e` (replay-v16 manifest `f0781292…`, through 2026-09-14). Two runs gave
byte-identical output. It reads only three things:

- whether a positive close or volume exists on a date
- membership snapshots
- whether any corporate event is recorded for a name

It computes no returns.

### US: blocked, with no defensible repair and no structural cutoff

| Fact (pinned S&P 500 membership, weekly, strictly-earlier snapshot) | Value |
|---|---|
| names ever members / currently members / departed | 828 / 503 / 325 |
| names with no sealed price panel | **195 — all departed; 0 current** (P = 60% for departed, 0% for current) |
| priced symbols whose panel is not the member's own history (first close after last membership date: symbol reuse, e.g. FB, LB, STI, APC, NFX) | 30 |
| departed members with their own history | 100 of 325 |
| **securities in the panel that ever stop trading** | **0 of 633** |
| missing forward endpoints among tradable member-dates | **0** of 296,768 (21-day) / 285,810 (126-day) |
| longest gap between membership observations | 769 days (2018-04 → 2020-05) |

| Year | 2013 | 2015 | 2017 | 2019 | 2021 | 2023 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| member-dates with no panel | 27.1% | 24.3% | 19.5% | 16.6% | 9.5% | 4.8% | 2.2% | 0.65% |
| + panel without a signal-date close | 5.8% | 5.3% | 3.3% | 2.3% | 1.3% | 0.7% | 0.6% | 0.5% |

**The US panel contains no failed or acquired company at all.** A departed name
is present only if its symbol still trades today. The missingness is therefore
not random: it is conditioned on the future, because the name delisted and the
vendor dropped it.

**The endpoint stress was never a repair.** v2's worst-plausible endpoint stress
had nothing to act on here (0 missing endpoints). The missing companies never
contributed features, training rows or evaluation rows, and an endpoint bound
acts only on names that are in the sample.

**No source can restore them.** The sealed panels are Yahoo unadjusted plus
actions. `docs/us-delisted-prices-source.md` measured the alternatives:
polygon and FMP are paid-plan only, stooq is bot-blocked and finnhub is
unusable. Buying a vendor is a human budget decision.

**No window can be restricted to.** The departed-only missingness declines
smoothly and is nonzero in every year, including 2026, and no year is clean.
A cutoff would be a tolerance choice, not a structural break. v2's reuse of
the repository's 20% tolerance, which was built for a different gate, is
withdrawn.

### KR: coverage is complete; one lineage defect remains

| Fact (KRX KOSPI top-120, monthly, strictly-earlier snapshot) | Value |
|---|---|
| names ever members / current / departed | 260 / 120 / 140 |
| names with no panel | **0** (all 140 departed members priced) |
| securities that stop trading inside the sample (delistings observed to the last session) | 22 |
| **terminated names with any dividend event** | **0 of 22** vs 215 of 238 continuing names |
| tradable member-dates on terminated names without dividend lineage | 3.74% (7.93% in 2013 → 0.76% in 2025) |
| missing forward endpoints (all on terminated names) | 22 (21-day) / 300 (126-day) |
| tradable member-dates | 98.3–99.8% per year |
| membership | one missing month (2017-10), longest gap 61 days |

KR membership comes from KRX's own daily trade records, which include
later-delisted names. The prices come from the same source. So KR has none of
the US defects.

It does have one. KR distributions come from Yahoo actions, and Yahoo does not
carry delisted KR tickers. The 22 terminated names are therefore on a
price-return basis, while survivors and the 069500.KS benchmark are on a
total-return basis. Those 22 include regular dividend payers such as 000030
우리은행 and 000060 메리츠화재. The effect is that labels on exactly the names
that later leave are understated by their dividend yield. Terminal
consideration in share swaps is also not modelled.

This is repairable by a data-foundation build, not in a preregistration: DART
dividend disclosures for the 22 issuers, from the same vendor, key and
receipt-date PIT mechanism already used, sealed before any outcome.

### What remains defensible

**Nothing, for the registered claim.** US cannot be repaired from any allowed
source, and has no structural sub-period. KR is one named data build away.

A KR-only study would be a change of scope. It needs its own reviewed version
after that build, and is not decided here.

## 3. The dependency closure is computed, minimal and enforced

v2 sealed 51 files. Among them were `kelly_portfolio`, `longterm`,
`replay_valuation`, `selection_null` and `portfolio_validation`, which arrived
through two paths:
- a lazy import of `portfolio_validation`, used only for the 15-line
  `_dated_cost_policy`
- `alpha_opportunity_features → regional_alpha_features → historical_replay → longterm`

None of their functions is called on the research path. A production
portfolio edit would still have stranded v2.

v3 (`pipeline/alpha_opportunity_v3_spec.py`) recomputes the closure on every
load. It walks the pipeline imports, both top-level and inside functions,
starting from three entry points:
- `scripts/run_alpha_opportunity_model_v3.py`
- `scripts/audit_alpha_opportunity_v3_survivorship.py`
- `pipeline/alpha_opportunity_v3_decision.py`

The sealed file set must equal that closure plus the declared data inputs.
Currently that is 21 files:

- **13 code files:** `pipeline/__init__.py`, `alpha_opportunity_spec`,
  `alpha_opportunity_v3_decision`, `alpha_opportunity_v3_spec`,
  `alpha_opportunity_v3_survivorship`, `historical_store`, `market_dates`,
  `pit_data`, `price_adjustment`, `replay_calendar`, `replay_inputs`, and the
  two scripts.
- **8 data files:** the audit, the v1 and v2 specs with their sidecars, the v1
  feature registry, the pinned US membership, and `requirements.txt`.

The effects:
- A new import added without resealing raises `DEPENDENCY_CLOSURE_CHANGED`.
- Editing a sealed file raises `SEALED_DEPENDENCY_CHANGED`.
- Editing `kelly_portfolio`, `longterm`, `replay_valuation`, `selection_null`
  or `portfolio_validation` changes nothing.

The dated cost lookup is restated in the decision module, and a test proves it
identical to `portfolio_validation._dated_cost_policy`.

Future historical inputs drop the DART ownership shards (a prospective overlay),
`pit-*.jsonl`, collector bookkeeping and `data/us-unpriced-members.json`. The
feature path does not read them. They are recorded as documented adjacent
datasets, not execution dependencies.

## 4. Scope

v3 is a conservative baseline opportunity model. It does not test interactions
of fundamental state, fundamental change, liquidity shock, price leadership,
investor flow and event context. The shallow challenger gives limited
interaction diagnostics only. Neither this blockage nor any future failure of
this model says anything about those hypotheses.

## 5. What would unblock a successor version

**US:** a delisted-inclusive, identity-keyed price source for the 195 no-panel
names and the 30 symbol-reused ones. Because the defect is that a whole class
of company is absent, not that a small share of name-dates is missing, partial
recovery is not enough.

**KR:** a sealed DART dividend lineage for the 22 terminated issuers.

In either case the operator should also refrain from running
`Alpha opportunity model v2`. Its US leg would train and evaluate on this
survivor-only sample.
