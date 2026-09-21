# Alpha risk separation — diagnostic extension v1 — design

> Read-only extension of the FROZEN `alpha-risk-separation-v1` ladder. No rung
> is re-scored, no score moves, the checked-in frozen report is never
> rewritten, `promotionEligible` stays `false` and production is unchanged.

## Why this is an extension and not a re-run

`alpha-risk-separation-v1` is scored, published and merged. Its ladder is
`CONTROL` vs `RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR`, its paired
difference is **-0.902pp, 95% CI [-5.068, +3.210]** over 155 blocks, and that
interval **contains zero**.

Re-running a settled ladder is how a research programme talks itself into a
result. `alpha-reliability-v1` already wrote the rule that applies instead:

> A DIAGNOSTIC ADDED AFTER A LADDER IS SCORED MAY ONLY READ IT.

So this study re-runs the frozen rungs by **calling the frozen study's own
functions** — `alpha_reliability.run_rung` and
`alpha_risk_separation.run_alpha_only_rung`, unmodified — and then asserts
that all ten scored blocks it reproduces are byte-identical to the
checked-in `docs/results/alpha-risk-separation-report.json`. A mismatch
raises `FROZEN_LADDER_MOVED` and refuses to publish. The runner's `_guard`
additionally refuses the frozen report's own path as an output, so it cannot
be overwritten even by mistake.

That assertion is the whole point: it is a mechanical proof that nothing
added here could have moved the published result.

## What the frozen study already answered — not repeated

`risk_dominance` (held-vs-rejected downside vol, `lowvol` sleeve percentile,
`lowvol` as highest / top-two sleeve, alpha-only-top-N overlap, names the
risk term promoted or dropped across the cut), `boundary_instability` (tie
rate and the gaps at the cut), `replacement_anatomy` (swap anatomy, realised
arriving-minus-departing excess), `tilt_survival` (the cross-rung deltas of
all of those). All of it is reproduced above unchanged and read, not redone.

## The three things it did not

### 1. The set difference — the only population that can answer "what did the denominator buy?"

`risk_dominance` compares held against rejected **within** a rung. It never
looks at the names the two rungs **disagree about**, and that is the only
population that can say what removing the denominator actually bought.

`set_difference_profiles` pairs the two rungs **by date** and profiles
`selectedByChallengerNotControl` against `selectedByControlNotChallenger` on
momentum, value, quality, `lowvol`, downside volatility, alpha percentile,
calibrated expected excess, and the realised forward benchmark excess.

Paired **within** a rebalance, so the comparison carries no market-timing
term: both groups were chosen on the same date, from the same cross-section,
under the same caps, and the only thing that differs is whether the score
divided by downside volatility. Pooled across dates it would measure which
months were kind — the same error `signal-persistence-v1` named.

Factor facts are read from the **control rung's own scored rows for both
groups**. Both rungs score the identical candidate cross-section and differ
only in the score formula, so every name in either group is present in the
control's rows; reading a single source removes any doubt that a profile gap
came from the source rather than from the group.

The realised forward return is **evaluation only**. It is read off the same
priced cross-section `replacement_anatomy` already reads, it enters no score,
no ranking and no rule, and it is reported as a difference of two group means
— explicitly **not** a paired test.

### 2. The exploratory stack — reported outside the ladder

`signal-persistence-v1`'s k=6 smoother and this denominator removal are
orthogonal, so their combination is worth seeing. But it moves **two axes**
and is attributable to **neither** — exactly the status
`signal-persistence-v1` gave its own stacked path. It is therefore run and
reported strictly outside the primary ladder, never paired into it, and its
number may not be read as the denominator's independent effect.

It introduces nothing new: `AR.confidence_rows(persistence=True)` and
`ARS.separation_scores`, two existing pieces combined.

### 3. Q1–Q8 in prose

Answered from this run's own numbers in the report, rather than left for a
reader to assemble from tables.

## Observational only

`region_cap_binding` and `entry_state_dynamics` are run on both rungs. This
study touches **neither** the region quota nor the entry logic, and these
numbers are not grounds to change either — `region-quota-removal-v1` and
`entry-selection-separation-v1` are the studies that tested those axes.

## What this extension does NOT justify

- **It re-scores nothing.** The ladder is the frozen study's own,
  byte-identical. No new evidence about the denominator's effect is produced
  here, and no diagnostic below changes that interval.
- The realised set-difference return is **descriptive**: a difference of
  group means, no paired test, no multiplicity correction, nothing fitted.
- The exploratory stack moves two axes and settles neither.
- Region-cap and entry-state readings are observational.
- Nothing here is a promotion. No parameter is introduced, no threshold is
  added after seeing a result, no rung definition moves, and no permutation
  null was run.

## Next pre-registered study

`lowvol` sleeve alpha/risk separation — move the 0.20 `lowvol` sleeve out of
the four-factor alpha and into the risk layer. This extension's Q3/Q4
localise the surviving tilt there, which makes it the coherent next axis to
**test**. That is explicitly not evidence the move would help: this study's
own axis produced no separation, and a second axis inherits that uncertainty
rather than resolving it. It is not run here.

## Reproducing

```
python scripts/run_alpha_risk_separation_diagnostics_replay.py <sealed-ledger> \
  --output alpha-risk-separation-diagnostics-report.json \
  --markdown alpha-risk-separation-diagnostics-report.md
```

The runner refuses to write inside the sealed ledger, refuses the frozen
report's path as an output, digests the ledger tree before and after the run
and raises on any change, asserts the frozen ladder byte-identical, and the
workflow compares its output byte-for-byte against the checked-in artifacts
in `docs/results/`.
