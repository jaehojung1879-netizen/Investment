# Alpha risk separation — diagnostic extension v1

> Read-only extension of the FROZEN `alpha-risk-separation-v1` ladder.
> No rung is re-scored, no score moves, and the checked-in frozen report
> is never rewritten — every scored block below is asserted byte-identical
> to it. Nothing is promoted and production is unchanged.

## What this adds, and why it is a separate study

`alpha-risk-separation-v1` is scored and merged. `alpha-reliability-v1`'s own
rule — A DIAGNOSTIC ADDED AFTER A LADDER IS SCORED MAY ONLY READ IT — is what
this obeys: the frozen rungs are re-run by CALLING the frozen study's own
functions, and the run is refused if any of its published numbers move.

Byte-identity against `docs/results/alpha-risk-separation-report.json`: **IDENTICAL** (10 scored blocks checked).

## The frozen ladder, reproduced unchanged

| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Vol | Sharpe | MDD | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 13.564% | 1.404pp | 12.161% | 12.845% | -0.684pp | 11.985% | 0.853 | -25.158% | 4.679x |
| RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR | 13.175% | 1.771pp | 11.403% | 12.989% | -1.586pp | 12.941% | 0.747 | -28.958% | 5.744x |

Paired difference (challenger minus control): **-0.902pp**, 95% CI [-5.068pp, 3.210pp] over 155 paired blocks — **CONTAINS zero**.

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.315pp | 0.405pp | 0.719pp | 0.784x |
| RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR | -0.141pp | 0.326pp | 0.185pp | 0.804x |

## NEW: the names the two rungs disagree about

`risk_dominance` compares held against rejected WITHIN a rung. It cannot
answer what the denominator actually BOUGHT. This pairs the two rungs by
date and profiles only the names they disagree about.

- Rebalances measured: **145**
- Held name-dates both rungs agreed on: **489**
- Held name-dates they disagreed on: **233**
- Held-set overlap per rebalance (mean): **54.314%**

| Sleeve / metric | Challenger-only names | Control-only names |
|---|---:|---:|
| momentum | 84.382 | 83.695 |
| value | 66.068 | 62.599 |
| quality | 74.823 | 74.197 |
| lowvol | 61.378 | 71.103 |
| downside volatility | 27.877 | 22.720 |
| alpha percentile | 98.163 | 98.039 |
| calibrated expected excess | 0.392 | 0.376 |

### Realised forward benchmark excess — EVALUATION ONLY

Read off the same priced cross-section `replacement_anatomy` reads. It
enters no score, no ranking and no rule; it is reported because the
question was asked, not because anything was fitted to it.

| | Challenger-only | Control-only |
|---|---:|---:|
| Name-dates | 233 | 233 |
| Mean block excess | 0.587% | 0.799% |
| Median | -0.284% | 0.146% |
| Win rate | 46.780% | 51.930% |
| 95% CI | [-0.654, 1.913] | [-0.529, 2.223] |

Difference of the two group means: **-0.212pp** — a difference of means, NOT a paired test.

## EXPLORATORY ONLY — two axes at once, outside the ladder

k=6 percentile persistence AND the denominator removal. This moves TWO
axes and is attributable to NEITHER. It is not a rung of the primary
ladder, it is not paired into it, and its number may not be read as the
denominator's independent effect.

| Path | Net excess | Sharpe | MDD | Turnover |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS (control) | -0.684pp | 0.853 | -25.158% | 4.679x |
| EXPLORATORY_PERSISTENT_ALPHA_K6_PLUS_NO_RISK_DENOMINATOR | -0.231pp | 0.829 | -28.759% | 5.759x |

Against the control: 0.454pp, 95% CI [-4.235pp, 5.570pp] — reported for completeness and attributable to neither axis alone.

## Observational only — not this study's axis

The region quota and the entry logic are NOT touched by this study, and
these numbers are not grounds to change either. They are reported because
the denominator's removal interacts with both.

| Reading | Control | Alpha-only |
|---|---:|---:|
| Region cap bound (% of rebalances) | 93.100% | 93.790% |
| Sector cap bound (% of rebalances) | 24.140% | 24.830% |
| Rebalances a capped name outscored one taken | 134 | 135 |
| Held name-dates by region | {'KR': 421, 'US': 301} | {'KR': 426, 'US': 296} |
| Top-N by score with caps lifted, by region | {'KR': 640, 'US': 82} | {'KR': 666, 'US': 56} |
| Entry-state transitions observed | 1740 | 1740 |
| Transitions coinciding with a swap (%) | 26.320% | 28.510% |
| Departures whose state had turned blocking | 39 | 39 |
| Departures where the step fell and alpha moved <=1pt | 114 | 126 |

The last two rows are the §11 reading: a name dropped while the ranking had
barely changed its opinion, with the entry step as the thing that moved. It is
observational — `entry-selection-separation-v1` is the study that tested that
axis, and this extension does not reopen it.

## Q1–Q8

