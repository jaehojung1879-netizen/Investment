# Lowvol alpha separation v1

> Read-only research CHALLENGER on sealed replay-v16 inputs. The selection
> score's downside-volatility denominator, inverse-volatility sizing, the entry
> multiplier, the research pool, every cap and `evidenceCoverage` itself are
> unchanged and IDENTICAL on both rungs. `promotionEligible: false`,
> production unchanged.

## The one axis

| Rung | Alpha |
|---|---|
| `CONTROL_FOUR_FACTOR_ALPHA` | 0.3 momentum + 0.25 value + 0.25 quality + 0.2 lowvol |
| `NO_LOWVOL_IN_ALPHA` | 0.375 momentum + 0.3125 value + 0.3125 quality |

The challenger's weights are production's own 30:25:25 renormalized to sum to
one — derived from `longterm.FACTOR_WEIGHTS` at import, not fitted. No weight
sweep was performed.

## Read this first: the harness difference

Production blends sleeve **z-scores**. The sealed ledger stores only each
sleeve's **percentile**, so production's exact alpha arithmetic is unreachable
from sealed inputs — verified, not assumed. Both rungs therefore blend
percentiles, which keeps the axis between them exactly one thing but means this
harness's control is **not** the published path:

- Rank correlation of this control's `alphaPercentile` to the published one: **0.906** (median 0.901, p10 0.848) over 1430 cross-sections
- Exact percentile match: **5.843%**

Per `switch-hurdle-v1`: a ladder carries its own control, and the control's own
gap to the published path is published beside it. That is this section.

## The ladder

| Rung | Gross CAGR | Cost drag | Net CAGR | Benchmark | Net excess | Vol | Sharpe | MDD | Turnover | Avg cash | Names |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CONTROL_FOUR_FACTOR_ALPHA | 12.989% | 1.482pp | 11.507% | 13.154% | -1.647pp | 12.550% | 0.774 | -27.651% | 4.887x | 29.325% | 4.658 |
| NO_LOWVOL_IN_ALPHA | 11.216% | 1.709pp | 9.507% | 14.063% | -4.556pp | 13.687% | 0.588 | -31.733% | 5.729x | 26.951% | 4.658 |

**Paired difference (no-lowvol minus control): -2.909pp, 95% CI [-9.194pp, 3.417pp] over 155 paired blocks.**

Verdict: **DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED**

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |
|---|---:|---:|---:|---:|
| CONTROL_FOUR_FACTOR_ALPHA | -0.355pp | 0.190pp | -0.165pp | 0.859x |
| NO_LOWVOL_IN_ALPHA | -2.565pp | -0.282pp | -2.847pp | 0.967x |

## Factor profile of the names the rungs disagree about

145 rebalances; 386 held name-dates agreed, 336 disagreed.

| Sleeve / metric | Challenger-only | Control-only |
|---|---:|---:|
| momentum | 87.458 | 79.583 |
| value | 70.578 | 56.708 |
| quality | 77.209 | 75.417 |
| lowvol | 55.934 | 81.345 |
| downside volatility | 29.967 | 22.431 |
| alpha percentile | 92.461 | 94.696 |
| calibrated expected excess | 0.268 | 0.565 |

### Realised forward benchmark excess — EVALUATION ONLY

| | Challenger-only | Control-only |
|---|---:|---:|
| Name-dates | 336 | 336 |
| Mean block excess | -0.076% | -0.077% |
| Win rate | 47.020% | 49.400% |
| 95% CI | [-1.22, 1.037] | [-1.059, 0.927] |

Fitted to nothing. No rule, score or ranking reads it.

## Sector exposure

| Sector | Control share | Challenger share | Delta |
|---|---:|---:|---:|
| Technology | 4.570% | 7.890% | +3.32pp |
| Financials | 8.170% | 10.110% | +1.94pp |
| Industrials | 9.560% | 11.220% | +1.66pp |
| Unclassified | 29.500% | 30.610% | +1.11pp |
| Utilities | 0.550% | 0.420% | -0.13pp |
| Communication Services | 3.880% | 3.460% | -0.42pp |
| Energy | 3.460% | 2.910% | -0.55pp |
| Holding | 1.110% | 0.550% | -0.56pp |
| Consumer Discretionary | 8.030% | 7.340% | -0.69pp |
| Materials | 7.200% | 6.370% | -0.83pp |
| Health Care | 9.830% | 8.170% | -1.66pp |
| Consumer Staples | 14.130% | 10.940% | -3.19pp |

