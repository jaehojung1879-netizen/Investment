# Alpha opportunity model v2: sealed preregistration

**Preregistration only. `READY_FOR_HISTORICAL_EXECUTION`. No historical label,
fitted model, IC, calibration table, hit rate, CAGR or portfolio path was
computed for this study.** The executable contract is
`research_specs/alpha-opportunity-model-v2.json`; its sidecar
`alpha-opportunity-model-v2.sha256` is SHA-256 of the canonical JSON (sorted
keys, compact separators, unescaped Unicode, no NaN), the same convention as v1.
The operator supplies the reviewed hash independently. Nothing can reseal it.

`alpha-opportunity-model-v1` (`e3c699b1…6dd6e`) is **unchanged**: its JSON,
sidecar, registry, harness, workflow and documents are byte-identical to the
merged PR #154. v2 re-verifies the v1 seal every time it loads, pins v1's
registry, input identities and US membership by hash, and refuses to run any
spec whose `studyId` is not v2. v1 remains the provenance record of the
earlier design. v2 supersedes it conceptually. Nothing in history is rewritten.

## 1. Why v2 exists

v1 turned "which stock ranks highest?" into "does this stock offer a
meaningful benchmark-relative opportunity?" It then blocked execution on
quantities that belong to managing a specific account rather than to that
question: a human minimum edge, a concentration-risk multiple, an order
notional, a cash-ADV floor and participation fraction, and a slippage budget.

v2 keeps the question and changes the **decision contract**. The regional
passive benchmark is an explicit competitor for the same capital, with expected
net alpha exactly 0:

```
grossExpectedAlpha_i  = E[R_i - R_benchmark(i)]              (expected-return head)
expectedNetAlpha_i    = grossExpectedAlpha_i - roundTripCost_i  (cost known at the signal)
P(net alpha_i > 0)    = P(R_i - R_benchmark(i) - roundTripCost_i > 0)   (probability head)
expectedNetAlpha_benchmark = 0
```

A universe always has a best stock. It does not always have a stock that is a
better use of capital than its benchmark. **Zero active positions is a
valid, natural outcome** (`NO_ACTIVE_OPPORTUNITY`). The number of active names
is endogenous.

## 2. The opportunity rule and why each part follows from the outside option

For each tradable name-date (LINEAR family only):

```
ACTIVE_OPPORTUNITY  iff  expectedNetAlpha > 0        and  P(net alpha > 0) > 0.5
                    and  expectedNetAlphaLower > 0   and  probabilityLower > 0.5
```

| Part | Why it is not an arbitrary threshold |
|---|---|
| `> 0` on net alpha | The benchmark is in the choice set with net alpha 0. That is the only level to beat. |
| `> 0.5` on probability | The same comparison stated for the median. A stock more likely than not to trail its benchmark net of cost is not preferred to it. 0.5 is indifference, not a conviction cutoff. |
| Both heads must agree | Mean and probability can disagree for a skewed payoff. Either disagreement leaves the default (the benchmark) in place. |
| Lower bounds | A large point estimate the model cannot distinguish from the benchmark does not move capital. The bound is v1's sealed 5th percentile of 200 training-only moving-block refits. It is not chosen here and is never swept. |

Every other name keeps its capital in the benchmark and is labelled
`BENCHMARK_PREFERRED`, `HEADS_DISAGREE_BENCHMARK_RETAINED`,
`POSITIVE_BUT_NOT_DISTINGUISHABLE_FROM_BENCHMARK`, `NOT_TRADABLE` or
`UNMEASURED`. There is no Top-N, no percentile cut, no `alpha > +X%` hurdle,
no probability cut other than 0.5, no US/KR slot, no required invested fraction
and no requirement that both regions be represented. The loader refuses a spec
that reintroduces `minimumEdge`, `concentrationRiskMultiple`, `tradeNotional`,
`portfolioValue`, `maximumAdvFraction`, `minimumAdv`, `fixedTopN`,
`regionQuota` or `investedFraction` with a value. Ranking survives only as a
diagnostic (rank IC in evidence B).