**Q1. Downside-volatility denominator를 제거했을 때 benchmark-relative net performance는 어떻게 변했는가?**

Net excess moved -0.684pp -> -1.586pp. Paired difference -0.902pp, 95% CI [-5.068pp, 3.210pp] over 155 blocks, which CONTAINS zero. The point estimate is worse and the interval does not clear zero in either direction, so removing the denominator is NOT SHOWN to help and is not shown to hurt either.

**Q2. 그 변화 중 얼마가 arithmetic stock selection이고 얼마가 compounding / volatility effect인가?**

Arithmetic stock selection 0.315pp -> -0.141pp; compounding 0.405pp -> 0.326pp; block sd ratio 0.784x -> 0.804x. This is the primary mechanism metric: it says whether any move came from CHOOSING differently or merely from a changed volatility profile.

**Q3. 저변동성/방어주 편향은 실제로 감소했는가?**

Held downside volatility moved 1.664pp and `lowvol` being a held name's highest sleeve moved -7.760pp; the score's rank correlation with downside volatility moved 0.075 -> 0.203. The tilt is REDUCED, not removed — part of it arrives through the `lowvol` sleeve inside the alpha, which this study deliberately does not touch.

**Q4. Momentum/Quality가 강하지만 volatility가 높은 종목이 더 많이 선택되었는가?**

On the 233 name-dates the two rungs disagree about: the challenger-only names carry momentum 84.382 / quality 74.823 / lowvol 61.378 at 27.877% downside volatility, against the control-only names' momentum 83.695 / quality 74.197 / lowvol 71.103 at 22.720%. SO THE PREMISE OF THIS QUESTION IS NOT WHAT HAPPENED. Momentum moved +0.687 and quality +0.626 between the two groups — differences of well under a percentile point — while `lowvol` moved -9.725 and realised downside volatility +5.157pp. The denominator was not holding back high-momentum or high-quality names. It was holding back names with the SAME alpha profile at HIGHER volatility, which is what a risk denominator is supposed to do. That reframes the axis: removing it did not buy different alpha, it bought the same alpha more riskily.

**Q5. 그러한 newly selected high-vol names가 실제 forward benchmark-relative return에서도 더 나았는가? (descriptive only)**

Challenger-only names realised 0.587% mean forward block excess (win rate 46.780%) against control-only names' 0.799% (win rate 51.930%), a difference of -0.212pp. This is a difference of two group means, not a paired test, and it is DESCRIPTIVE: no rule, score or ranking in this repository reads it.

**Q6. Volatility와 MDD는 얼마나 악화 또는 개선되었으며 inverse-vol sizing만으로 그 risk 증가가 충분히 통제되었는가?**

Realized volatility 11.985% -> 12.941%, MDD -25.158% -> -28.958%, Sharpe 0.853 -> 0.747. Inverse-downside-volatility SIZING is identical on both rungs, so whatever risk moved is what the SELECTION change let in that sizing alone did not absorb.

**Q7. Top-5 boundary에서 expected-alpha tie가 발생했을 때 denominator 제거 전후로 무엇이 실제 tie-breaker가 되었는가?**

Cuts tied on expected alpha 86.710% -> 94.410%, and the relative score gap at the cut (median) 0.086 -> 0.000. Removing the score's one continuously-varying term can only make ties at the margin MORE common: with the denominator gone the calibration's coarse alpha is all that is left, and the tie-break falls to the deterministic ticker ordering inside `_select_scored` rather than to any signal at all.

**Q8. 이번 결과는 'lowvol sleeve를 alpha에서 제거하고 risk layer로 이동'할 충분한 근거를 주는가?**

Interpretation only; that experiment is NOT run here. The denominator's removal did not separate from the control in either direction, and the defensive tilt SURVIVED it — which localises the remaining tilt in the `lowvol` sleeve inside the alpha rather than in the ranking. That makes the sleeve the coherent next axis to TEST, and it is exactly not evidence that moving it would help: this study's own axis produced no separation, and a second axis inherits that uncertainty rather than resolving it.

## What this extension does NOT justify

- It re-scores nothing: the ladder above is the frozen study's own,
  byte-identical. No new evidence about the denominator's effect is
  produced here, and none of these diagnostics changes that interval.
- The realised set-difference return is descriptive. It is a difference of
  group means over names the two rungs happened to disagree about, with no
  multiplicity correction and no paired test, and nothing is fitted to it.
- The exploratory stack moves two axes and settles neither.
- Region-cap and entry-state readings are observational; this study does
  not touch either mechanism and its numbers are not grounds to.
- Nothing here is a promotion. `promotionEligible` is false.

## Next pre-registered study

`lowvol` sleeve alpha/risk separation — move the 0.20 `lowvol` sleeve out
of the four-factor alpha and into the risk layer. This extension's Q3/Q4
localise the surviving tilt there, which makes it the coherent next axis
to TEST; it is explicitly not evidence that the move would help, and it is
not run here.
