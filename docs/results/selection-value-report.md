# Selection-value decomposition v1

> Read-only DIAGNOSTIC on sealed replay-v16 inputs. No selector is promoted,
> production is unchanged, and no rung is a tuned variant.

## The question

`benchmark-relative-alpha-v1` closed BENCHMARK_NOT_BEATEN and proposed protecting
the calibrated challenger's +0.340pp/yr gross edge from turnover. That edge had
never been split into what stock selection earned and what lower volatility
compounded, and the share of the gap owned by the SCREEN rather than the RANKING
had never been measured at all. This ladder measures both.

## Ladder

| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Annual turnover | Avg cash | Names |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SCREEN_ONLY_RISK_WEIGHTED_NO_RANKING | 11.476% | 0.902pp | 10.574% | 13.303% | -2.729pp | 0.818 | -27.832% | 3.676x | 20.417% | 21.080 |
| SCREEN_PLUS_CONVICTION_TILT_NO_CONCENTRATION | 12.183% | 0.988pp | 11.195% | 13.671% | -2.476pp | 0.886 | -26.503% | 3.796x | 20.550% | 21.080 |
| SCREEN_PLUS_CONCENTRATION_PUBLISHED_BOOK | 12.979% | 1.386pp | 11.593% | 12.639% | -1.046pp | 0.757 | -24.563% | 4.564x | 30.515% | 4.660 |

## Where the gross gap comes from

A CAGR gap answers *which ended richer*. It does not say whether the book
picked better names or simply lost less to variance. Splitting it:

| Rung | Arithmetic selection | Compounding (volatility) | Geometric gross edge | Block sd vs benchmark |
|---|---:|---:|---:|---:|
| SCREEN_ONLY_RISK_WEIGHTED_NO_RANKING | -1.771pp | -0.056pp | -1.827pp | 0.885x |
| SCREEN_PLUS_CONVICTION_TILT_NO_CONCENTRATION | -1.501pp | 0.013pp | -1.488pp | 0.862x |
| SCREEN_PLUS_CONCENTRATION_PUBLISHED_BOOK | 0.040pp | 0.300pp | 0.340pp | 0.826x |

## Where the turnover goes

| Rung | Avg one-way | From name replacement | From weight retarget | Names carried to next block |
|---|---:|---:|---:|---:|
| SCREEN_ONLY_RISK_WEIGHTED_NO_RANKING | 30.292% | 26.693% (88.120% of it) | 3.599% | 64.970% |
| SCREEN_PLUS_CONVICTION_TILT_NO_CONCENTRATION | 31.340% | 24.985% (79.720% of it) | 6.356% | 64.970% |
| SCREEN_PLUS_CONCENTRATION_PUBLISHED_BOOK | 41.073% | 38.224% (93.060% of it) | 2.849% | 39.810% |

## Paired differences

- SCREEN_PLUS_CONVICTION_TILT_NO_CONCENTRATION minus SCREEN_ONLY_RISK_WEIGHTED_NO_RANKING: Δ annualized excess 0.253pp, 95% CI [-0.789pp, 1.274pp].
- SCREEN_PLUS_CONCENTRATION_PUBLISHED_BOOK minus SCREEN_PLUS_CONVICTION_TILT_NO_CONCENTRATION: Δ annualized excess 1.430pp, 95% CI [-3.762pp, 6.354pp].

## Selection null, per selector

A null permutes ONE ranking, so its verdict is about that ranking alone.
The sealed report publishes only the champion's; the challenger is the
selector a promotion would actually move into production.

| Selector | Verdict | Beats random on | Actual turnover | Null median turnover |
|---|---|---|---:|---:|
| champion (sealed) — `ALPHA_RANK_PER_DOWNSIDE_RISK` | INDISTINGUISHABLE_FROM_RANDOM | nothing | 56.280% | n/a |
| challenger (this run) — `CALIBRATED_EXPECTED_RETURN_PER_DOWNSIDE_RISK` | INDISTINGUISHABLE_FROM_RANDOM | nothing | 40.710% | 66.200% |

Challenger, independent-per-date draws:

| Statistic | Actual | Null mean | Null p95 | Percentile | p (beats random) |
|---|---:|---:|---:|---:|---:|
| annualizedExcessPct | -1.378 | -4.324 | 0.070 | 87.000 | 0.134 |
| informationRatio | -0.122 | -0.346 | 0.047 | 84.000 | 0.164 |
| sharpe | 0.814 | 0.521 | 0.823 | 94.000 | 0.065 |

The sealed report already tests the champion ranking against the book the same construction builds from a permuted ranking: INDISTINGUISHABLE_FROM_RANDOM on annualizedExcessPct, informationRatio, sharpe. The null book also churns more than the real one, so the real book is not a null that merely trades less.

## Reading

**BENCHMARK_NOT_BEATEN**

The published concentrated book's 0.340pp gross edge is 0.040pp of arithmetic stock selection and 0.300pp of compounding at 0.826x the benchmark's block volatility, and 93.060% of its turnover is names being replaced rather than weights retargeted. The hypothesis that followed — that the ranking is not worth that bill, so hold what the screen approved — is REFUTED by this ladder: holding the pool broadly lands at -2.729pp against the concentrated book's -1.046pp, and the arithmetic selection edge rises monotonically with how much of the ranking is used (-1.771pp -> -1.501pp -> 0.040pp).

The challenger's own null — never computed before, because the sealed report permutes the champion's score — returns INDISTINGUISHABLE_FROM_RANDOM at best p=0.065, so the ranking does not clear the pre-registered 5% bar on any statistic even though it sits far above the champion's. Two bars are being confused if that is read as the whole answer: choosing beats a permuted ranking here and the book still trails its matched benchmark, so the remaining deficit is implementation rather than ordering. Breadth is now ruled out as the remedy, which leaves the hurdle/hysteresis proposal `benchmark-relative-alpha-v1` already named — supported now by a measurement rather than by an unsplit CAGR gap. It must still be frozen before prospective observations and judged forward.

This is a diagnostic on sealed history. It is not evidence to promote a
selector, and a rung ending higher than another is not a promotion trigger.
