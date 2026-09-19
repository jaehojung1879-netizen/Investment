# Regional Rotation v1 — frozen challenger validation

Research question: does dynamic regional timing add incremental value beyond a
static combination of independently ranked US and KR portfolios?

## Freeze and status

`pipeline.regional_validation.freeze_manifest()` is the machine-readable freeze.
The existing main defaults are retained: lookback **252 calendar days**, softmax
0.05, regional capital floor 0.15. The old comment called the lookback trading days,
but the code uses `Timedelta(days=...)`; changing that would define another model.
The score is mean **gross benchmark excess** of matured 21-common-session regional
blocks. Only `decisionDate - lookback <= endDate < decisionDate` enters. A missing
score in either region produces equal weights. Final targets retain six decimals.
The first fixed evaluation anchor in each calendar quarter sets the allocation,
effective on that anchor (the old module prose incorrectly said next quarter).

Status remains **CHALLENGER**. No registry/framework, factor, optimizer, selector,
Kelly, macro or production policy is introduced. Prospective shadow evidence has
not yet been collected. Subsequent parameter changes require a separately named
challenger; historical sensitivity never changes v1.

## A / B / C and attribution

- A, Combined CHAMPION: read `portfolioReplay.headlineRows` and the published
  summary from the sealed report. Recompute research metrics on copies only;
  require exact agreement with its published metrics when the path is complete.
- B, Static 50/50: the same standalone US-only and KR-only rows as C, with fixed
  capital targets at every existing rebalance anchor. Within each block, sleeve
  values drift. Each sleeve retains its own cash/risk-budget constraints.
- C, Dynamic v1: the same rows, weighted by the frozen quarterly trailing rule.

B−A combines independent regional reranking, diversification, different effective
concentration, and induced equity/cash allocation. It **does not identify pure
reranking versus pure diversification**. C−B isolates the allocation rule on
identical sleeves, including its cash, benchmark and turnover/cost interactions.
C−A is the total architecture effect. A separate cash/cost/benchmark delta table
prevents labelling all of these changes timing alpha.

All paths use `portfolio_validation._path_metrics` and its daily KRW NAV / BOK
policy-rate proxy / FX / transaction-cost semantics. CAGR is net of costs;
annualized excess is portfolio CAGR minus its own equity/cash-matched benchmark
CAGR. Sharpe uses daily risk-free excess, not benchmark excess. Sortino uses the
root mean square negative risk-free excess across **all** daily observations.
Calmar = CAGR / absolute MDD. CVaR is the average worst 5% daily net returns.
MDD is negative; a positive ΔMDD means shallower drawdown, not deterioration.

The old blend discarded daily NAV and terminal holdings. Consequently Sharpe and
Sortino were `None`, MDD was a **block-endpoint lower bound**, and rebalance costs
used prior target weights instead of drifted terminal weights. The repair keeps
all daily NAVs and combines terminal holdings by terminal sleeve capital share.
Neither the production metric implementation nor the sealed CHAMPION changes.
Comparing an old rotation endpoint MDD with a CHAMPION daily MDD was invalid.

## Alignment and leakage protection

The runner uses the existing `replay_calendar.schedule` unchanged. Decisions use
that full predetermined schedule, not available row dates. Missing sleeves are
never rescaled into 100% of another region. Exact `(date, endDate)` matching is
shared by all three comparisons. Missing blocks are disclosed; no cash fill,
interpolation, greedy re-anchoring or unknown-interval concatenation is allowed.
The full-path headline is withheld unless all matured scheduled blocks exist.
Duplicate dates, invalid NAVs, missing RF, mismatched endpoints and dates fail
closed. An undefined ratio has an explicit reason; no zero fallback is used.

The underlying frozen replay retains its published PIT/vintage/survivorship and
production-fidelity limitations. Regional decisions add no future outcomes;
freezing a historical dataset does not make its source limitations disappear.

## Statistical uncertainty

Defaults match the existing bootstrap convention: **2,000 draws, seed 11**.
Each draw uses the same evaluation-block indices for both portfolios and every
metric. Blocks retain their entire daily sequence, risk-free path, elapsed
calendar duration and original chronological transaction costs. Costs are not
recomputed between impossible synthetic transitions, and allocation is not
retrained on shuffled history.

Two estimands are reported separately:

1. **Path difference CI:** recompute CAGR, excess, Sharpe, Sortino, MDD, Calmar and
   CVaR on jointly resampled net blocks. The point estimate is the original
   chronological path difference. The numeric resampling implementation is
   parity-tested against the unchanged production daily calculator, including
   entry-cost drawdown events.
2. **Mean paired block-metric difference CI:** calculate each matched block's
   challenger metric minus control metric, and resample those differences as
   pairs. This is the literal block contrast; its mean CAGR/MDD is **not** the
   full-path CAGR/MDD. Undefined ratios are disclosed without dropping pairs or
   conditioning a CI on valid replicates.

The block bootstrap assumes exchangeable blocks. It preserves within-block daily
dependence but not persistent regimes across blocks. MDD/Calmar intervals depend
on the synthetic ordering and are historical uncertainty diagnostics, not proof
of deployable timing. Intervals containing zero say **historical evidence is
inconclusive**. Seven metrics and three comparisons are exploratory, unadjusted
for multiple comparisons; do not turn a lone exclusion of zero into a promotion.

## Robustness

Seven pre-specified cases, no grid or best-parameter selection:

| Case | Calendar lookback | Temperature | Floor |
|---|---:|---:|---:|
| Frozen v1 | 252 | 0.05 | 0.15 |
| Short lookback | 126 | 0.05 | 0.15 |
| Long lookback | 504 | 0.05 | 0.15 |
| Low floor | 252 | 0.05 | 0.10 |
| High floor | 252 | 0.05 | 0.25 |
| Low temperature | 252 | 0.03 | 0.15 |
| High temperature | 252 | 0.10 | 0.15 |

Compare direction, CAGR/drawdown trade-off, ranges and extreme weight changes.
The full already-observed history is used for diagnostics; this is not selection
on an unopened holdout. No unused holdout is claimed and no variant is promoted.

## Deterministic execution

Code baseline: `61df7d5583c090c4ddefd77ee86560a5f366b743`.
Sealed input branch snapshot: `b71d8cb5ce21815980d28b606852f9294d43cc53`.
Frozen replay-v16 input: `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2`,
through 2026-09-14. It is independently pinned from main's code revision.

```bash
python scripts/run_regional_rotation_replay.py /path/to/sealed/ledger \
  --output /new/results/regional-validation.json \
  --markdown /new/results/regional-validation.md \
  --paths-output /new/results/regional-paths.json.gz
```

The runner checks the full sealed ledger byte hash before/after, input-manifest
hashes and report lineage. It refuses output inside the ledger (including symlink
aliases) and refuses overwriting any existing output. It makes no vendor calls.
Standalone signals are computed in memory, never written under replay-v16.

For a repeat report, `--paths-input /new/results/regional-paths.json.gz` reuses a
content-hashed checkpoint only when input, relevant config and replay-engine
hashes agree. It still reads the sealed CHAMPION and verifies the ledger invariant.
The checkpoint is an analysis cache, never a replacement sealed input or ledger.

The existing **Regional rotation analysis** workflow completed the full standalone
replays in [run 35409650292](https://github.com/jaehojung1879-netizen/Investment/actions/runs/35409650292).
Its content-hashed checkpoint is retained in `docs/results/`. Branch pushes now
recompute all metrics, CIs and sensitivities from that verified checkpoint and
require byte-identical JSON/Markdown against the checked-in report. Manual
workflow dispatch defaults to recomputing both standalone regional selections.
Both modes retain read-only permissions, the pinned ledger checkout and complete
sealed-byte verification. The ordinary Tests workflow remains intact.

The research metric wrapper corrects the inherited `riskFreeStatus=UNAVAILABLE`
label left by the legacy endpoint result dictionary, after validating the actual
daily risk-free path. Published sealed metadata remains untouched. This is a
status correction, not a change to the production Sharpe calculation.

## Results

The generated JSON and Markdown reports in `docs/results/` contain the actual
A/B/C estimates, both CI estimands, OFAT table and allocation history. Historical
validation does not authorize production promotion; new prospective periods are
still needed under the frozen rules.


## Observed interpretation (155 matched blocks, 2013-01-07–2026-09-14)

| Portfolio | Net CAGR % | Excess pp/yr | Sharpe | MDD % | Average cash % |
|---|---:|---:|---:|---:|---:|
| Combined CHAMPION | 10.338 | -3.635 | 0.744 | -29.264 | 22.461 |
| Static 50/50 | 8.661 | -2.349 | 0.801 | -19.095 | 38.662 |
| Dynamic v1 | 8.938 | -1.917 | 0.817 | -19.956 | 38.725 |

Static versus combined reduces observed drawdown by **10.168pp**, while dynamic
versus static makes it **0.861pp deeper**. Total dynamic-versus-combined reduction
is therefore **9.308pp**. The drawdown improvement appears primarily attributable
to the regional diversification/reranking architecture, rather than dynamic
regional timing. This is not pure diversification: average cash rises by about
**16.2pp**, effective holdings increase, and turnover falls. A/B/C alone cannot
separate those structural components. Static's own ΔMDD CI includes zero.

Dynamic versus static adds **0.277pp CAGR** (95% CI **[-0.557, +1.135]**),
**0.431pp annualized benchmark excess** (CI **[-0.540, +1.457]**) and **0.015 Sharpe**
(CI **[-0.071, +0.107]**). ΔMDD is **-0.861pp** (CI **[-2.565, +1.542]**).
All seven dynamic-versus-static path-difference intervals include zero:
**historical evidence is inconclusive**. The apparent gain in benchmark excess
is larger than the CAGR gain partly because the dynamic benchmark CAGR is lower.

Across baseline plus six OFAT variants, **all seven have deeper MDD than static**
(by 0.121–1.433pp). Six have positive CAGR deltas, but 126-day lookback changes the
sign (-0.025pp). Short lookback has a maximum quarterly US-weight change of 37.6pp;
low temperature reaches the 85% ceiling. There is no stable incremental drawdown
advantage and no parameter is selected as a winner. Static's CVaR improvement
versus combined excludes zero under this bootstrap, but that is evidence about
the structural blend, not timing alpha, and the tests are not multiplicity-adjusted.

The previously reported dynamic MDD around -13.1% was a block-endpoint lower
bound. Correct daily valuation gives **-19.956%**. It must not be compared with
CHAMPION's daily MDD as though both had identical semantics.

Decision: preserve the frozen v1 **CHALLENGER** for prospective shadow evidence;
do not replace CHAMPION or enable production/live execution.