Magnitude, probability and uncertainty are published as separate fields on
every prediction: `grossExpectedAlpha`, `expectedNetAlpha`,
`probabilityNetOutperform`, `grossExpectedAlphaLower/Upper`,
`probabilityLower/Upper`, and `predictiveResidualRms` (past matured
out-of-fold dispersion, disclosed for a future portfolio layer and never used
in the decision). No Sharpe-like `alpha / uncertainty` score is formed.

## 3. Personal-scale capital: what was removed, and why

`SMALL_CAPITAL_ASSUMPTION`: individual-investor capital. Institutional
scalability is not required. Opportunities too small for large mandates
remain valid.

| v1 blocker | v2 disposition | Reason |
|---|---|---|
| `ECONOMIC_EDGE_AND_CONCENTRATION_BUDGET_UNSPECIFIED` | removed | The outside option is the economic edge. A human +X% would be an arbitrary second benchmark. Concentration risk is a sizing question. |
| `POSITION_NOTIONAL_LIQUIDITY_CAPACITY_AND_SLIPPAGE_UNSPECIFIED` | reclassified to the portfolio layer | Whether a stock beats its benchmark does not depend on account size. Spread, commission and dated tax stay in net alpha. |
| `AS_TRADED_ADV_SOURCE_CONTRACT_UNSEALED` | not required for alpha research | Cash ADV fed only the participation ceiling. |
| `FULL_PIT_UNIVERSE_FEATURE_COVERAGE_UNVERIFIED` | pre-label runtime gate | The rule is fixed here and is outcome-free. It runs on features before any label. A failure stops the run without touching the registry. |

What stays mandatory: dated realistic costs, basic PIT tradability,
survivorship eligibility and bounds, and PIT features and labels.

**Transaction costs.** v1's schedule, unchanged: round trip
`(2 × commission + full spread + sell tax) / 10000` at the signal date, from
`benchmark_alpha.REALISTIC_COSTS` via `_dated_cost_policy` (US 16.3 bp; KR 41
bp in 2013 falling to 26 bp in 2025 and 31 bp from 2026 under the dated sell-tax
schedule). The stock pays its full round trip and the benchmark pays nothing,
which errs toward the benchmark. A disclosure-only view doubles the round trip
and is never gated.

**Tradability guard (the minimal execution guard).** The name must be a
strictly-earlier PIT member (US S&P 500 observation; KR KRX top-120 by market
cap). It must also have a positive finite sealed close **and** positive
share volume on every one of the 20 regional sessions ending on the signal
date: calendar reindex, no fills. The 20-session window is v1's sealed ADV
window. The unsealed cash-value requirement is replaced by traded-at-all
evidence. Share volume is never multiplied by the forward total-return index
into a fictitious cash ADV. Tradability is a filter, never a feature.
Liquidity as predictive information would be a separately registered feature,
and it is not one here. That a personal order is small relative to these names'
traded value is an **assumption** about capital scale, not a measured
participation rate. An actual traded-value source is a portfolio-layer
obligation before sizing outside these universes or at larger size.

## 4. Signal layer versus portfolio layer

The model answers one question: which stocks beat their benchmark in expected
net value, by how much, and how uncertain is that? It never defines or
optimises how capital is split between them. Sizing, Kelly, inverse-volatility,
dependence, sector and region limits, and cash-versus-benchmark allocation are
never used to decide whether a stock has alpha. Outputs carry no `weights`,
`positions`, `NAV`, `CAGR`, `Sharpe`, `allocation` or `orderNotional`, and the
result validator refuses them. v2 modules never import `kelly_portfolio`,
`replay_valuation` or `selection_null`.

## 5. Model family, features, horizons (inherited)

The models are v1's frozen family, with no search: LINEAR (Logistic C=1, Ridge
α=10) is primary and the only family that decides. The fixed shallow HGB is
complementary only. The transforms are also v1's: training-only signed-log1p,
date-weighted median/IQR, median imputation plus indicators. So are the
horizons (21 and 126 regional sessions), the expanding annual walk-forward
with exact maturity purge, the next-close entry and the weekly cadence. Separate
US and KR models are kept because the PIT sources, calendars, costs and
benchmarks differ. Region is not a capital quota.

