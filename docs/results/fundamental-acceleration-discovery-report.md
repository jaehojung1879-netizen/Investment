# Fundamental-acceleration discovery v1

> Read-only research DISCOVERY study on sealed replay-v16 inputs. No factor
> weight is changed, no portfolio is selected or valued, no threshold is tuned
> after seeing a result. `promotionEligible: false`, production unchanged.

## Coverage (Stage A)

Overall data-sufficient ratio: **0.6495** over 399547 name-dates (PASS, threshold 0.6).

| Region | Total | Data-sufficient | Ratio |
|---|---:|---:|---:|
| KR | 98901 | 13611 | 0.1376 |
| US | 300646 | 245894 | 0.8179 |

| Field | Present among OK filing pairs |
|---|---:|
| debtToEquity | 93.6140% |
| earningsGrowth | 74.9910% |
| operatingMargin | 75.9640% |
| profitMargin | 79.1180% |
| roe | 79.4620% |

## Orthogonality vs. existing sleeves (Stage B)

|rho| vs Quality: **0.1180** (PASSES the 0.7 redundancy threshold).

| Factor | Mean Spearman |
|---|---:|
| lowvol | -0.0124 |
| momentum | 0.1772 |
| quality | 0.1180 |
| value | -0.0235 |

## Debt-to-equity acceleration (diagnostic only, never scored)

Non-exempt observations: 297790, exempt masked: 17617, mean delta (non-exempt): 0.0284. Exempt sectors: Financials, Holding, Real Estate, Utilities.

## Primary discovery statistics (126D)

| Statistic | Mean | 95% CI | Raw p | Holm p |
|---|---:|---:|---:|---:|
| Standalone Rank IC | -0.0026 | [-0.0257, 0.0204] | 0.8233 | 1.0000 |
| Incremental Rank IC (beyond Quality) | -0.0009 | [-0.0205, 0.0187] | 0.9248 | 1.0000 |

## Region stability

{'KR': 'POSITIVE', 'US': 'NEGATIVE'} -- REGION_SIGN_UNSTABLE

## Time stability (fixed chronological half-split)

First half mean -0.0222, second half mean 0.0157 -- HALF_SIGN_UNSTABLE

## Quintile table (pooled)

| Q1 | Q2 | Q3 | Q4 | Q5 | Monotonicity | Q5-Q1 |
|---:|---:|---:|---:|---:|---:|---:|
| 0.0023 | -0.0106 | -0.0165 | -0.0131 | 0.0068 | 0.5000 | 0.0045 |

## Quality-level-conditional (descriptive only)

| Quality quintile | High-accel mean excess | Low-accel mean excess | Diff | n |
|---|---:|---:|---:|---:|
| qualityQ1 | 0.0144 | 0.0093 | 0.0051 | 1348 |
| qualityQ2 | -0.0076 | -0.0100 | 0.0025 | 1348 |
| qualityQ3 | -0.0219 | -0.0177 | -0.0042 | 1348 |
| qualityQ4 | -0.0117 | -0.0160 | 0.0044 | 1348 |
| qualityQ5 | 0.0058 | -0.0077 | 0.0135 | 1348 |

## Secondary horizons (descriptive only, never promoted to primary)

| Horizon | Standalone pooled IC |
|---|---:|
| 21D | 0.0049 |
| 63D | -0.0007 |
| 252D | -0.0091 |

## Classification (Q1-Q12)

**D_NO_DISCOVERY_EVIDENCE**

Standalone and/or incremental pooled Rank IC point estimates are not both positive, or the evidence is otherwise mixed. No discovery evidence of a forward-return relationship beyond the existing Quality level factor on this sample.

**Q1. Is the two-consecutive-filing PIT construction computable on real data, and at what overall coverage?**

Data-sufficient coverage ratio 0.6495 over 399547 signal name-dates (MEETS the pre-registered 0.6 minimum). Status breakdown: {'OK': 336309, 'NO_FILING_VISIBLE': 51893, 'NOT_CONSECUTIVE': 9725, 'NO_PREVIOUS_FILING': 1620}.

**Q2. How does coverage split by region and by chronological half?**

By region: KR: 0.1376; US: 0.8179. By half: first 0.5813, second 0.7065.

**Q3. Which of the four primary fields (roe, operatingMargin, profitMargin, earningsGrowth) most limits coverage among OK consecutive-filing pairs?**

debtToEquity: 93.6140%; earningsGrowth: 74.9910%; operatingMargin: 75.9640%; profitMargin: 79.1180%; roe: 79.4620%

**Q4. Is the acceleration composite genuinely distinct information from the existing Quality LEVEL factor, or a relabelling of it?**

Pooled Spearman(accelerationPercentile, qualityPercentile) = 0.1180 (PASSES the pre-registered |rho| < 0.7 redundancy threshold).

**Q5. How does the acceleration composite correlate with the other three existing sleeves (momentum, value, lowvol), descriptively?**

lowvol: -0.0124; momentum: 0.1772; value: -0.0235

**Q6. What is the standalone pooled-within-region Rank IC at the primary 126D horizon, with its 95% CI and Holm-adjusted p-value?**

mean -0.0026, CI [-0.0257, 0.0204], raw p 0.8233, Holm p 1.0000.

**Q7. What is the incremental Rank IC once Quality's own level is residualized out (single-predictor regression, Quality alone), with its 95% CI and Holm-adjusted p-value?**

mean -0.0009, CI [-0.0205, 0.0187], raw p 0.9248, Holm p 1.0000.

**Q8. Do KR and US agree in direction on the standalone Rank IC?**

{'KR': 'POSITIVE', 'US': 'NEGATIVE'} -- REGION_SIGN_UNSTABLE.

**Q9. Does the direction persist across a fixed chronological half-split of the sample?**

first half mean -0.0222, second half mean 0.0157 -- HALF_SIGN_UNSTABLE.

**Q10. Is the primary-horizon relationship monotone across acceleration quintiles?**

quintile means [0.002275, -0.010594, -0.016543, -0.013075, 0.00677], monotonicity 0.5000, Q5-Q1 0.0045.

**Q11. Within a fixed Quality-percentile quintile, does a median-split on acceleration separate forward excess return (descriptive only, no score, ranking or rule)?**

qualityQ1: high-low=0.0051 (n=1348); qualityQ2: high-low=0.0025 (n=1348); qualityQ3: high-low=-0.0042 (n=1348); qualityQ4: high-low=0.0044 (n=1348); qualityQ5: high-low=0.0135 (n=1348)

**Q12. What is the overall outcome classification, and what does this study recommend next?**

D_NO_DISCOVERY_EVIDENCE -- Standalone and/or incremental pooled Rank IC point estimates are not both positive, or the evidence is otherwise mixed. No discovery evidence of a forward-return relationship beyond the existing Quality level factor on this sample. Per design, a favourable reading here is discovery-stage evidence only; confirmatory validation is reserved for the prospective sealed window, never for a same-sample re-tune of this composite.

## What this study does NOT establish

- Not a promotion. `promotionEligible` is false; no factor weight is changed,
  no portfolio is selected or valued.
- No threshold, window, or field was tuned after seeing a result -- the
  composite formula, the primary horizon, and the 0.60/0.70 thresholds were
  all fixed by `docs/challenger-2-fundamental-acceleration-v1-design.md` before
  this module was written.
- Confirmatory evidence is reserved for the prospective sealed window; a
  favourable historical reading here is DISCOVERY-STAGE evidence only.
- This ledger has been used by eleven prior studies; this result is DISCOVERY
  / DIAGNOSTIC EVIDENCE, never final out-of-sample validation.
