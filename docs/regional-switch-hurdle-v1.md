# Regional switch hurdle v1

## Research question

`selection_value` established that the deficit to the matched benchmark is an
implementation cost rather than an ordering failure, and ruled out breadth as
the remedy. One lever was left: **replace an incumbent only when the improvement
covers what the swap costs** — priced in the region where it is actually paid.

Read-only research **CHALLENGER** on the sealed replay-v16 ledger. It promotes
nothing and leaves CHAMPION, production selection, Kelly, macro policy,
`paperTrading` and `liveValidated` unchanged.

## Why the regions cannot be pooled

A buy pays commission plus half the spread. A sell pays that plus the statutory
transaction tax, and in Korea that tax has run 30bp down to 15bp across the
replay. Off the dated schedule:

| Year | US round trip | KR round trip | KR / US |
|---|---:|---:|---:|
| 2013 | 0.163% | 0.410% | 2.52x |
| 2019 | 0.163% | 0.360% | 2.21x |
| 2023 | 0.163% | 0.310% | 1.90x |
| 2026 | 0.163% | 0.310% | 1.90x |

A single pooled cost rate under-protects the expensive market and over-protects
the cheap one. The hurdle therefore credits an incumbent the **sell cost of its
own region** and charges a challenger the **buy cost of its own region** — the
same split `portfolio_validation._turnover_cost` charges the realised path, so
the bar a decision clears is the bill that decision will actually pay.

## What varies, and the control

Three rungs. Cadence stays at every 21-session block, caps and the cash floor
stay production, and there is no positive-alpha cash gate —
`benchmark-relative-alpha-v1` moved cadence, a cash gate and the weighting rule
together, and its 1.4pp gross loss could not be attributed to any of them.

| Rung | The replacement decision must clear |
|---|---|
| `NO_HURDLE_CONTROL_SAME_LOOP` | nothing. **The control.** |
| `SWITCH_HURDLE_ROUND_TRIP_COST` | the swap's own friction |
| `SWITCH_HURDLE_ROUND_TRIP_COST_PLUS_ONE_STANDARD_ERROR` | that, plus one standard error of the bucket estimate |

`k = 1` standard error is fixed a priori — the natural unit of "the gap is
bigger than the noise behind it", never swept.

**The control is the point of the design.** This loop is not
`portfolio_replay`: it follows `benchmark_alpha` and builds its
`ExpandingBucketCalibration` on **gross** excess returns rather than the
cost-adjusted default, because a rule that subtracts costs itself must not be
handed an alpha with them already removed. The two therefore rank on different
quantities, and the control lands at **-0.684pp** against the published
challenger's **-1.046pp**. That 0.362pp is a harness difference and **must not
be attributed to the hurdle**, which is why every rung is paired against the
control and never against the published path.

## Result

| Path | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Published challenger | 12.979% | 1.386pp | 11.593% | 12.639% | -1.046pp | 0.757 | -24.563% | 4.564x |
| **Control** (no hurdle) | 13.564% | 1.404pp | 12.161% | 12.845% | **-0.684pp** | 0.853 | -25.158% | 4.679x |
| **Cost hurdle** | 15.963% | 1.133pp | 14.830% | 12.757% | **+2.072pp** | 1.057 | -22.311% | 3.567x |
| Cost + 1 SE | 14.867% | 0.814pp | 14.053% | 13.553% | +0.500pp | 0.848 | -35.036% | 2.814x |

Paired against the control:

- **Cost hurdle: Δ +2.757pp, 95% CI [+0.122, +5.732]** — excludes zero.
- Cost + 1 SE: Δ +1.185pp, 95% CI [-6.814, +10.263] — contains zero.

This is the first path in this project to post positive net excess against its
matched benchmark, and the first paired interval to clear zero. Sharpe and
drawdown move with it (0.853 → 1.057, -25.2% → -22.3%), so it is not return
bought with risk.

**More hysteresis is not better.** The SE rung trades least (2.814x) and gives
back most of the gain, with a drawdown of -35.0% — deeper than anything else in
the table. Over-restricting the book leaves it stuck in names it should have
left.

## Two things the rule did not do for the reasons given

**It did not protect the expensive market more.** Korea's credit is three times
America's, so Korean positions should have become the stickier ones. Measured
against the control they did the opposite:

| Path | US retention | KR retention |
|---|---:|---:|
| Control | 41.2% | 53.2% |
| Cost hurdle | **88.0%** (+46.8pp) | **62.9%** (+9.7pp) |

A credit is spent against the **gap between the names competing for the slot**,
not against zero, so what decides whether it flips an ordering is the dispersion
of expected alpha inside that region rather than the size of the credit. Korea
also runs at its `maxNamesPerRegion` cap — roughly three of twelve pool names
held against America's one or two — so a Korean incumbent faces more internal
competition per rebalance. The cost asymmetry is real; "the expensive market
gets protected more" was an assumption and it did not survive.

**And the gain is not the fee saving it was designed to collect.** Against the
control:

| Path | Cost drag saved | Arithmetic stock selection gained |
|---|---:|---:|
| Cost hurdle | 0.270pp | **2.157pp** |
| Cost + 1 SE | 0.590pp | 1.441pp |

Eight times more of the improvement comes from the book **holding names longer**
than from the fees it avoids. Chasing each month's top-ranked name was
destroying gross return, and the hurdle stopped that as a side effect of being
designed for something else.

A rule that works for a reason its author did not predict is weaker evidence
than one that works for the stated reason. It suggests the real finding is about
the **persistence of the calibrated alpha estimate** — that last month's ranking
is noisier than the position it displaces — and that is a hypothesis about the
signal, not about costs. It has not been tested here.

## Regional attribution

`excessByRegion` sums to `grossExcessReturn`, so these rebuild the headline
rather than approximating it. Sleeve figures are weight-normalised.

| Path | Region | Avg weight | Contribution | 95% CI |
|---|---|---:|---:|---|
| Control | KR | 49.8% | -0.467pp | [-7.272, +5.743] |
| Control | US | 19.8% | +0.781pp | [-1.178, +2.922] |
| Cost hurdle | KR | 50.7% | +0.335pp | [-6.071, +6.309] |
| Cost hurdle | US | 18.5% | +2.136pp | [-0.261, +4.599] |

Every regional interval spans zero except the cost hurdle's **US sleeve excess**
(+14.057pp weight-normalised, 95% CI [+0.731, +27.762]). On 155 blocks split two
ways these locate where to look; they do not establish that one region's ranking
works and the other's does not.

## What this is not

- **Not a promotion.** `promotionEligible` stays `False` and no prospective
  shadow evidence exists. The repository's gate requires the selection null to
  clear on the selector being promoted, and the calibrated challenger's null
  returns `INDISTINGUISHABLE_FROM_RANDOM` at best p=0.065.
- **A thin interval.** The cost rung's lower bound clears zero by 0.122pp, on
  one historical sample, after several rungs have been looked at across two
  studies, with no correction for that multiplicity.
- **A historical result.** Nothing here may move production. The rule must be
  frozen as it stands and judged on observations that arrive after it was
  written down.

## Reproduction

```
python scripts/run_switch_hurdle_replay.py <sealed-ledger> \
  --output switch-hurdle-report.json --markdown switch-hurdle-report.md
```

`.github/workflows/switch-hurdle.yml` checks out sealed commit
`b71d8cb5ce21815980d28b606852f9294d43cc53` read-only, runs the tests, verifies
the ledger tree digest is unchanged before and after, and `cmp`s against the
checked-in result. The runner refuses to write inside the ledger and refuses to
overwrite an existing artifact. Two runs produce byte-identical reports.