Two mechanics change, because v1's were incompatible with the revised decision
or were measured defective before any outcome:

1. **The probability head is trained on the NET event** `R_i − R_b > cost`,
   because the benchmark competes net of switching.
2. **Probability calibration is gated on pooled, date-balanced ECE** (v1's 10
   fixed bins and 0.05 bound). v1 averaged a per-date ECE. A perfectly
   calibrated synthetic predictor reads **0.0693** at 120 names (KR) and
   0.0342 at 500 names (US), so v1's gate rejected a calibrated KR model with
   certainty. Pooled, the same null reads 0.0010 / 0.0018. The simulated null
   is recorded in the spec and reproduced by a test. Per-date ECE stays
   disclosed.

**Allowed features** are unchanged from v1's registry, and no new feature was
found PIT-unsafe:

| Region / horizon | Features |
|---|---|
| US & KR, 21 | relative126, acceleration21, vol63, logVolumeShock60, shockPersistence5d, volumePriceAlignment |
| US, 126 | the six above plus ocfToNetIncomePct, assetGrowthPct, debtGrowthPct, capexIntensityPct, shareCountChangePct |
| KR, 126 | the six above plus ocfToNetIncomePct, assetGrowthPct, debtGrowthPct |

Re-checked for v2: sealed volume is split-adjusted **forward** from each
panel's first session, so volume ratios carry no future split. **Excluded for
PIT or data reasons (as v1 sealed them):** KR `shareCountChangePct` (none of
3,721 raw KR share records carries its own availability date), KR capex/FCF
(sparse), US FCF (redundant), receivables, inventory and working capital (raw
fields absent), cash dollar volume/Amihud (no traded-cash-value source), US/KR
macro (`BLOCKED_MACRO_PIT`), and US dividends (precision). Guru/13F holdings
are never features, and SEC access does not gate this study.

## 6. Survivorship: measured before any label

`docs/results/alpha-opportunity-model-v2-input-audit.json` intersects the pinned
US membership (829 names) with the 194 names the sealed replay-v16 panel
carries no series for. It reads identities only: no price, no return.

| US year | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2020 | 2022 | 2024 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|
| member-dates with no panel | 27.10% | 25.50% | 24.31% | 21.07% | 19.55% | 17.33% | 13.03% | 9.04% | 3.30% | 0.65% |

703 of 715 US weekly dates hold at least one member with no panel. v1 voided a
date on any missing member and required every date measured, so **v1's US leg
could only ever return `DATA_INSUFFICIENT`**. v2 replaces that with rules
inherited from the repository:

- **Region-year eligibility** for training and evaluation: the unvouched share
  (no sealed signal-date close) must be ≤ `pit_data.HISTORICAL_UNIVERSE_GAP_TOLERANCE_PCT`
  = 20%. On the lower bound alone, US 2013–2016 are excluded. KR is measured
  at runtime from the panels, before labels.
- **Bounded endpoints:** a tradable name whose exact forward endpoint is
  missing is `MISSING_FORWARD_PRICE_OR_DELISTING`. Every gate must pass under
  **both** `OBSERVED_ONLY` (drop it) and `WORST_PLAUSIBLE` (the date's 5th
  percentile observed relative return, net label 0; `worst_case_excess`
  convention). A date with more than 20% unresolved is INCOMPLETE, and any
  INCOMPLETE evaluation date makes the cell `DATA_INSUFFICIENT`.
- **Stressed level:** the active set's realised net alpha is also stressed at
  the date's full unvouched share with its worst plausible outcome
  (`_stressed_excess` at scale 1.0).

## 7. Pre-registered evidence (per region × horizon; LINEAR; no portfolio)

