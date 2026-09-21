# Alpha risk separation v1

> Read-only research CHALLENGER on sealed replay-v16 inputs. No factor is
> added, the `lowvol` sleeve weight and inverse-vol sizing are unchanged, no
> selector is promoted and production is unchanged.

## The question

`alpha-reliability-v1` measured a score/calibrated-alpha rank correlation of
0.758 against 0.075 with downside volatility across the whole cross-section —
alpha orders most pairs — but 86.71% of top-5 cuts are between names the
calibration scores IDENTICALLY, where what remains ordering the cut is the
risk-and-entry product in the score's denominator. This removes ONLY that
denominator from the selection ranking and asks whether the defensive tilt
measured there survives.

## The axis

| Rung | Score formula |
|---|---|
| `LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS` | calibrated alpha / (downside vol x 100) x entry multiplier |
| `RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR` | calibrated alpha x entry multiplier |

The control is `alpha_reliability.run_rung(alpha_reliability.CONTROL, ...)`
called directly — not reproduced — so there is no second implementation of it
to drift from the first. `DOWNSIDE_RISK_UNAVAILABLE` still excludes a name on
both rungs: sizing needs a risk unit whatever the ranking divides by.

## The ladder

| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Vol | Sharpe | MDD | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 13.564% | 1.404pp | 12.161% | 12.845% | -0.684pp | 11.985% | 0.853 | -25.158% | 4.679x |
| RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR | 13.175% | 1.771pp | 11.403% | 12.989% | -1.586pp | 12.941% | 0.747 | -28.958% | 5.744x |

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.315pp | 0.405pp | 0.719pp | 0.784x |
| RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR | -0.141pp | 0.326pp | 0.185pp | 0.804x |

### Turnover and selection behaviour

| Rung | One-way turnover | Name share | Names held | Incumbent retention |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 42.170% | 93.470% | 4.658 | 38.080% |
| RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR | 51.889% | 94.560% | 4.658 | 33.470% |

### Regional contribution to gross excess

| Rung | US contribution | US 95% CI | KR contribution | KR 95% CI |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.781pp | [-1.178pp, 2.922pp] | -0.467pp | [-7.272pp, 5.743pp] |
| RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR | 0.660pp | [-1.405pp, 2.809pp] | -0.801pp | [-8.008pp, 5.596pp] |

### Paired difference against the control

Δ annualized net excess: **-0.902pp**, 95% CI [-5.068pp, 3.210pp], over 155 paired blocks.

This interval CONTAINS zero.

## Did the defensive tilt survive?

`risk_dominance` (`alpha_reliability`) run unmodified on each rung's own
decisions — nothing here re-derives that instrument, it only reads it
twice.

| Reading | Control | Alpha-only |
|---|---:|---:|
| Spearman(score, downside vol) | 0.075 | 0.203 |
| Downside vol of names held (%) | 24.445 | 26.109 |
| Downside vol of names rejected (%) | 27.172 | 26.651 |
| `lowvol` sleeve percentile, held | 74.374 | 71.236 |
| `lowvol` sleeve percentile, rejected | 63.808 | 64.791 |
| `lowvol` is the highest sleeve (%) | 32.690 | 24.930 |
| `lowvol` is in the top two sleeves (%) | 58.860 | 54.570 |
| Held matches an alpha-only top-N (%) | 30.070 | 32.000 |

- Δ downside vol held: **1.664pp** (alpha-only minus control).
- Δ `lowvol` sleeve percentile held: **-3.139**.
- Δ `lowvol` is the highest sleeve: **-7.760pp**.

## Why did turnover move?

`boundary_instability` and `replacement_anatomy` (`alpha_reliability`), run
unmodified on each rung's own decisions. The calibration already hands most
of the pool one alpha; removing the score's one continuously-varying term
(downside volatility) can only make ties at the margin MORE common, never
less — this measures whether it did.

| Reading | Control | Alpha-only |
|---|---:|---:|
| Cuts tied on expected alpha (%) | 86.710% | 94.410% |
| Relative score gap at the cut, median | 0.086 | 0.000 |
| Swaps tied on expected alpha (%) | 29.770% | 20.590% |
| Held names whose percentile moved ≤1pt and were replaced anyway (%) | 47.820% | 53.730% |

## Reading

**BENCHMARK_NOT_BEATEN**

Net excess moves from -0.684pp (control, risk in the denominator) to -1.586pp (alpha only). Paired difference -0.902pp, 95% CI [-5.068pp, 3.210pp], which CONTAINS zero. On the defensive-tilt question named by `alpha-reliability-v1`: downside volatility held moves by 1.664pp and `lowvol` being the highest sleeve moves by -7.760pp when the denominator is removed — the tilt largely SURVIVES, which points at the alpha term (the `lowvol` sleeve) rather than the ranking denominator, and is the next study's axis. Cuts tied on expected alpha move from 86.710% to 94.410% once the one continuously-varying term in the score is removed, which is the mechanism behind any turnover change measured above.

### Refuted

- Nothing was refuted by its own pre-specified test.

### Next direction

If the tilt survives, the open question is whether the `lowvol` sleeve itself belongs in the alpha layer or the risk layer — that two-risk-channel move is explicitly out of scope here and belongs to its own study, per the pre-registration. If the tilt does not survive, the denominator was the channel and the sleeve question is less urgent. Either way, `dynamic-breadth-v1`, `region-quota-removal-v1` and `entry-selection-separation-v1` remain pre-registered and untouched by this result.

A rung ending higher than another is a point estimate on sealed history,
after several rungs across five studies, with no multiplicity correction.
It is not evidence to promote a selector.