## Boundary diagnostic

| Reading | Control | No-lowvol |
|---|---:|---:|
| Cuts tied on expected alpha | 59.440% | 48.940% |
| Median relative score gap at cut | 0.110 | 0.130 |
| Median expected-alpha gap at cut | 0.000pp | 0.000pp |
| Incumbent retention | 38.770% | 35.560% |

## EXPLORATORY stacks — outside the ladder

Each row below moves MORE THAN ONE axis and is attributable to NONE of
them individually. None is paired into the primary ladder and none is
the lowvol sleeve's independent effect.

| Stacked path | Axes moved | Net excess | Arithmetic selection | Sharpe | MDD | Avg cash | vs control |
|---|---:|---:|---:|---:|---:|---:|---:|
| EXPLORATORY_NO_LOWVOL_PLUS_PERSISTENCE_K6 | 2 | -3.528pp | -1.463pp | 0.603 | -41.035% | 26.875% | -1.881pp [-8.915pp, 5.280pp] |
| EXPLORATORY_NO_LOWVOL_PLUS_ENTRY_AT_WEIGHT | 2 | -2.259pp | -1.362pp | 0.418 | -21.505% | 60.552% | -0.612pp [-6.659pp, 5.642pp] |
| EXPLORATORY_NO_LOWVOL_PLUS_PERSISTENCE_K6_PLUS_ENTRY_AT_WEIGHT | 3 | -1.878pp | -1.010pp | 0.411 | -18.319% | 61.311% | -0.231pp [-6.034pp, 5.907pp] |

### Combined interpretation: **CASE D — keep the lowvol sleeve for now**

Net excess moves -2.909pp and the paired interval contains zero, arithmetic stock selection does not improve, and no stacked path changes that reading in a way attributable to this axis. The sleeve is not shown to be suppressing selection alpha. Research attention belongs on signal persistence and role separation, and above all on the calibration resolution `alpha-reliability-v1` named as the bottleneck.

## Q1–Q10

**Q1. Lowvol sleeve를 alpha에서 제거했을 때 Net benchmark excess는 어떻게 변했는가?**

-1.647pp -> -4.556pp. Paired difference -2.909pp, 95% CI [-9.194pp, 3.417pp] over 155 blocks. Verdict: **DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED**.

**Q2. 그 변화는 arithmetic stock selection 개선인가, compounding / volatility effect인가?**

Arithmetic stock selection -0.355pp -> -2.565pp; compounding 0.190pp -> -0.282pp; block sd ratio 0.859x -> 0.967x. This is the primary mechanism metric: it separates picking better names from merely running a different volatility profile.

**Q3. Control-only와 Challenger-only 종목의 Momentum / Value / Quality / Lowvol profile은 어떻게 달라졌는가?**

On the 336 disagreed name-dates — challenger-only vs control-only: momentum 87.458 vs 79.583, value 70.578 vs 56.708, quality 77.209 vs 75.417, lowvol 55.934 vs 81.345, downside volatility 29.967% vs 22.431%.

**Q4. Challenger가 더 많은 high-momentum / high-quality / high-volatility 종목을 선택했는가?**

Sleeve gaps (challenger-only minus control-only): momentum +7.875, value +13.871, quality +1.792, lowvol -25.411; realised downside volatility +7.536pp. So the names the challenger took are MORE volatile than the ones it dropped, and its momentum edge over them is +7.875 percentile points with quality +1.792. Whether that trade paid is Q6, and whether it paid for a reason this study tested is Q2 — the profile alone establishes neither.

**Q5. Technology 및 growth-sensitive sectors의 selected exposure가 실제로 증가했는가?**

Technology share moved +3.32pp. Largest increases: Technology +3.32pp, Financials +1.94pp, Industrials +1.66pp. Largest decreases: Consumer Staples -3.19pp, Health Care -1.66pp, Materials -0.83pp. A larger technology share DESCRIBES what removing the sleeve did; it is not evidence that holding more technology is better.

**Q6. 새로 선택된 종목의 subsequent benchmark-relative return은 기존에 밀려난 종목보다 나았는가? (descriptive only)**

