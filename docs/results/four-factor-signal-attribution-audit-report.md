# Four-factor signal attribution audit v1

> Read-only research AUDIT on sealed replay-v16 inputs. No factor weight is
> changed, no combination is searched, no new Alpha formula is built from this
> sample, and no portfolio is selected or valued anywhere in this study.
> `promotionEligible: false`, production unchanged.

## Provenance inventory (Stage 0, measured before any statistic was computed)

| Sleeve | Sealed-ledger coverage |
|---|---:|
| momentum | 100.0000% |
| value | 71.6374% |
| quality | 86.2354% |
| lowvol | 100.0000% |

| Subfactor | Status |
|---|---|
| momentum.mom121 | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| momentum.mom6 | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| value.earningsYield | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| value.fwdEarningsYield | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| value.bookYield | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| value.fcfYield | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| quality.roe | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| quality.opMargin | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| quality.profitMargin | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| quality.earningsGrowth | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| quality.debtToEquity | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| lowvol.vol252 | AVAILABLE |

AVAILABLE/UNAVAILABLE is measured by scanning every signal row for the exact key path production's own raw_inputs()/historical_replay.py would have written it to, not assumed from reading the code. `mom20Pct`/`mom60Pct`/`relMomentum` exist on the record but are a DIFFERENT short-horizon feature (entry/overheat layer), never production's momentum sleeve inputs (mom121, mom6), and are never substituted for them in this audit.

## Primary output table -- 126D pooled Rank IC (Holm-corrected)

| Sleeve | Weight | 126D Rank IC | 95% CI | Raw p | Holm p | Incremental IC | KR sign | US sign | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| momentum | 0.3 | -0.0015 | [-0.0297, 0.0267] | 0.9155 | 1.0000 | 0.0212 | NEGATIVE | POSITIVE | 100.0000% |
| value | 0.25 | -0.0056 | [-0.0381, 0.0269] | 0.7373 | 1.0000 | -0.0079 | POSITIVE | NEGATIVE | 79.8910% |
| quality | 0.25 | -0.0223 | [-0.0473, 0.0027] | 0.0805 | 0.3220 | -0.0177 | NEGATIVE | NEGATIVE | 99.0380% |
| lowvol | 0.2 | 0.0286 | [-0.0100, 0.0673] | 0.1464 | 0.4392 | 0.0172 | POSITIVE | NEGATIVE | 100.0000% |

## Subfactor output table

| Sleeve | Input | Status |
|---|---|---|
| momentum | mom121 | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| momentum | mom6 | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| value | earningsYield | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| value | fwdEarningsYield | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| value | bookYield | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| value | fcfYield | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| quality | roe | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| quality | opMargin | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| quality | profitMargin | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| quality | earningsGrowth | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| quality | debtToEquity | UNAVAILABLE_PIT_INPUT_NOT_STORED |
| lowvol | vol252 | AVAILABLE |

## Redundancy matrix (pooled, time-averaged pairwise Spearman)

| | momentum | value | quality | lowvol |
|---|---:|---:|---:|---:|
| momentum | 1.0000 | -0.1706 | 0.0461 | 0.0028 |
| value | -0.1706 | 1.0000 | -0.1182 | 0.0859 |
| quality | 0.0461 | -0.1182 | 1.0000 | 0.0909 |
| lowvol | 0.0028 | 0.0859 | 0.0909 | 1.0000 |

## Quintile monotonicity (pooled)

| Sleeve | Q1 | Q2 | Q3 | Q4 | Q5 | Monotonicity | Q5-Q1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| momentum | -0.0200 | -0.0209 | -0.0206 | -0.0213 | -0.0048 | 0.5000 | 0.0152 |
| value | -0.0057 | -0.0242 | -0.0152 | -0.0109 | -0.0137 | 0.5000 | -0.0079 |
| quality | -0.0001 | -0.0071 | -0.0249 | -0.0220 | -0.0178 | 0.5000 | -0.0177 |
| lowvol | 0.0006 | -0.0170 | -0.0236 | -0.0241 | -0.0243 | 0.0000 | -0.0249 |

## Classification (descriptive only, section 15)

| Sleeve | Case | Rationale |
|---|---|---|
| momentum | D_UNSTABLE_REGIME_DEPENDENT | Sign disagrees across KR/US and/or first/second half; recorded as possibly conditional, not classified as independent or redundant. |
| value | D_UNSTABLE_REGIME_DEPENDENT | Sign disagrees across KR/US and/or first/second half; recorded as possibly conditional, not classified as independent or redundant. |
| quality | D_UNSTABLE_REGIME_DEPENDENT | Sign disagrees across KR/US and/or first/second half; recorded as possibly conditional, not classified as independent or redundant. |
| lowvol | D_UNSTABLE_REGIME_DEPENDENT | Sign disagrees across KR/US and/or first/second half; recorded as possibly conditional, not classified as independent or redundant. |

## EvidenceCoverage audit (descriptive, not primary confirmatory)

rawAlpha vs alpha rank Spearman: 0.9932

evidenceCoverage distribution: mean 0.7933, sd 0.1637

## Secondary horizons (descriptive only, never promoted to primary)

| Sleeve | 21D pooled IC | 63D pooled IC | 252D pooled IC |
|---|---:|---:|---:|
| momentum | -0.0073 | -0.0071 | -0.0200 |
| value | -0.0018 | -0.0049 | -0.0161 |
| quality | -0.0080 | -0.0172 | -0.0205 |
| lowvol | 0.0107 | 0.0216 | 0.0424 |

