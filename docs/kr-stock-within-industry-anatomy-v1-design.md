# KR stock-within-industry anatomy v1 — preregistration and outcome-free harness

Status: `PROTOCOL_AND_HARNESS_ONLY_NO_OUTCOME_COMPUTED`.
Scientific label, everywhere: `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`.

This is anatomy. It is not a model, not a portfolio, not a selection rule and not confirmation. It cannot validate, rescue,
refute or alter `kr-model-overlay-portfolio-v1`, `kr-factor-anatomy-v1`, `kr-top120-regime-review-v1` or
`kr-industry-opportunity-anatomy-v1`, none of which is rerun, and the sealed results are pinned by hash.

## 1. Question

`kr-factor-anatomy-v1` read eleven stock features against `stock - market`. `kr-industry-opportunity-anatomy-v1` read industry
states against `industry - market`. Returns decompose exactly:

    stock - market  =  (industry - market)  +  (stock - industry)

This study asks whether the stock-factor associations survive once the contemporaneous industry component is removed, so it
reads ONLY `stock - leave-one-out industry`. The identity is an identity on returns and is asserted on every matured row; rank
correlations are not additive, so no statistic here treats the three components' correlations as a sum.

## 2. The leave-one-out industry benchmark

For stock `i` in industry `s` at signal date `t`:

* **Peers** = the classified Top120 members of `s` at `t` (frozen v4 14-group crosswalk, eligible membership statuses only) minus
  `i`. The evaluated stock is never in its own benchmark: not in the cohort, not in the weights, not in the denominator.
* **Weights (primary, `CAP_WEIGHTED`)** = signal-date market caps of the PEERS, normalised over the peers. The stock's own cap is
  not used. If any peer lacks a finite positive cap the cap lens is `INELIGIBLE_CAP_WEIGHT_UNAVAILABLE` for `i` (never partial).
* **Robustness (`EQUAL_WEIGHT`)** = the plain mean of the peers' returns.
* Cohort and weights are frozen at `t` for the whole forward window.
* A target is `MATURED` only when `i` and **every** peer have a matured return under the accepted terminal discipline (the
  sealed v1 `target_from_sessions` plus `attach_eligibility`; the harness cross-checks its own endpoints against them name by
  name). Otherwise the target is `PENDING` or `UNRESOLVED_*`. No survivor renormalisation, no survivor or successor substitution,
  no UNKNOWN fill, no zero.
* Eligibility: at least 5 classified members at `t` (so at least 4 OTHER peers). Everything else keeps a row, a status and a reason
  and stays in every denominator: `INELIGIBLE_UNCLASSIFIED` (UNKNOWN, conflict, unmapped, terminated),
  `INELIGIBLE_BELOW_MINIMUM_INDUSTRY_MEMBERS`, `EXCLUDED_BY_SENSITIVITY`.
* Entry is the next KR session strictly after `t`; exit is `H` sessions later; exact endpoints only. Horizons: **H126 primary**,
  H63 and H252 descriptive. Return basis `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS` (never price return, never
  total shareholder return); benchmark `069500.KS`. Nothing is recollected from DART, KIND or KRX.

Three components are computed on exactly the same name-dates: `STOCK_MINUS_LOO_INDUSTRY` (primary), `LOO_INDUSTRY_MINUS_MARKET`
(the industry component, for separation) and `STOCK_MINUS_MARKET` (the sealed anatomy's target, on THIS study's sample).

## 3. Features and the two lenses

The eleven features are exactly the repository's `kr_value_quality_catalyst.RAW_FEATURES` (definitions copied from the sealed factor
anatomy spec and compared with it on every load; the source file is hash-pinned): `bookToMarketProxy`, `earningsYieldProxy`,
`ocfYieldProxy`, `netIncomeToAssets`, `ocfToAssets`, `negativeAccrualsToAssets`, `relative126`, `momentum121`,
`ocfImprovementToAssets`, `negativeDownsideVol126` (higher = calmer), `logAdv60`. No feature is added, dropped or re-signed
because of any earlier outcome. `relative126` minus a within-date constant is the stock's own trailing return, so its
within-industry rank is a within-industry price-momentum rank.

* **RAW** — the registered value, ranked across the whole same-date eligible cross-section by the Spearman.
* **WITHIN_INDUSTRY_RANK** — the average-rank percentile `(r - 0.5) / n` among the finite values of the SAME signal date and the
  stock's OWN industry (the stock included), only when at least 5 finite values exist, else `NaN`. Ties share the average
  percentile, so the result does not depend on row order. Only date `t` information enters; ranks are fixed before any outcome is
  attached; a mega-cap exclusion is applied before ranking.

Both lenses and all components are evaluated on one **common sample** per feature, lens and horizon (eligible, matured, finite raw,
finite within-industry rank), so a lens difference is never a sample difference.

## 4. Statistics

Per date first; dates equal-weighted; no threshold decides anything.

**Primary.** Per signal date, the Spearman between the within-industry feature rank and the H126 `stock - leave-one-out
CAP_WEIGHTED industry` return across the common-sample stocks (at least 30). Reported: mean, median, sign fraction, valid dates,
annual values, a descriptive HAC standard error (lag `ceil(h/5)`), and the positive-year fraction over years with at least 13 dates.