Challenger-only names realised -0.076% mean forward block excess (win rate 47.020%, n=336) against control-only -0.077% (win rate 49.400%, n=336); difference of group means 0.001pp. DESCRIPTIVE ONLY — a difference of two group means, not a paired test, fitted to nothing.

**Q7. Portfolio volatility와 MDD는 얼마나 변했고, 기존 downside-risk denominator + inverse-vol sizing이 그 위험을 충분히 흡수했는가?**

Held-name downside volatility is the input risk; portfolio realised volatility 12.550% -> 13.687%, MDD -27.651% -> -31.733%, Sharpe 0.774 -> 0.588, average cash 29.325% -> 26.951%. The denominator and inverse-vol sizing are identical on both rungs, so whatever risk moved is what they did NOT absorb.

**Q8. Lowvol sleeve 제거가 top-5 boundary의 tie / instability를 개선했는가?**

Cuts tied on expected alpha 59.440% -> 48.940%; median relative score gap at the cut 0.110 -> 0.130; incumbent retention 38.770% -> 35.560%; one-way turnover 4.887x -> 5.729x. The tie rate is a property of the CALIBRATION's coarse buckets, which this axis does not touch, so a large move here would be surprising rather than expected.

**Q9. 이 결과를 근거로 lowvol을 production alpha에서 제거할 수 있는가?**

No. Verdict is DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED, and three separate caveats stack on top of it. (1) This harness blends stored sleeve PERCENTILES because the sealed ledger has no z-scores, so its own control reproduces the published ranking at a rank correlation of only 0.906 — the ladder is internally consistent but is not the production path. (2) This is one historical sample with no multiplicity correction, after nine studies on this ledger. (3) No permutation null was run, so no rung here may be described as beating random. A single favourable interval would still not be a promotion, and this one is not even that.

**Q10. 현재까지 모든 연구를 종합했을 때 가장 유망한 구조는 무엇인가?**

Current control (four-factor, this harness): net excess -1.647pp, arithmetic selection -0.355pp (1 (baseline) axis/axes); No-lowvol alpha (this study): net excess -4.556pp, arithmetic selection -2.565pp (1 axis/axes); EXPLORATORY_NO_LOWVOL_PLUS_PERSISTENCE_K6: net excess -3.528pp, arithmetic selection -1.463pp (2 axis/axes); EXPLORATORY_NO_LOWVOL_PLUS_ENTRY_AT_WEIGHT: net excess -2.259pp, arithmetic selection -1.362pp (2 axis/axes); EXPLORATORY_NO_LOWVOL_PLUS_PERSISTENCE_K6_PLUS_ENTRY_AT_WEIGHT: net excess -1.878pp, arithmetic selection -1.010pp (3 axis/axes). Published elsewhere on this same ledger: signal-persistence-v1's k=6 (favourable point estimate, CI contains zero) and entry-selection-separation-v1 (+2.069pp, 95% CI [-1.881, +6.061], contains zero, achieved partly by roughly doubling average cash to 56.0%). RANKING THESE BY CAGR WOULD BE THE WRONG READING. Every interval this programme has produced contains zero, so no path is statistically distinguished from the control; the multi-axis rows above are attributable to none of their axes individually; and the one path with a large point estimate bought it with a structurally different cash profile rather than with demonstrably better names. On mechanism clarity the honest summary is that the single-axis studies have repeatedly failed to separate, which points at the calibration's two-bucket resolution — named as the bottleneck by alpha-reliability-v1 — rather than at any of the axes tried since.

## What this study does NOT establish

- Not a promotion. `promotionEligible` is false and no permutation null
  was run, so no rung here may be described as beating random.
- The harness blends percentiles, not the z-scores production blends. The
  ladder is internally consistent; it is not the production path.
- The forward-return and sector readings are descriptive, fitted to
  nothing, with no multiplicity correction.
- Every stacked path moves more than one axis and settles none of them.
- One historical sample, after nine studies on this ledger.

## Next research (proposed, NOT run here)

1. A clean two-axis study of persistence k=6 + entry-selection separation.
2. Whether a blocking entry state should force an incumbent EXIT at all.
3. A cross-region common expected-return scale.
4. Calibration bucket RESOLUTION — `alpha-reliability-v1` named the
   two-occupied-bucket map as the bottleneck, and four single-axis studies
   have now failed to separate downstream of it.
5. If `lowvol` stays, whether the calibration layer rather than the factor
   definition is what limits it.
