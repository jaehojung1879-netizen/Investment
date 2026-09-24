# Alpha opportunity model v1 — sealed preregistration

**Phase 1 only. BLOCKED_PREREGISTRATION. No historical labels, models, performance
metrics or portfolio simulations were computed for this study. Do not run the
model Action now; merge and review this preregistration first.** The seal freezes
an explicitly blocked design, not permission to fill economic parameters later
from results. Resolving a blocker requires a new immutable version and review
**before any outcomes**. No production component or replay history changes.

The executable contract is `research_specs/alpha-opportunity-model-v1.json`;
its adjacent `.sha256` is SHA-256 of UTF-8 JSON with sorted keys, compact separators,
no trailing newline, no NaN, and unescaped Unicode. The spec also hashes its
registry, source modules and runtime requirements. The operator must supply the
reviewed hash independently. Neither validation nor execution can reseal it.

## 1. Question and prior research

Does a stock offer a meaningful advantage over putting the same capital into its
own passive regional benchmark? Predicting a useful opportunity is different
from finding the highest score in a weak cross-section. Zero candidates is valid.
No fixed count, selected percentile, invested fraction, US/KR quota, positions or
capital allocation are defined here.

`regional-alpha-model-v1` **already executed and closed its 31-feature scope**.
Actions run 35826122755/job 107068116226, not its stale pending-execution document,
is the authority; the foundation erratum records the correction. We do not rerun
it. Its rank-heavy price transformations motivate a small magnitude-preserving
registry, two separate prediction heads, and an economic admission test. Existing
price fields supply parsimonious context; they are not another ablation of the
closed production score. The nonlinear complexity is reused, not searched.

The new information is accounting cash conversion, balance-sheet growth,
capital expenditure/share change where available, and magnitude/persistence/sign
of attention. DART is newly collected but too short for a primary claim.
`fundamental-acceleration-v1`, opportunity radar, lowvol ablations, reliability
ladders, dynamic breadth, quota removal, switch hurdle and signal persistence
remain closed. Their runners are never called. Source-only calendar/membership
and price loaders from the old regional module are reused.

The reliability research rules out arbitrary coverage-based confidence
contraction. Missingness is disclosed; it does not multiply or shrink a score.
Selection-value research also requires selection to be distinguished from market
exposure and compounding. No CAGR or portfolio path is a model-quality gate here.

## 2. Sources and what was actually verified