Intervals use moving blocks of 26 whole weekly dates, 2,000 draws, seed 42, at
98.75% (Bonferroni over 4 claims). Within a claim every gate is conjunctive,
and conjunctive across both endpoint treatments. Name rows are never resampled
independently.

| | Gate |
|---|---|
| **A: absolute usefulness** | pooled, **not** within-date demeaned, date-balanced slope of realised on predicted relative return: lower > 0. MSE improvement over the training mean: lower > 0. Calibration-in-the-large bias is disclosed. |
| **B: direction** | equal-date rank IC lower > 0, within-date slope lower > 0 |
| **C: probability** | Brier and log-loss improvement (net label, vs training prevalence) lower > 0. Pooled ECE upper ≤ 0.05. |
| **D: vs the outside option** | on dates with ≥1 active name: realised net alpha of ACTIVE names lower > 0; same-date ACTIVE − non-active spread lower > 0 (the lesser of level and spread); survivorship-stressed level lower > 0; point estimate > 0 in each chronological half; ≥ 52 active dates. Zero-active dates stay in the resampled calendar and contribute counts, never a fictitious return. |
| **E: stability** | ≥ 70% of annual folds jointly positive in rank IC, Brier and MSE; D's halves rule. US and KR are separate claims, never pooled. No other subgroup is examined. |

Verdicts, in priority order: `PIT_INVALID` > `MODEL_UNSTABLE` >
`DATA_INSUFFICIENT` > `OPPORTUNITY_EVIDENCE` (A–E pass) >
`PREDICTIVE_EVIDENCE_BENCHMARK_PREFERRED` (A, B, C, E pass, but D fails or too
few active dates: the predictions carry information yet do not beat the
benchmark net of cost) > `NO_MODEL_EVIDENCE`. `promotionEligible` is always
false. No threshold, horizon, feature, tolerance or confidence level may be
changed after outcomes to rescue a cell.

## 8. DART ownership

Latest measured coverage, from the v1 input audit (manifest updated
2026-09-24): receipts 2024-09-24 → 2026-09-23, 2,496 events, 254 issuers.
The `majorstock.json` endpoint takes no date bounds and cannot be extended
backward. v1's calendar upper bound was 98 weekly dates, or 46 evaluation
dates, against 60 required. **Status: `PROSPECTIVE_OVERLAY_ONLY`, excluded
from historical execution.** The core KR history is not truncated, and no older
ownership history is invented.

## 9. Status and what can still stop a run

**`READY_FOR_HISTORICAL_EXECUTION`.** No design blocker remains. These
outcome-free gates run **before any label** and fail closed:

| Gate | Stops as |
|---|---|
| sealed input identity (git blob SHA-1 of every raw shard, replay manifest, no extra shards) | `BLOCKED_BY_DATA_INTEGRITY` |
| region-year survivorship eligibility (excludes years, never repairs) | via calendar depth |
| feature coverage per evaluation region-year (price ≥ 0.8, accounting ≥ 0.2, tradable denominator) | `BLOCKED_BY_DATA_INTEGRITY` |
| calendar sample depth after eligibility (≥ 5 years, ≥ 156 dates) | `BLOCKED_BY_SAMPLE_DEPTH` |

Operational risk: the v2 runner has been exercised on synthetic fixtures
only. A first real run may stop at a pre-label gate (the report says which,
with no labels) or exceed the 360-minute hosted-runner limit (no result).
Neither permits editing this spec. A fix needs a new version.

## 10. Execution

Manual only: **`Alpha opportunity model v2`**
(`.github/workflows/alpha-opportunity-model-v2.yml`). It has no schedule, push
or PR trigger. It runs only when `github.ref == refs/heads/main`. It validates
the reviewed hash against the sidecar, verifies v1 immutability and fails
closed unless READY, all before dependencies are installed or inputs fetched.
It then checks out the sealed signal-history commit, runs the synthetic
contract tests, executes, and uploads `alpha-opportunity-model-v2-results`. It
has `contents: read` only, and writes nothing to production, the site, the
ledger or signal-history. **Do not run it until this PR is reviewed and
merged.**
