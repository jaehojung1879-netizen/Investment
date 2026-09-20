# Signal persistence v1

> Read-only research CHALLENGER on sealed replay-v16 inputs. No selector is
> promoted and production is unchanged.

## The question

`regional-switch-hurdle-v1` saved 0.270pp of cost drag and gained 2.157pp of
arithmetic stock selection. Holding a name longer cannot make the name better,
so the finding was about the SIGNAL: chasing each block's top-ranked name was
destroying gross return. This asks that directly.

## Diagnostic: are the ranking's newest picks its worst ones?

At every rebalance the book's names divide into those it just ADDED and those
it RETAINED. Both were chosen by the same ranking on the same date under the
same constraints; only incumbency separates them. The paired figure is the
within-rebalance difference, so it carries no market-timing term.

- ADDED realised **-0.357%** mean 21-session benchmark excess over 449 name-blocks.
- RETAINED realised **0.980%** over 273.
- Paired ADDED minus RETAINED: **-1.331%** per block, 95% CI [-3.029%, 0.174%] over 131 rebalances.

| Region | ADDED mean | RETAINED mean | Difference |
|---|---:|---:|---:|
| KR | -0.710% | 0.230% | -0.940% |
| US | 0.008% | 2.791% | -2.784% |

## Is there room to smooth?

A name's alpha percentile moves a mean of **1.146** points between consecutive blocks it appears in (median 1.000, p90 3.000, 3276 observations). A ranking that barely moves leaves smoothing nothing to do.

## Ladder: rank on the signal averaged over the span it forecasts

One axis. No hurdle, same cadence, same caps, same cash floor, same costs.
`k=6` is the forecast horizon in blocks (126 sessions / 21); `k=3` is the
midpoint to the control. Neither is swept.

| Rung | k | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RANK_ON_LATEST_ALPHA_PERCENTILE | 1 | 13.564% | 1.404pp | 12.161% | 12.845% | -0.684pp | 0.853 | -25.158% | 4.679x |
| RANK_ON_MEAN_ALPHA_PERCENTILE_OVER_3_BLOCKS | 3 | 14.181% | 1.387pp | 12.794% | 12.733% | 0.061pp | 0.869 | -24.519% | 4.617x |
| RANK_ON_MEAN_ALPHA_PERCENTILE_OVER_6_BLOCKS | 6 | 16.519% | 1.427pp | 15.092% | 12.802% | 2.289pp | 1.050 | -24.287% | 4.625x |

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Geometric gross edge |
|---|---:|---:|---:|
| RANK_ON_LATEST_ALPHA_PERCENTILE | 0.315pp | 0.405pp | 0.719pp |
| RANK_ON_MEAN_ALPHA_PERCENTILE_OVER_3_BLOCKS | 1.137pp | 0.310pp | 1.448pp |
| RANK_ON_MEAN_ALPHA_PERCENTILE_OVER_6_BLOCKS | 2.994pp | 0.723pp | 3.717pp |

### Paired differences against the control

- RANK_ON_MEAN_ALPHA_PERCENTILE_OVER_3_BLOCKS minus RANK_ON_LATEST_ALPHA_PERCENTILE: Δ annualized excess 0.745pp, 95% CI [-4.042pp, 5.158pp].
- RANK_ON_MEAN_ALPHA_PERCENTILE_OVER_6_BLOCKS minus RANK_ON_LATEST_ALPHA_PERCENTILE: Δ annualized excess 2.974pp, 95% CI [-0.348pp, 6.906pp].

## Smoothing AND the switch hurdle, reported separately

This moves TWO axes at once, so its number cannot be attributed to
either. It is here because the combination is what a production rule
would actually be, not because it belongs in the ladder.

- Net excess **3.560pp**, Sharpe 1.115, MDD -22.560%, turnover 3.506x.
- Against the ladder control: Δ 4.244pp, 95% CI [0.233pp, 8.712pp].

## Reading

**BENCHMARK_BEATEN**

Newly added names realised -0.357% against 0.980% for names the book already held; paired within rebalance the difference is -1.331% with 95% CI [-3.029%, 0.174%], which contains zero. Averaging the ranking over the span it forecasts moves net excess from -0.684pp (k=1) to 0.061pp (k=3), 2.289pp (k=6).

Every ordering is read against its paired interval; one that spans zero is not a finding. The diagnostic and the ladder are separate claims — the first is about the ranking's newest opinions and holds whatever the ladder does, the second is about a rule and does not. Nothing here is prospective evidence, and the smoothing-plus-hurdle number moves two axes and is attributable to neither.

A rung ending higher than another is a point estimate on sealed history.
It is not evidence to promote a selector.
