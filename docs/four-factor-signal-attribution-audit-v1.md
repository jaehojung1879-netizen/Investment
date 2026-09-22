# Four-factor signal attribution audit v1 — design

> Research AUDIT, not a search for a better combination. No factor weight is
> changed, no combination is searched, and no portfolio is selected or
> valued anywhere in this study. `promotionEligible: false`, production
> unchanged.

## The question

Production's long-horizon alpha is `0.30 momentum + 0.25 value + 0.25
quality + 0.20 lowvol`, shrunk by `alpha = rawAlpha × evidenceCoverage`.
`alpha-calibration-resolution-v1` measured that, within a calibration-tied
group, the composite's own discarded ordinal information does not predict
forward excess (pairwise concordance ≈49%, within-group Spearman ≈0). This
study asks the question one level down:

> Of the four sleeves that feed the composite, which carry information
> about future benchmark-relative return, which are redundant with each
> other, and which cannot be assessed at all because the sealed ledger
> never stored their raw inputs?

## Confirmatory family, fixed before any number was computed

Exactly four primary hypotheses — one per sleeve — at `PRIMARY_HORIZON =
126` trading days (production's own target horizon; the expanding-bucket
calibration is itself built on 126 days). 21D/63D/252D are secondary and
descriptive only. The primary confirmatory statistic is each sleeve's
**pooled-within-region** rank IC; KR-only and US-only readings are reported
beside it as corroboration, never substituted for it.

## Why this is not a portfolio replay

No selection, no valuation, no calendar of rebalance blocks.
`kelly_portfolio.select_portfolio_by_scores` and `replay_valuation` are
never called. The audit reads `factorPercentiles`, `alphaPercentile`,
`rawAlpha`, `alpha` and matured `excessReturn` directly from the sealed
signals/outcomes and computes cross-sectional Spearman correlations —
`historical_outcomes.horizon_frame` and `portfolio_validation._nw_summary`
are reused exactly as production's own `alpha_diagnostics` uses them, not
reimplemented.

## Stage 0 — provenance, measured by scanning the sealed ledger

`lowvol-alpha-separation-v1` established the discipline this study repeats
one level down: read the schema before designing around it.

| Sleeve | Sealed coverage |
|---|---:|
| momentum | 100.00% |
| value | 71.64% |
| quality | 86.24% |
| lowvol | 100.00% |

| Subfactor | Status |
|---|---|
| momentum.mom121 | `UNAVAILABLE_PIT_INPUT_NOT_STORED` |
| momentum.mom6 | `UNAVAILABLE_PIT_INPUT_NOT_STORED` |
| value.earningsYield / fwdEarningsYield / bookYield / fcfYield | `UNAVAILABLE_PIT_INPUT_NOT_STORED` |
| quality.roe / opMargin / profitMargin / earningsGrowth / debtToEquity | `UNAVAILABLE_PIT_INPUT_NOT_STORED` |
| lowvol.vol252 | **`AVAILABLE`** (via `risk.vol252Pct`) |

Every raw subfactor input for momentum, value and quality is absent from
the sealed signal record — only each sleeve's already-blended percentile
survives. `mom20Pct`/`mom60Pct`/`relMomentum` exist on the record but are a
**different** short-horizon feature computed for the entry/overheat layer,
not production's momentum sleeve inputs (12-1 month and 6-month momentum),
and are never substituted for them. This makes the subfactor audit
(sections 17–19 of the pre-registration) `PIT_NOT_AVAILABLE` for three of
the four sleeves — a measured fact, not an assumption from reading
`longterm.py`.

## Primary output table — 126D pooled Rank IC (Holm-corrected)

| Sleeve | Weight | 126D Rank IC | 95% CI | Raw p | Holm p | Incremental IC | KR sign | US sign | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| momentum | 0.30 | -0.0015 | [-0.0297, 0.0267] | 0.9155 | 1.0000 | +0.0212 | NEGATIVE | POSITIVE | 100.00% |
| value | 0.25 | -0.0056 | [-0.0381, 0.0269] | 0.7373 | 1.0000 | -0.0079 | POSITIVE | NEGATIVE | 79.89% |
| quality | 0.25 | -0.0223 | [-0.0473, 0.0027] | 0.0805 | 0.3220 | -0.0177 | NEGATIVE | NEGATIVE | 99.04% |
| lowvol | 0.20 | +0.0286 | [-0.0100, 0.0673] | 0.1464 | 0.4392 | +0.0172 | POSITIVE | NEGATIVE | 100.00% |

**None of the four primary hypotheses clears even raw p < 0.05**, let alone
Holm correction. Every 95% CI on the pooled-within-region statistic
contains zero. This is on 399,547 sealed signals / 396,358 matured
outcomes, ~688 KR dates and ~689 US dates.

### Regional detail (not the primary confirmatory statistic)

| Sleeve | KR mean [CI] | US mean [CI] |
|---|---|---|
| momentum | -0.0120 [-0.0479, 0.0238] | +0.0155 [-0.0301, 0.0612] |
| value | +0.0257 [-0.0340, 0.0854] | -0.0187 [-0.0575, 0.0200] |
| quality | -0.0300 [-0.0684, 0.0084] | -0.0166 [-0.0496, 0.0163] |
| lowvol | **+0.0511 [+0.0047, 0.0974]** | -0.0225 [-0.0925, 0.0475] |

KR-only lowvol clears zero on its own (raw p=0.031) — the ONE region-level
reading in this table that does. It is not the primary confirmatory claim
(section 8 forbids substituting a regional reading for the pooled one), it
does not survive being pooled with US's negative point estimate, and it is
reported here as a secondary, descriptive number, not a finding.

## Redundancy matrix (pooled, time-averaged pairwise Spearman)

| | momentum | value | quality | lowvol |
|---|---:|---:|---:|---:|
| momentum | 1.0000 | -0.1706 | 0.0461 | 0.0028 |
| value | -0.1706 | 1.0000 | -0.1182 | 0.0859 |
| quality | 0.0461 | -0.1182 | 1.0000 | 0.0909 |
| lowvol | 0.0028 | 0.0859 | 0.0909 | 1.0000 |

No pair is strongly redundant (|ρ| ≤ 0.17 everywhere) — the four sleeves are
picking largely different names, they are just not, individually or
jointly, picking names whose forward benchmark-relative return the
percentile orders.

## Quintile monotonicity (pooled)

| Sleeve | Q1 | Q2 | Q3 | Q4 | Q5 | Monotonicity | Q5-Q1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| momentum | -0.0200 | -0.0209 | -0.0206 | -0.0213 | -0.0048 | 0.50 | +0.0152 |
| value | -0.0057 | -0.0242 | -0.0152 | -0.0109 | -0.0137 | 0.50 | -0.0079 |
| quality | -0.0001 | -0.0071 | -0.0249 | -0.0220 | -0.0178 | 0.50 | -0.0177 |
| lowvol | +0.0006 | -0.0170 | -0.0236 | -0.0241 | -0.0243 | 0.00 | -0.0249 |

No sleeve is monotone across its own quintiles (best score 0.50 of a
possible 1.0). Lowvol is monotone the WRONG way (Q1, the lowest sleeve
score, has the highest forward excess) — consistent with the pooled
standalone IC being small and the KR/US signs disagreeing.

## Classification (descriptive only — never a deletion recommendation)

| Sleeve | Case |
|---|---|
| momentum | `D_UNSTABLE_REGIME_DEPENDENT` |
| value | `D_UNSTABLE_REGIME_DEPENDENT` |
| quality | `D_UNSTABLE_REGIME_DEPENDENT` |
| lowvol | `D_UNSTABLE_REGIME_DEPENDENT` |

Every sleeve lands in Case D because KR and US disagree in sign for all
four sleeves (`classify_sleeve` checks region/half sign agreement before
magnitude). This is a stronger and more specific finding than plain
weakness: it is not just that the pooled point estimate is small, it is
that the sign itself does not generalize across the two regions the
composite is applied to identically.

## Time stability

First half: 2013-01-04 to 2019-08-02. Second half: 2019-08-09 to
2026-03-13 (one fixed chronological median split, never tuned per sleeve).
Sign flips between halves for at least one region on every sleeve; see the
sealed JSON's `timeStability` block for the full region×half cells.

## EvidenceCoverage audit (descriptive, not primary confirmatory)

- `rawAlpha` vs `alpha` rank Spearman: **0.9932** — evidence shrinkage
  barely reorders the ranking.
- `evidenceCoverage` distribution: mean 0.793, sd 0.164.
- By coverage quartile, realised excess-return dispersion does not rise
  monotonically toward the lowest-coverage quartile (sd 0.223, 0.289, 0.203
  across q1–q3 on this sample), so low evidence coverage is not obviously
  concentrating outcome variance in this cut.

## Coverage / missingness

| Region | Momentum | Value | Quality | Lowvol |
|---|---:|---:|---:|---:|
| KR | 0.00% missing | 55.45% missing | 53.99% missing | 0.00% missing |
| US | 0.00% missing | 20.11% missing | 0.96% missing | 0.00% missing |

Korean value/quality coverage is far worse than US — consistent with the
PIT-fundamentals invariants already on this repository (DART serves from
2015, Korean fundamentals dark for the replay's first two years, and
quarterly filing gaps run into later years too). A weak Korean value/quality
IC is `NO EVIDENCE DUE TO COVERAGE`-adjacent, not necessarily
`EVIDENCE OF NO EFFECT` — the coverage gap is published beside the IC
rather than silently averaged away.

## Secondary horizons (descriptive only, never promoted to primary)

| Sleeve | 21D | 63D | 252D |
|---|---:|---:|---:|
| momentum | -0.0073 | -0.0071 | -0.0200 |
| value | -0.0018 | -0.0049 | -0.0161 |
| quality | -0.0080 | -0.0172 | -0.0205 |
| lowvol | +0.0107 | +0.0216 | +0.0424 |

Directionally consistent with the primary 126D reading for three of four
sleeves (momentum, value, quality stay small/negative; lowvol stays small/
positive across every horizon measured) — reported for completeness, never
substituted for the fixed primary horizon.

## Answering the pre-registered questions (Q1–Q10)

1. **Standalone relationship?** All four pooled 126D ICs are near zero and
   every CI contains zero.
2. **Survives Holm correction?** No sleeve's raw p clears 0.05 even before
   correction, so none survives Holm either.
3. **Redundant pairs?** None strongly (|ρ| ≤ 0.17 pooled).
4. **Positive incremental IC?** momentum +0.021, lowvol +0.017 are the two
   positive incremental readings; value -0.008 and quality -0.018 are
   negative. All four are small relative to their standalone SEs.
5. **KR/US agreement?** Disagree in sign on all four sleeves.
6. **First/second-half persistence?** Signs flip for at least one region on
   every sleeve.
7–9. **Subfactor audits (momentum 12-1M/6M; value's four inputs; quality's
   five inputs)?** `PIT_NOT_AVAILABLE` — measured absent from the sealed
   ledger, not substituted with a proxy.
10. **What best explains the composite's weak discrimination?** All four
    sleeves classify as region-sign-unstable (Case D) at the primary
    horizon; none of the four clears even raw significance; redundancy is
    low, so the sleeves are not simply duplicating each other's
    information — they are, individually and jointly, close to
    uninformative about 126D forward benchmark-relative return on this
    sample, with the added caveat that value/quality also carry a real
    Korean coverage gap this audit cannot separate from a true weak signal.

## What this study does NOT establish

- Not a promotion. `promotionEligible` is `false`, no factor weight is
  changed, and no new Alpha formula is built from this sample.
- The classification is descriptive; it is never used, on its own, to
  recommend removing a sleeve — that needs an independent sample.
- Subfactor-level attribution is `PIT_NOT_AVAILABLE` for momentum, value and
  quality; only lowvol's raw input survives on the sealed ledger.
- `replay-v16` has been used by ten prior studies. This result is DISCOVERY
  / DIAGNOSTIC EVIDENCE, never final out-of-sample validation, regardless of
  how favourable or unfavourable any single reading looks.

## Proposed next research (NOT executed here)

Per the pre-registration's decision tree, this sample reads closest to
**Case C** (weak across the board) with a **Case D** (KR/US sign
instability, plus a genuine Korean value/quality coverage gap) overlay:

1. No sleeve here is an independent Case-A candidate on this sample, so no
   independent-sample validation of a single sleeve is proposed.
2. Redundancy is low, so this is not primarily a Case-B "the other sleeves
   already know this" story.
3. Evaluate new information sources (earnings revisions, estimate
   dispersion, relative-strength breadth, valuation change) as a separate
   CHALLENGER — proposed, not implemented here.
4. Extend PIT instrumentation to store the raw subfactor inputs (mom121,
   mom6, and the value/quality raw ratios) on future signal records, so a
   subfactor audit becomes possible on the NEXT ledger generation —
   proposed, not executed; no historical ledger was regenerated and no
   production code changed for this study.

## Reproducing

```
python scripts/run_four_factor_signal_attribution_audit.py <sealed-ledger> \
  --output four-factor-signal-attribution-audit-report.json \
  --markdown four-factor-signal-attribution-audit-report.md
```

The runner refuses to write inside the sealed ledger, digests the ledger
tree before and after the run and raises on any change, and the workflow
compares its output byte-for-byte against the checked-in artifacts in
`docs/results/`. Two independent full sealed runs produced byte-identical
JSON and Markdown output.