Baseline main: `9f5fbd38d9744df7cf09e77cb6ca2410766ad11d` (PR #153).
Source signal-history: `4ea107ed0cde289f0a049a65ff13d2441a786710`.
Replay-v16 manifest:
`f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2`,
through **2026-09-14**. Latest frozen Actions run **35980991319**, job
**107572568277**, passed schedule and cross-section stability after the PR #153
configuration-representation fix. This verifies the latest frozen incremental
prefix reproduction; it is **not a newly run double full-replay comparison**.
No replay was rerun for this PR. Reproducibility does not cure source PIT gaps.

Read against source: AGENTS, README, philosophy v2, inventory v1, foundation v2
and results/lineage/gaps, regional study and its correction, opportunity model,
reliability/persistence/selection-value research, replay manifests/provenance,
longterm, accounting, liquidity, ownership, dividend and macro modules, PIT
fundamental loaders, total-return adjustment, costs, calendars and membership.
`alpha-opportunity-model-v1-input-audit.json` distinguishes inherited coverage
from the stricter input-only KR measurement. The registry includes raw fields,
formula, availability, region, coverage denominator, missingness and model access.

US benchmark remains **SPY**; KR remains **069500.KS**, the repository's established
PIT-safe lineage. No benchmark shopping, FX allocation, cash timing or portfolio
aggregation. US membership uses the pinned upstream constituent observations
(commit `3b2bb60e6269439cd75541eded6281c48e7681d1`, deterministic export included);
KR uses strictly prior monthly KRX top-120 observations. This universe definition
is not a portfolio breadth target. Current constituents are never backfilled.
Intermediate membership changes remain intact. Former members are retained where
sources contain them; missing delisting endpoints are disclosed, never invented.

## 3. Predictions, horizons and information

Separate **US_OPPORTUNITY_MODEL_V1** and **KR_OPPORTUNITY_MODEL_V1**, only for this
study. Each outputs P(stock return > own benchmark return) and E(stock return −
own benchmark return), plus uncertainty, benchmark, timestamp, coverage/provenance,
training cutoff and model/spec identity. A probability is not an expected return.

Exactly **21 and 126 regional trading sessions** are primary. One trading month
matches attention/event decay (philosophy's 5–63 days); two quarters match quality
and leadership (126–252 and 63–126 days). Weekly cadence gives roughly five and
26 overlapping weekly labels respectively; maturity and block lengths reflect
that. No 63-day third candidate or performance-based horizon substitution.

| Region / horizon | Allowed information |
|---|---|
| US & KR, 21 | relative126; acceleration21; vol63; logVolumeShock60; shockPersistence5d; volumePriceAlignment |
| US, 126 | same six + ocfToNetIncomePct, assetGrowthPct, debtGrowthPct, capexIntensityPct, shareCountChangePct |
| KR, 126 | same six + ocfToNetIncomePct, assetGrowthPct, debtGrowthPct |

Relative leadership, disjoint short-period acceleration and realized risk are
three distinct price concepts. Attention magnitude, five-session persistence and
price alignment are the only three volume concepts. Keep their magnitude, not
within-date percentile. Momentum is short-horizon context; attention is
medium-horizon context. Accounting enters only the medium head.

US foundation coverage was measured on 30,999 derived filing rows (2011–2026):
OCF 97.39%, assets 96.39%, liabilities 96.08%, capex 83.03%, shares 78.70%.
These are **not** full universe name-date coverage. Our stricter KR input-only
audit has 4,373 raw filing observations through the cutoff: OCF 1,873, assets
3,853, liabilities 3,850, capex 305, FCF 167. None of 3,721 raw KR share records
has an independent availability date: exclude KR share change even though the
older derivation reported high coverage. No borrowing a financial statement's
receipt date for an independently collected share record.

Fixed coverage bands: broad >=80%, moderate >=20%, sparse <20%. OCF in KR has
explicit missingness; sparse KR capex/FCF are excluded. US FCF is redundant with
OCF/capex and excluded without outcome testing. Receivables, inventory and working
capital lack the necessary raw fields. Full PIT-universe annual coverage is still
unverified and blocks execution. Before labels, each evaluation region-year (2016 onward) needs >=80%
coverage for each selected price/attention field and >=20% for each selected
accounting field; failure blocks rather than silently changing the registry.

No primary US dividends: upstream integer precision can alter even event
categories, so a categorical label is not automatically a repair. All US/KR
macro inputs are excluded as **BLOCKED_MACRO_PIT** pending per-series release and
vintage proof. KR macro is also incomplete. These excluded families do not block
the remaining design. Dollar-volume/Amihud/capacity are not estimated using a
forward total-return index times volume; an actual traded-cash-value source is
required for capacity.

## 4. PIT targets and fitting

Information is available at end of signal day in the regional timezone. Date-only
filings must be strictly earlier; raw records are filtered before any fiscal-period
index/TTM derivation. Mixed KR receipt dates are rejected. Regional price histories
are reindexed to exchange sessions, without fills.

Entry is the **next regional session close**; exit is H additional sessions after
entry. This explicitly moves the old same-close outcome proxy to an executable
later close while preserving replay-v16 calendars and forward accumulated split/
distribution-adjusted total-return basis. Target = stock simple total return minus
benchmark simple total return; binary target = 1 iff this difference >0. Gross
labels contain no costs. Exact endpoints are required; holidays use repository
calendars; absent delisting/forward prices stay missing, never zero or last price.
Pending maturity is removed by calendar date alone. Missing matured members
prevent an evidence verdict for the scheduled cross-section.

Chronological expanding windows start in 2013, refit on the first regional weekly
signal of each year after 36 months, and predict weekly (last exchange session of
week). Require 104 matured training dates and >=10 names per date. Only endpoints
strictly before the fold cutoff train. This exact maturity purge is the embargo;
no future fold trains a past prediction. Unpriced training labels are excluded
with counts. Each date has total fitting weight 1, equally divided among names.

Training only: accounting signed-log1p, date-weighted median/IQR scaling, median
imputation and missing indicators. Zero IQR becomes 1. An entirely missing train
field is omitted and logged for that fold; future availability cannot activate it
inside the fold. No full-sample scaling, clipping, rank normalization or feature
selection. The same transformations serve both fixed families.

| Head | Frozen parameters |
|---|---|
| Logistic | L2, C=1, lbfgs, max_iter=2000, tol=1e-4, seed42 |
| Ridge | alpha=10, lsqr, tol=1e-6 |
| HGB classifier + regressor | learning_rate=.05, max_iter=100, max_leaf_nodes=7, min_samples_leaf=50, l2=10, early_stopping=False, max_depth=None, seed42 |

Runtime versions are pinned by repository requirements; HGB uses classifier log
loss / regressor squared error. One computation thread. Primary is linear;
nonlinear is complementary interaction evidence only. It cannot replace a failed
primary or be crowned a winner. Baselines are training-date-balanced prevalence
and mean relative return. No calibration refitting or hyperparameter search.

## 5. Opportunity and uncertainty

Training-only moving blocks: 200 refits of both linear heads, 26 whole weekly-date
clusters per block, seed42, >=104 training dates. Refit transforms per replicate.
5th–95th percentiles represent **sampling uncertainty of fitted means**, not
individual-return bounds. Separately estimate equal-date RMS of past matured OOF
residuals (>=26 dates), never in-sample residuals or future folds.

A candidate passes iff

`mu > dated round-trip cost + slippage + max(0, mu - bootstrap mean lower bound)`
`     + minimum meaningful edge + concentration-risk multiple × past OOF RMS`

and actual traded 20-session ADV exceeds the liquidity floor, with proposed trade
notional <= the specified ADV fraction. Missing uncertainty/capacity => abstain.
No names are forced through. Opportunity evidence starts with the second eligible
annual fold, after a predeclared reliability warmup.

Costs reuse `benchmark_alpha.REALISTIC_COSTS` and `_dated_cost_policy`:
`(2*commission + full spread + dated sell tax)/10000`, with the exact KR historical
schedule in the spec. Apply the known-at-signal round-trip estimate explicitly to
candidate diagnostics, not hidden in labels. This is not realized portfolio
turnover accounting. Report adjacent-date entrants/exits as candidate-set churn,
not as traded capital or a NAV.

**Unresolved, execution blocking:** minimum edge, concentration-risk multiple,
trade notional, liquidity floor, ADV fraction, slippage and an independently
sealed actual traded-value source; full-universe annual feature coverage. Existing
cost assumptions alone do not define this capital's concentration-risk budget.
No invented threshold chosen to produce desired breadth. A new version must
resolve these with non-outcome information before execution; editing this seal
is not allowed.

## 6. Evidence and stopping rules

Per region × horizon, date-balanced out-of-fold metrics: expected-return rank IC,
Brier/log-loss improvement against training prevalence, MSE improvement against
training mean, realized-on-predicted return slope, and 10 fixed probability-bin
ECE. Biases are also reported. Use 2,000 moving-block draws of **26 entire weekly
dates**, seed42, >=156 evaluation dates and >=5 annual folds. 98.75% intervals
(two-sided tails .00625) control the four primary region/horizon claims; within
one claim all gates are conjunctive. Never bootstrap stock rows independently.

**MODEL_EVIDENCE** requires all five ordering/improvement/slope lower bounds >0,
ECE upper <=.05, and >=70% of annual folds jointly positive in rank IC, Brier and
MSE improvement. It additionally requires >=52 selected-opportunity dates,
selected net-advantage lower bound > minimum edge and selected-minus-full-universe
lower bound >0, resampling the complete calendar including zero-selection dates.
Zero-selection dates are not fictitious zero returns. These are candidate-date
diagnostics; no portfolio compounding, sizes, CAGR, Sharpe or capital weights.

**NO_MODEL_EVIDENCE:** enough valid evidence but any substantive gate fails,
including no opportunities. **DATA_INSUFFICIENT:** inadequate dates/folds,
unpriced matured members, unavailable gate inputs or unmeasured reliability.
**PIT_INVALID:** invalid provenance, availability or source identity overrides
statistical claims. **MODEL_UNSTABLE:** numerical/convergence/bootstrap failure,
or aggregate quality but failure of chronological stability. No automatic
production eligibility, even for MODEL_EVIDENCE. No rerun with changed features,
horizons, thresholds or algorithm to rescue failure.

## 7. DART short history

Latest official bounded endpoint: 260 historical securities /254 issuers;
119 current securities /116 issuers; 141 historical-only securities /138 issuers;
254 queried successfully; 2,496 events; zero errors/refusals; no companies remaining.
Observed receipts **2024-09-24 through 2026-09-23**. Six preferred-share identities
remain unresolved. Completion is for mapped issuers in the currently reachable
API window, not proof that all historical filings or every security is covered.

**KR_OWNERSHIP_EXPERIMENTAL_OVERLAY_V1**: 21-session horizon; prior21-session
receipt count and sum of signs of holdingPctChange, distinct receipts, strict
receipt-date availability. No transaction-date backdating. Raw reasons/type/major
transaction fields stay raw. No inferred amendment. Full observed lookback and
issuer identity required; pre-window/unknown coverage stays missing, never zero.

Before outcomes, require >=52 training weekly dates over >=12 months, >=60 later
evaluation dates, >=200 distinct receipts and >=50 issuers. A possible later
sufficient-sample design would refit quarterly, compare matched core6 vs core6+2
linear heads on identical name-dates, use paired five-week blocks and 95% intervals,
and report exploratory evidence separately. **This sealed snapshot cannot enter
that training path:** at most 98 weekly dates after lookback, hence <=46 evaluation
dates even before label maturity/event restrictions. The harness stops it with
DATA_INSUFFICIENT. Longer history needs a new version and implementation review;
no pretending this overlay provides thirteen years or promotion eligibility.

## 8. Execution and safety

One manual-only workflow: **Alpha opportunity model v1**. It requires main, an
explicit review acknowledgement and the reviewed external seal; validation checks
run before fetching historical inputs. The blocked spec fails before labels or
models. Merged main ancestry, clean checkout, sealed code/registry/source hashes,
raw-shard allowlist, benchmark basis, coverage and calendar contracts are guarded.
Normal CLI invocation only prints readiness. Execution needs `--execute` and every
gate; changing spec/dependencies requires a new version. No automatic triggers,
auto-merge, production imports, production writes or signal-history commits.
Synthetic deterministic tests cover the contract, not historical performance.
