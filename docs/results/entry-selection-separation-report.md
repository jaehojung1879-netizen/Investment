# Entry selection separation v1

> Read-only research CHALLENGER on sealed replay-v16 inputs. Alpha/risk
> score, targetNames, sector/region caps, cash floor and every cost
> assumption are unchanged, no selector is promoted and production is
> unchanged.

## The question

The entry-state multiplier (1.0 ACCUMULATE, 0.5 WATCH, 0.25
WAIT_FOR_PULLBACK, 0.0 fully blocking) is baked directly into the
SELECTION score today, so a WATCH name's score is halved before it is
ever ranked. The pre-registration's separation says alpha should decide
the held set and entry state should decide how fast the target weight is
approached. This moves the CONTINUOUS throttle (never the 0.0 blocking
case, which stays a full eligibility exclusion on both rungs) from the
ranking step to a post-selection weight throttle.

## Before the ladder: does this axis have any bite?

Measured on the control's own 155 rebalances.

- Eligible names by state: `{'ACCUMULATE_GRADUALLY': 845, 'WAIT_FOR_PULLBACK': 1518, 'WATCH': 665}`
- Held names by state: `{'ACCUMULATE_GRADUALLY': 365, 'WAIT_FOR_PULLBACK': 197, 'WATCH': 160}`
- Rebalances where an alpha-only selection would choose a DIFFERENT set: **130** (83.870%)
- Names the discount kept OUT that alpha-only would hold: **258**
- Names the discount let IN that alpha-only would drop: **258**

## The axis

| Rung | Entry-state role |
|---|---|
| `LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS` | multiplies the selection score |
| `ENTRY_STATE_THROTTLES_WEIGHT_NOT_SELECTION` | removed from selection/tilt, applied once to the held name's weight |

## The ladder

| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Vol | Sharpe | MDD | Turnover | Avg cash |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 13.564% | 1.404pp | 12.161% | 12.845% | -0.684pp | 11.985% | 0.853 | -25.158% | 4.679x | 30.417% |
| ENTRY_STATE_THROTTLES_WEIGHT_NOT_SELECTION | 8.976% | 0.921pp | 8.056% | 6.671% | 1.385pp | 7.446% | 0.813 | -11.466% | 3.620x | 56.002% |

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.315pp | 0.405pp | 0.719pp | 0.784x |
| ENTRY_STATE_THROTTLES_WEIGHT_NOT_SELECTION | 2.017pp | 0.289pp | 2.306pp | 0.788x |

### Turnover and selection behaviour

| Rung | One-way turnover | Name share | Names held (mean) | Incumbent retention |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 42.170% | 93.470% | 4.658 | 38.080% |
| ENTRY_STATE_THROTTLES_WEIGHT_NOT_SELECTION | 26.906% | 70.720% | 4.658 | 53.560% |

### The throttle's own footprint, on the new rung

- Held name-dates: 722
- Throttled below full weight: **496** (68.700%)
- Unapproached weight when throttled (pp of target, mean): 66.734

### Regional contribution to gross excess

| Rung | US contribution | US 95% CI | KR contribution | KR 95% CI |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.781pp | [-1.178pp, 2.922pp] | -0.467pp | [-7.272pp, 5.743pp] |
| ENTRY_STATE_THROTTLES_WEIGHT_NOT_SELECTION | 0.945pp | [-0.113pp, 2.073pp] | 1.072pp | [-3.409pp, 5.165pp] |

### Paired difference against the control

Δ annualized net excess: **2.069pp**, 95% CI [-1.881pp, 6.061pp], over 155 paired blocks.

This interval CONTAINS zero.

## Reading

**BENCHMARK_BEATEN**

The discount changed which names were held on 83.87% of control rebalances (130 of 155). On the new rung, 68.700% of held name-dates carried a throttled weight, and average cash held rose from 30.417% to 56.002% -- a much larger share of the book than the throttle's own direct effect, since alpha-only selection also holds many more of the WATCH/WAIT_FOR_PULLBACK names the discount used to keep out, and most of those are the ones then throttled. Net excess moves from -0.684pp (state discounts selection) to 1.385pp (state throttles weight only). Paired difference 2.069pp, 95% CI [-1.881pp, 6.061pp], which CONTAINS zero. The gross gap is overwhelmingly arithmetic stock selection (0.315pp -> 2.017pp), not compounding (0.405pp -> 0.289pp): on this sample the names the discount used to exclude realised BETTER excess returns than the ones it favoured, not merely lower volatility from holding more cash. That is a claim about THIS historical sample's realised outcomes, not a mechanism this study tested.

### Refuted

- Nothing was refuted by its own pre-specified test.

### Next direction

This axis is the continuous throttle only; a state whose multiplier is 0 stays a full eligibility exclusion on both rungs, for incumbents and new entries alike. Whether an incumbent should be forced out on a blocking state at all is a separate claim about exits and was explicitly left for its own test by the pre-registration -- this was the fourth and last of the four studies alpha-reliability-v1 pre-registered.

A rung ending higher than another is a point estimate on sealed history,
after several rungs across eight studies, with no multiplicity correction.
It is not evidence to promote a selector.