**Secondary.**

* Industry-date top-vs-bottom groups: inside one industry-date, `k = floor(n/3)` stocks per outer group, `n >= 6` so each outer
  group has at least 2 stocks; ordering `(feature, ticker)`; a feature value tied across a group boundary invalidates the
  industry-date; stocks equal-weighted in a group; the spread is averaged with equal weight per industry within a date (at least
  3 industries) and then equal weight per date, so large industries do not dominate. No stock-style deciles are formed.
* Equal-industry rank correlation: per industry-date Spearman (`n >= 6`), equal weight per industry then per date. A Spearman
  inside one industry is invariant to the within-industry transform, so RAW and WITHIN give the identical value here; it is
  reported once and is the guard against the largest industry (Financials is about a quarter of eligible stock-dates) dominating
  the pooled statistic.
* H63 and H252; CAP versus EQUAL leave-one-out benchmark; the three components.
* Slices decided by outcome window (`PRE_2025_COMPLETE_WINDOW`, `TOUCHES_2025_OR_LATER`) and the signal-date market state
  (`riskMultiplier` 1.0 / 0.7 / 0.4, the repository's only past-only state).
* `logAdv60` size control: the within-industry rank of signal-date market cap is a CONTEXT variable (not a feature). Reported: the
  rank overlap of the two within-industry ranks and the pooled `logAdv60` association inside the lower and upper half of
  within-industry size; the mega-cap exclusion sensitivity addresses the mega-cap question.

**Sensitivities.** `FULL`; `EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX` (`005930.KS`, `000660.KS`, removed before cohorts, ranks and
weights). Diagnostics only: none is an alternative route and none is promoted.

## 5. Comparison with the sealed stock anatomy (interpretive)

The reference is the sealed `kr-factor-anatomy-v1` mean per-date rank correlation (stock minus market, `V1_TERMINAL_DISCIPLINE`,
H126 and H252), read from its result file and never recomputed. Because the sample differs, the same-sample stock-minus-market
reading of this study is reported beside it and the shift class is computed against both; neither is preferred.

Conventions fixed now (not tests): `|IC| < 0.01` is not read as a direction; ratio new/reference `>= 0.75` is `SURVIVES`,
`>= 0.25` `WEAKENS_MATERIALLY`, otherwise `LARGELY_ABSORBED`; a sign difference is `CHANGES_SIGN`; fewer than 52 valid dates is
`DATA_INSUFFICIENT`. Stability is the sign of the pooled mean over eight registered views (two sensitivities x two weight lenses
at H126, H63, H252, and the two outcome-window slices of the primary cell; a slice needs 26 valid dates): all positive, all
negative, or `SIGN_DEPENDS_ON_VIEW`. Nothing is called validated, predictive, confirmed, best or recommended; output keys carrying
such semantics are refused.

## 6. The five registered questions

Each question has a registered feature list and is read as a table of the registered numbers, not an answer key:

1. `bookToMarketProxy` — positive association with stock-minus-industry?
2. `relative126`, `momentum121` — informative after industry momentum is removed?
3. quality, cash-flow and improvement features — stock-specific or mostly industry?
4. `logAdv60` — still material after industry control, or size / mega-cap / composition?
5. `negativeDownsideVol126` — still regime-dependent after industry neutralisation?

## 7. Lifecycle and what this change does not do

* This change adds the frozen spec, pinned identities, the leave-one-out constructor, target builder, within-industry transform,
  statistics, coverage audit, synthetic tests and a manual workflow. Pull-request CI runs `verify`, `readiness` and synthetic
  tests only and computes no historical outcome.
* `execute` is a manual dispatch on merged `main`: committed spec at the dispatched commit, the exact preserved raw artifact (name,
  run id, artifact id, archive digest), the input identity, no committed result or marker and no execution lock. The durable
  exclusive git-tag lock (`refs/tags/kr-stock-within-industry-anatomy-v1-execution-lock` and `...-<specSha256>`, POST and GET
  only) is created after identities and gates and before the first outcome; any ref under that prefix, for any spec SHA, refuses
  execution; a failure after the lock consumes the study.
* Readiness (`READY_FOR_STOCK_WITHIN_INDUSTRY_ANATOMY_EXECUTION` or `DATA_BLOCKED_BEFORE_STOCK_WITHIN_INDUSTRY_ANATOMY`) is
  decided from identities, structure and the frozen membership alone. Signal-date cap availability of every peer and matured-return
  completeness of every peer are outcome-time facts, measured at execution and not assumed ready.

## 8. Limitations

Outcome-exposed single sample; reconstructed (not PIT-exact) industry history; peer sets of 4 to a few dozen names make the
leave-one-out benchmark noisy; weekly signals overlap; large caps only; partial-distribution return basis (banks and high-dividend
names unreliable); issue-cap accounting proxies; no multiplicity correction; terminal securities are unclassified and any peer
without a matured return makes a target unresolved; a within-industry rank removes industry composition, not size, mega-cap or
sector-cycle effects inside an industry.