## Q1-Q10

**Q1. Which sleeves show a standalone relationship with forward benchmark excess?**

momentum: pooled 126D IC -0.0015 [-0.0297, 0.0267]; value: pooled 126D IC -0.0056 [-0.0381, 0.0269]; quality: pooled 126D IC -0.0223 [-0.0473, 0.0027]; lowvol: pooled 126D IC 0.0286 [-0.0100, 0.0673]

**Q2. What survives Holm multiple-testing correction across the primary four-sleeve family?**

momentum: raw p=0.9155, Holm-adjusted p=1.0000; value: raw p=0.7373, Holm-adjusted p=1.0000; quality: raw p=0.0805, Holm-adjusted p=0.3220; lowvol: raw p=0.1464, Holm-adjusted p=0.4392. Correction applied over exactly these 4 pooled-126D p-values.

**Q3. Which sleeves are redundant with each other?**

Redundancy matrix (pooled, mean pairwise Spearman): momentum-value -0.1706, momentum-quality 0.0461, momentum-lowvol 0.0028, value-quality -0.1182, value-lowvol 0.0859, quality-lowvol 0.0909

**Q4. Does any sleeve carry positive incremental information once the other three are controlled for?**

momentum: standalone -0.0015 vs incremental 0.0212; value: standalone -0.0056 vs incremental -0.0079; quality: standalone -0.0223 vs incremental -0.0177; lowvol: standalone 0.0286 vs incremental 0.0172

**Q5. Do KR and US agree in direction?**

momentum: {'KR': 'NEGATIVE', 'US': 'POSITIVE'}; value: {'KR': 'POSITIVE', 'US': 'NEGATIVE'}; quality: {'KR': 'NEGATIVE', 'US': 'NEGATIVE'}; lowvol: {'KR': 'POSITIVE', 'US': 'NEGATIVE'}

**Q6. Does the direction persist across the first/second half of the sample?**

momentum: first-half {'KR': 'NEGATIVE', 'US': 'POSITIVE'}, second-half {'KR': 'POSITIVE', 'US': 'POSITIVE'}; value: first-half {'KR': 'POSITIVE', 'US': 'NEGATIVE'}, second-half {'KR': 'POSITIVE', 'US': 'POSITIVE'}; quality: first-half {'KR': 'POSITIVE', 'US': 'NEGATIVE'}, second-half {'KR': 'NEGATIVE', 'US': 'NEGATIVE'}; lowvol: first-half {'KR': 'POSITIVE', 'US': 'POSITIVE'}, second-half {'KR': 'POSITIVE', 'US': 'NEGATIVE'}

**Q7. Do the two momentum inputs (12-1M, 6M) carry different information?**

PIT_NOT_AVAILABLE -- the sealed ledger never stored the raw 12-1M/6M momentum inputs, only the blended momentum sleeve percentile. Not substituted with mom20Pct/mom60Pct, which are a different feature.

**Q8. How redundant are the value inputs (trailing/forward earnings yield, book yield, FCF yield)?**

PIT_NOT_AVAILABLE -- no raw value input is stored on the sealed signal record.

**Q9. Does Quality mix offsetting profitability/growth/balance-sheet signals?**

PIT_NOT_AVAILABLE -- no raw quality input is stored on the sealed signal record.

**Q10. Is the composite's weak discrimination best explained by uniformly weak sleeves, a mix of good and bad sleeves, excessive redundancy, or PIT coverage limits?**

Classification per sleeve: momentum=D_UNSTABLE_REGIME_DEPENDENT; value=D_UNSTABLE_REGIME_DEPENDENT; quality=D_UNSTABLE_REGIME_DEPENDENT; lowvol=D_UNSTABLE_REGIME_DEPENDENT. Redundancy: momentum-value mean pairwise Spearman -0.1706, momentum-lowvol 0.0028. Subfactor-level attribution (which would separate 'sleeve is weak' from 'sleeve mixes a good and a bad input') is PIT_NOT_AVAILABLE for three of the four sleeves.

## What this study does NOT establish

- Not a promotion. `promotionEligible` is false; no factor weight is changed.
- No new Alpha formula is built from this sample; the classification is
  descriptive and is never used to recommend removing a sleeve on its own.
- Subfactor-level attribution is PIT_NOT_AVAILABLE for momentum, value and
  quality -- only lowvol's single raw input (vol252) is stored on the sealed
  ledger.
- This ledger has been used by ten prior studies; this result is DISCOVERY /
  DIAGNOSTIC EVIDENCE, never final out-of-sample validation.

## Proposed next research (NOT executed here)

1. Case A (independent sleeve found): design an independent-sample validation of that sleeve's information, never a same-sample reweighting.
2. Case B (standalone but redundant): investigate an orthogonal information source rather than reweighting the existing four sleeves.
3. Case C (weak across the board): evaluate new information sources (earnings revisions, estimate dispersion, relative-strength breadth, valuation change) as a separate CHALLENGER -- proposed, not implemented here.
4. Case D (insufficient data): extend PIT instrumentation to store the raw subfactor inputs (mom121, mom6, and the value/quality raw ratios) on future signal records so a subfactor audit becomes possible -- proposed, not executed.