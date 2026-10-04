# kr-stock-within-industry-anatomy-v1 — sealed exploratory result

**Status: `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`.** Descriptive historical associations on an outcome-exposed, partially reconstructed history. Not confirmatory, not validated, not predictive, not production-ready, not prospective. Nothing here is a model, a selection rule or a recommendation, and no feature is called best. The membership underneath ended `DATA_FOUNDATION_INSUFFICIENT_V4`; that decision is not relabelled.

This report is rendered from the committed exact result bytes by `scripts/render_kr_stock_within_industry_anatomy_v1_report.py`. It reads numbers and recomputes nothing. The formal one-shot execution (run 37196246044) has been spent and cannot be rerun. No registered feature, horizon, taxonomy, sample, sensitivity or interpretation rule was changed after the outcomes were read, and none was selected from them.

* Return basis: `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS` (adjusted index, partial observed distributions; neither a price return nor a total shareholder return). Benchmark: `069500.KS`.
* Primary target: stock forward return minus the LEAVE-ONE-OUT CAP_WEIGHTED industry forward return (the evaluated stock is excluded from the cohort and the weights; weights are signal-date market caps of the peers). Primary horizon H126; H63 and H252 descriptive; EQUAL_WEIGHT is the robustness benchmark.
* Primary statistic: per signal date, the Spearman between the WITHIN-INDUSTRY feature rank and that target across the common-sample stocks of the date (at least 30), then the mean over dates. Weekly signals overlap, so the effective number of independent observations is far smaller than the valid dates shown.
* The three components satisfy stock − market = (leave-one-out industry − market) + (stock − leave-one-out industry) on every matured row. Rank correlations are not additive, so no figure below is a decomposition of another.

## 1. Eligibility and denominators

| Sensitivity | stock-dates | signal dates | eligible | below 5 industry members | unclassified | excluded by sensitivity | eligible per date min / median / max |
|---|---:|---:|---:|---:|---:|---:|---|
| FULL | 73200 | 610 | 61049 | 8707 | 3444 | 0 | 90 / 100 / 111 |
| EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX | 73200 | 610 | 59829 | 8707 | 3444 | 1220 | 88 / 98 / 109 |

UNKNOWN names retained in the denominator: 3442. Ineligible reasons (FULL): BELOW_MINIMUM_CLASSIFIED_MEMBERS 8707, IDENTITY_TERMINATED 2, UNKNOWN 3442. No UNKNOWN name was used to fill a cohort and no terminal name was replaced by a survivor.

Target status by lens and horizon (FULL; every eligible stock-date has a status):

| lens / horizon | MATURED | PENDING | ineligible stock-date | any other |
|---|---:|---:|---:|---:|
| CAP_WEIGHTED H126 | 58476 | 2573 | 12151 | 0 |
| CAP_WEIGHTED H252 | 55815 | 5234 | 12151 | 0 |
| CAP_WEIGHTED H63 | 59799 | 1250 | 12151 | 0 |
| EQUAL_WEIGHT H126 | 58476 | 2573 | 12151 | 0 |
| EQUAL_WEIGHT H252 | 55815 | 5234 | 12151 | 0 |
| EQUAL_WEIGHT H63 | 59799 | 1250 | 12151 | 0 |

Feature coverage (FULL, CAP_WEIGHTED H126; the common sample is eligible, matured, raw finite and within-industry rank finite):

| feature | eligible | matured | raw finite | within-industry rank finite | common sample |
|---|---:|---:|---:|---:|---:|
| bookToMarketProxy | 61049 | 58476 | 45946 | 45877 | 43368 |
| earningsYieldProxy | 61049 | 58476 | 37011 | 33783 | 31370 |
| ocfYieldProxy | 61049 | 58476 | 36718 | 33941 | 31528 |
| netIncomeToAssets | 61049 | 58476 | 36985 | 33737 | 31324 |
| ocfToAssets | 61049 | 58476 | 36705 | 33928 | 31515 |
| negativeAccrualsToAssets | 61049 | 58476 | 35715 | 32125 | 29712 |
| relative126 | 61049 | 58476 | 60344 | 60232 | 57671 |
| momentum121 | 61049 | 58476 | 59523 | 59167 | 56623 |
| ocfImprovementToAssets | 61049 | 58476 | 30921 | 27651 | 25289 |
| negativeDownsideVol126 | 61049 | 58476 | 60344 | 60232 | 57671 |
| logAdv60 | 61049 | 58476 | 60102 | 59826 | 57286 |

## 2. Primary: within-industry rank vs stock − leave-one-out CAP_WEIGHTED industry, H126, FULL

Features are listed in the registered order, never sorted by result.

| feature | mean | median | positive-date fraction | valid dates | descriptive HAC se | mean / se | positive-year fraction (years >= 13 dates) |
|---|---:|---:|---:|---:|---:|---:|---:|
| bookToMarketProxy | +0.086 | +0.105 | 0.71 | 518 | 0.029 | +2.9 | 0.90 |
| earningsYieldProxy | +0.073 | +0.079 | 0.67 | 472 | 0.028 | +2.6 | 0.78 |
| ocfYieldProxy | +0.022 | +0.027 | 0.58 | 472 | 0.025 | +0.9 | 0.78 |
| netIncomeToAssets | +0.036 | +0.054 | 0.60 | 472 | 0.034 | +1.0 | 0.56 |
| ocfToAssets | +0.015 | +0.017 | 0.57 | 472 | 0.026 | +0.6 | 0.56 |
| negativeAccrualsToAssets | -0.009 | -0.016 | 0.46 | 472 | 0.025 | -0.4 | 0.33 |
| relative126 | +0.028 | +0.035 | 0.57 | 583 | 0.026 | +1.1 | 0.55 |
| momentum121 | +0.010 | +0.003 | 0.51 | 583 | 0.029 | +0.3 | 0.36 |
| ocfImprovementToAssets | +0.044 | +0.033 | 0.60 | 420 | 0.025 | +1.8 | 0.75 |
| negativeDownsideVol126 | +0.062 | +0.081 | 0.68 | 583 | 0.024 | +2.6 | 0.73 |
| logAdv60 | +0.041 | +0.049 | 0.60 | 583 | 0.026 | +1.6 | 0.73 |

Annual mean rank correlation (same cell):

| feature | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bookToMarketProxy | n/a | +0.30 | +0.08 | +0.11 | -0.17 | +0.07 | +0.11 | +0.03 | +0.16 | +0.05 | +0.17 | +0.12 |
| earningsYieldProxy | n/a | +0.19 | -0.09 | +0.08 | +0.06 | -0.12 | +0.11 | +0.02 | +0.15 | +0.17 | +0.18 | +0.26 |
| ocfYieldProxy | n/a | +0.13 | -0.09 | +0.05 | -0.13 | +0.03 | +0.11 | +0.03 | +0.06 | +0.04 | +0.01 | +0.19 |
| netIncomeToAssets | n/a | -0.12 | -0.01 | +0.06 | +0.24 | -0.19 | -0.07 | -0.01 | +0.06 | +0.13 | +0.11 | +0.20 |
| ocfToAssets | n/a | +0.07 | -0.16 | +0.04 | +0.11 | -0.14 | +0.01 | -0.00 | -0.01 | +0.14 | +0.05 | +0.29 |
| negativeAccrualsToAssets | n/a | +0.29 | -0.21 | -0.04 | -0.03 | +0.06 | +0.07 | -0.00 | -0.06 | +0.05 | -0.04 | +0.07 |
| relative126 | +0.02 | +0.02 | -0.03 | -0.11 | +0.07 | -0.10 | -0.05 | -0.03 | +0.11 | +0.22 | +0.15 | +0.11 |
| momentum121 | -0.02 | -0.09 | -0.05 | -0.06 | +0.05 | -0.14 | -0.06 | -0.03 | +0.10 | +0.28 | +0.12 | +0.03 |
| ocfImprovementToAssets | n/a | n/a | -0.07 | +0.15 | +0.12 | +0.01 | +0.02 | -0.01 | -0.07 | +0.15 | +0.03 | +0.04 |
| negativeDownsideVol126 | +0.07 | +0.07 | -0.05 | +0.15 | +0.01 | -0.07 | +0.21 | +0.07 | +0.15 | +0.12 | -0.06 | +0.10 |
| logAdv60 | -0.06 | +0.20 | +0.13 | -0.10 | +0.15 | +0.06 | -0.17 | +0.01 | +0.03 | +0.01 | +0.17 | +0.09 |

## 3. Stock − market vs stock − leave-one-out industry

Reference A is the SEALED `kr-factor-anatomy-v1` mean per-date rank correlation (stock − market, PIT Top120, v1 terminal discipline), read from its pinned result and not recomputed; it is on a different (larger) sample. A' is this study's own same-sample stock − market reading of the RAW feature. B is this study's within-industry rank vs stock − leave-one-out industry. Shift classes use the conventions frozen in the spec (|mean| < 0.01 is not a direction; ratio >= 0.75 SURVIVES; >= 0.25 WEAKENS_MATERIALLY; otherwise LARGELY_ABSORBED); they are interpretive, never tests.

H126 (CAP_WEIGHTED, FULL):

| feature | A sealed stock−market | A' same-sample stock−market (raw) | raw feature vs stock−LOO industry | B within-industry vs stock−LOO industry | LOO industry−market (raw) | B vs A | B vs A' |
|---|---:|---:|---:|---:|---:|---|---|
| bookToMarketProxy | +0.097 | +0.108 | +0.093 | +0.086 | +0.010 | SURVIVES (+0.88) | SURVIVES (+0.80) |
| earningsYieldProxy | +0.065 | +0.088 | +0.060 | +0.073 | +0.033 | SURVIVES (+1.11) | SURVIVES (+0.82) |
| ocfYieldProxy | +0.026 | +0.043 | -0.002 | +0.022 | +0.072 | SURVIVES (+0.85) | WEAKENS_MATERIALLY (+0.51) |
| netIncomeToAssets | +0.021 | +0.026 | +0.040 | +0.036 | -0.025 | SURVIVES (+1.69) | SURVIVES (+1.37) |
| ocfToAssets | +0.008 | +0.019 | +0.006 | +0.015 | +0.018 | REFERENCE_NEAR_ZERO (n/a) | SURVIVES (+0.80) |
| negativeAccrualsToAssets | +0.009 | +0.012 | -0.012 | -0.009 | +0.037 | REFERENCE_NEAR_ZERO (n/a) | ABSORBED_TO_NEAR_ZERO (-0.76) |
| relative126 | +0.020 | +0.038 | +0.030 | +0.028 | +0.026 | SURVIVES (+1.36) | WEAKENS_MATERIALLY (+0.73) |
| momentum121 | +0.004 | +0.025 | +0.019 | +0.010 | +0.015 | REFERENCE_NEAR_ZERO (n/a) | ABSORBED_TO_NEAR_ZERO (+0.38) |
| ocfImprovementToAssets | +0.018 | +0.043 | +0.035 | +0.044 | +0.004 | SURVIVES (+2.47) | SURVIVES (+1.04) |
| negativeDownsideVol126 | +0.082 | +0.080 | +0.070 | +0.062 | +0.025 | SURVIVES (+0.76) | SURVIVES (+0.78) |
| logAdv60 | +0.015 | +0.028 | +0.009 | +0.041 | +0.030 | SURVIVES (+2.68) | SURVIVES (+1.47) |

H252 (CAP_WEIGHTED, FULL):

| feature | A sealed stock−market | A' same-sample stock−market (raw) | raw feature vs stock−LOO industry | B within-industry vs stock−LOO industry | LOO industry−market (raw) | B vs A | B vs A' |
|---|---:|---:|---:|---:|---:|---|---|
| bookToMarketProxy | +0.116 | +0.129 | +0.113 | +0.102 | +0.001 | SURVIVES (+0.88) | SURVIVES (+0.79) |
| earningsYieldProxy | +0.061 | +0.093 | +0.054 | +0.069 | +0.004 | SURVIVES (+1.13) | WEAKENS_MATERIALLY (+0.75) |
| ocfYieldProxy | +0.024 | +0.056 | +0.003 | +0.036 | +0.081 | SURVIVES (+1.50) | WEAKENS_MATERIALLY (+0.64) |
| netIncomeToAssets | +0.016 | +0.023 | +0.025 | +0.011 | -0.031 | WEAKENS_MATERIALLY (+0.70) | WEAKENS_MATERIALLY (+0.47) |
| ocfToAssets | +0.001 | +0.021 | -0.006 | -0.012 | +0.041 | REFERENCE_NEAR_ZERO (n/a) | CHANGES_SIGN (-0.58) |
| negativeAccrualsToAssets | +0.013 | +0.031 | +0.001 | +0.003 | +0.071 | ABSORBED_TO_NEAR_ZERO (+0.24) | ABSORBED_TO_NEAR_ZERO (+0.10) |
| relative126 | +0.004 | +0.016 | +0.009 | +0.003 | +0.016 | REFERENCE_NEAR_ZERO (n/a) | ABSORBED_TO_NEAR_ZERO (+0.20) |
| momentum121 | -0.027 | -0.011 | -0.008 | -0.018 | -0.009 | WEAKENS_MATERIALLY (+0.68) | SURVIVES (+1.69) |
| ocfImprovementToAssets | +0.015 | +0.048 | +0.029 | +0.052 | +0.035 | SURVIVES (+3.44) | SURVIVES (+1.08) |
| negativeDownsideVol126 | +0.114 | +0.109 | +0.088 | +0.085 | +0.019 | WEAKENS_MATERIALLY (+0.75) | SURVIVES (+0.78) |
| logAdv60 | +0.024 | +0.038 | +0.008 | +0.046 | +0.049 | SURVIVES (+1.90) | SURVIVES (+1.21) |

Both lenses and all three components of the primary H126 cell (mean per-date rank correlation, FULL, CAP_WEIGHTED):

| feature | RAW vs stock−LOO | WITHIN vs stock−LOO | RAW vs LOO industry−market | WITHIN vs LOO industry−market | RAW vs stock−market | WITHIN vs stock−market |
|---|---:|---:|---:|---:|---:|---:|
| bookToMarketProxy | +0.093 | +0.086 | +0.010 | -0.022 | +0.108 | +0.082 |
| earningsYieldProxy | +0.060 | +0.073 | +0.033 | -0.015 | +0.088 | +0.076 |
| ocfYieldProxy | -0.002 | +0.022 | +0.072 | -0.004 | +0.043 | +0.022 |
| netIncomeToAssets | +0.040 | +0.036 | -0.025 | -0.006 | +0.026 | +0.036 |
| ocfToAssets | +0.006 | +0.015 | +0.018 | -0.002 | +0.019 | +0.019 |
| negativeAccrualsToAssets | -0.012 | -0.009 | +0.037 | +0.001 | +0.012 | -0.013 |
| relative126 | +0.030 | +0.028 | +0.026 | -0.002 | +0.038 | +0.018 |
| momentum121 | +0.019 | +0.010 | +0.015 | -0.001 | +0.025 | +0.005 |
| ocfImprovementToAssets | +0.035 | +0.044 | +0.004 | -0.008 | +0.043 | +0.039 |
| negativeDownsideVol126 | +0.070 | +0.062 | +0.025 | -0.007 | +0.080 | +0.065 |
| logAdv60 | +0.009 | +0.041 | +0.030 | -0.003 | +0.028 | +0.033 |

## 4. Sign stability over the eight registered views

Views: FULL and EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX x CAP_WEIGHTED and EQUAL_WEIGHT at H126; FULL CAP_WEIGHTED at H63 and H252; FULL CAP_WEIGHTED H126 over the PRE_2025 and 2025+ outcome windows. Only the sign of each view's mean is read.

| feature | label | positive views | negative views | views read |
|---|---|---:|---:|---:|
| bookToMarketProxy | POSITIVE_IN_ALL_REGISTERED_VIEWS | 8 | 0 | 8 / 8 |
| earningsYieldProxy | POSITIVE_IN_ALL_REGISTERED_VIEWS | 8 | 0 | 8 / 8 |
| ocfYieldProxy | POSITIVE_IN_ALL_REGISTERED_VIEWS | 8 | 0 | 8 / 8 |
| netIncomeToAssets | POSITIVE_IN_ALL_REGISTERED_VIEWS | 8 | 0 | 8 / 8 |
| ocfToAssets | SIGN_DEPENDS_ON_VIEW | 6 | 2 | 8 / 8 |
| negativeAccrualsToAssets | SIGN_DEPENDS_ON_VIEW | 1 | 7 | 8 / 8 |
| relative126 | SIGN_DEPENDS_ON_VIEW | 7 | 1 | 8 / 8 |
| momentum121 | SIGN_DEPENDS_ON_VIEW | 6 | 2 | 8 / 8 |
| ocfImprovementToAssets | POSITIVE_IN_ALL_REGISTERED_VIEWS | 8 | 0 | 8 / 8 |
| negativeDownsideVol126 | SIGN_DEPENDS_ON_VIEW | 7 | 1 | 8 / 8 |
| logAdv60 | POSITIVE_IN_ALL_REGISTERED_VIEWS | 8 | 0 | 8 / 8 |

## 5. Weight lens, horizon and sensitivity grid (within-industry rank vs stock − leave-one-out industry)

| feature | FULL CAP H63 | FULL CAP H126 | FULL CAP H252 | FULL EQ H63 | FULL EQ H126 | FULL EQ H252 | EXCL CAP H63 | EXCL CAP H126 | EXCL CAP H252 | EXCL EQ H63 | EXCL EQ H126 | EXCL EQ H252 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bookToMarketProxy | +0.068 | +0.086 | +0.102 | +0.068 | +0.087 | +0.099 | +0.069 | +0.087 | +0.105 | +0.068 | +0.087 | +0.100 |
| earningsYieldProxy | +0.055 | +0.073 | +0.069 | +0.059 | +0.081 | +0.078 | +0.051 | +0.069 | +0.067 | +0.055 | +0.075 | +0.074 |
| ocfYieldProxy | +0.018 | +0.022 | +0.036 | +0.020 | +0.026 | +0.035 | +0.018 | +0.019 | +0.032 | +0.018 | +0.023 | +0.030 |
| netIncomeToAssets | +0.023 | +0.036 | +0.011 | +0.027 | +0.040 | +0.021 | +0.018 | +0.030 | +0.004 | +0.022 | +0.034 | +0.013 |
| ocfToAssets | +0.006 | +0.015 | -0.012 | +0.010 | +0.020 | -0.009 | -0.001 | +0.003 | -0.031 | +0.001 | +0.008 | -0.028 |
| negativeAccrualsToAssets | -0.017 | -0.009 | +0.003 | -0.019 | -0.014 | -0.008 | -0.022 | -0.016 | -0.009 | -0.024 | -0.019 | -0.021 |
| relative126 | +0.005 | +0.028 | +0.003 | +0.006 | +0.030 | +0.006 | +0.003 | +0.027 | +0.000 | +0.005 | +0.030 | +0.006 |
| momentum121 | +0.012 | +0.010 | -0.018 | +0.013 | +0.012 | -0.017 | +0.009 | +0.008 | -0.023 | +0.011 | +0.011 | -0.018 |
| ocfImprovementToAssets | +0.017 | +0.044 | +0.052 | +0.020 | +0.048 | +0.053 | +0.018 | +0.039 | +0.037 | +0.019 | +0.042 | +0.040 |
| negativeDownsideVol126 | +0.039 | +0.062 | +0.085 | +0.042 | +0.067 | +0.088 | +0.040 | +0.062 | +0.086 | +0.041 | +0.066 | +0.085 |
| logAdv60 | +0.022 | +0.041 | +0.046 | +0.026 | +0.044 | +0.049 | +0.013 | +0.031 | +0.033 | +0.017 | +0.033 | +0.036 |

EXCL = Samsung Electronics and SK Hynix removed before cohorts, ranks and weights.

## 6. Outcome-window slices and signal-date market state (FULL, CAP_WEIGHTED H126)

| feature | PRE_2025 | dates | 2025+ | dates | state 1.0 | dates | state 0.7 | dates | state 0.4 | dates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bookToMarketProxy | +0.078 | 429 | +0.123 | 89 | +0.089 | 306 | +0.084 | 192 | +0.056 | 20 |
| earningsYieldProxy | +0.052 | 383 | +0.160 | 89 | +0.067 | 260 | +0.087 | 192 | +0.010 | 20 |
| ocfYieldProxy | +0.020 | 383 | +0.028 | 89 | -0.001 | 260 | +0.052 | 192 | +0.020 | 20 |
| netIncomeToAssets | +0.017 | 383 | +0.117 | 89 | +0.025 | 260 | +0.055 | 192 | -0.013 | 20 |
| ocfToAssets | -0.005 | 383 | +0.102 | 89 | -0.007 | 260 | +0.050 | 192 | -0.038 | 20 |
| negativeAccrualsToAssets | -0.010 | 383 | -0.007 | 89 | -0.025 | 260 | +0.009 | 192 | +0.025 | 20 |
| relative126 | -0.000 | 494 | +0.181 | 89 | +0.046 | 334 | -0.003 | 229 | +0.067 | 20 |
| momentum121 | -0.017 | 494 | +0.158 | 89 | +0.019 | 334 | -0.014 | 229 | +0.121 | 20 |
| ocfImprovementToAssets | +0.038 | 331 | +0.068 | 89 | +0.017 | 212 | +0.070 | 188 | +0.096 | 20 |
| negativeDownsideVol126 | +0.076 | 494 | -0.014 | 89 | +0.068 | 334 | +0.065 | 229 | -0.064 | 20 |
| logAdv60 | +0.025 | 494 | +0.128 | 89 | +0.052 | 334 | +0.025 | 229 | +0.037 | 20 |

The 0.4 state has few dates; read it as a count, not a regime estimate.

## 7. Secondary statistics that do not let large industries dominate (FULL, CAP_WEIGHTED H126)

Equal-industry rank correlation is invariant to the within-industry transform. The group spread is top minus bottom third by feature inside an industry-date (at least 2 stocks per group), averaged with equal weight per industry (at least 3 industries) then per date; ties across a group boundary invalidate the industry-date.

| feature | equal-industry rank correlation | valid dates | mean industries per date | group spread (pp) | valid dates | mean industries per date |
|---|---:|---:|---:|---:|---:|---:|
| bookToMarketProxy | +0.120 | 518 | 7.1 | +5.48 | 518 | 7.1 |
| earningsYieldProxy | +0.103 | 472 | 5.8 | +6.81 | 472 | 5.8 |
| ocfYieldProxy | +0.051 | 472 | 5.7 | +2.20 | 472 | 5.7 |
| netIncomeToAssets | +0.034 | 472 | 5.7 | +3.51 | 472 | 5.7 |
| ocfToAssets | +0.030 | 472 | 5.7 | +0.46 | 472 | 5.7 |
| negativeAccrualsToAssets | +0.001 | 472 | 5.5 | -2.49 | 472 | 5.5 |
| relative126 | +0.019 | 583 | 7.5 | +5.07 | 583 | 7.5 |
| momentum121 | -0.010 | 583 | 7.4 | +3.55 | 583 | 7.4 |
| ocfImprovementToAssets | +0.056 | 420 | 5.6 | +4.38 | 420 | 5.6 |
| negativeDownsideVol126 | +0.089 | 583 | 7.5 | +2.08 | 583 | 7.5 |
| logAdv60 | +0.020 | 583 | 7.5 | +3.50 | 583 | 7.5 |

## 8. The five registered questions (tables of the registered numbers, not an answer key)

### Q1_BOOK_TO_MARKET_RETAINS_ASSOCIATION

| feature | mean (primary) | valid dates | sign label | B vs A | B vs A' |
|---|---:|---:|---|---|---|
| bookToMarketProxy | +0.086 | 518 | POSITIVE_IN_ALL_REGISTERED_VIEWS | SURVIVES | SURVIVES |

### Q2_MOMENTUM_AFTER_INDUSTRY_MOMENTUM_REMOVED

| feature | mean (primary) | valid dates | sign label | B vs A | B vs A' |
|---|---:|---:|---|---|---|
| momentum121 | +0.010 | 583 | SIGN_DEPENDS_ON_VIEW | REFERENCE_NEAR_ZERO | ABSORBED_TO_NEAR_ZERO |
| relative126 | +0.028 | 583 | SIGN_DEPENDS_ON_VIEW | SURVIVES | WEAKENS_MATERIALLY |

### Q3_QUALITY_CASHFLOW_IMPROVEMENT_STOCK_SPECIFIC_OR_INDUSTRY

| feature | mean (primary) | valid dates | sign label | B vs A | B vs A' |
|---|---:|---:|---|---|---|
| earningsYieldProxy | +0.073 | 472 | POSITIVE_IN_ALL_REGISTERED_VIEWS | SURVIVES | SURVIVES |
| negativeAccrualsToAssets | -0.009 | 472 | SIGN_DEPENDS_ON_VIEW | REFERENCE_NEAR_ZERO | ABSORBED_TO_NEAR_ZERO |
| netIncomeToAssets | +0.036 | 472 | POSITIVE_IN_ALL_REGISTERED_VIEWS | SURVIVES | SURVIVES |
| ocfImprovementToAssets | +0.044 | 420 | POSITIVE_IN_ALL_REGISTERED_VIEWS | SURVIVES | SURVIVES |
| ocfToAssets | +0.015 | 472 | SIGN_DEPENDS_ON_VIEW | REFERENCE_NEAR_ZERO | SURVIVES |
| ocfYieldProxy | +0.022 | 472 | POSITIVE_IN_ALL_REGISTERED_VIEWS | SURVIVES | WEAKENS_MATERIALLY |

### Q4_LIQUIDITY_AFTER_INDUSTRY_CONTROL

| feature | mean (primary) | valid dates | sign label | B vs A | B vs A' |
|---|---:|---:|---|---|---|
| logAdv60 | +0.041 | 583 | POSITIVE_IN_ALL_REGISTERED_VIEWS | SURVIVES | SURVIVES |

`logAdv60` size control (CAP_WEIGHTED H126; within-industry size is a context variable, not a feature):

| sensitivity | rank overlap with within-industry size | lower half by size | dates | upper half by size | dates |
|---|---:|---:|---:|---:|---:|
| EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX | +0.674 | +0.043 | 583 | +0.033 | 583 |
| FULL | +0.690 | +0.040 | 583 | +0.054 | 583 |

### Q5_DOWNSIDE_VOLATILITY_REGIME_AFTER_INDUSTRY_NEUTRALISATION

| feature | mean (primary) | valid dates | sign label | B vs A | B vs A' |
|---|---:|---:|---|---|---|
| negativeDownsideVol126 | +0.062 | 583 | SIGN_DEPENDS_ON_VIEW | SURVIVES | SURVIVES |

`negativeDownsideVol126` by signal-date market state (CAP_WEIGHTED H126):

| sensitivity | state 1.0 | dates | state 0.7 | dates | state 0.4 | dates |
|---|---:|---:|---:|---:|---:|---:|
| EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX | +0.068 | 334 | +0.064 | 229 | -0.052 | 20 |
| FULL | +0.068 | 334 | +0.065 | 229 | -0.064 | 20 |

## 9. Observed

* Registered features positive in all eight views: bookToMarketProxy, earningsYieldProxy, ocfYieldProxy, netIncomeToAssets, ocfImprovementToAssets, logAdv60.
* Registered features whose sign depends on the view: ocfToAssets, negativeAccrualsToAssets, relative126, momentum121, negativeDownsideVol126.
* Shift versus the sealed stock − market reading at H126 (conventions frozen before outcomes): REFERENCE_NEAR_ZERO: 3; SURVIVES: 8. Features that change sign against the sealed reading at H126: none.
* Shift at H252 versus the sealed stock − market reading: ABSORBED_TO_NEAR_ZERO: 1; REFERENCE_NEAR_ZERO: 2; SURVIVES: 5; WEAKENS_MATERIALLY: 3. Features that change sign: none.
* Shift at H252 versus the same-sample stock − market reading: ABSORBED_TO_NEAR_ZERO: 2; CHANGES_SIGN: 1; SURVIVES: 5; WEAKENS_MATERIALLY: 3. Features that change sign: ocfToAssets.
* The leave-one-out industry component (RAW feature vs industry − market) has |mean| >= 0.05 only for: ocfYieldProxy.
* The largest |mean / descriptive standard error| among the primary cells is 2.9 (bookToMarketProxy); the descriptive standard error is itself an approximation under overlapping weekly dates and no multiplicity correction is applied.

## 10. Hypotheses (for a NEW preregistration on an independent sample; none is tested here)

* The book-to-market and earnings-yield associations are not an industry-composition artefact: they keep their sign and most of their size after the industry component is removed.
* The `logAdv60` association was not only a size or mega-cap or industry-composition effect in this sample, but its size-control and mega-cap-exclusion readings are descriptive and the sample is exposed.
* `negativeDownsideVol126` and `relative126` look regime- or window-dependent rather than stable once industry is removed.
* Accrual and cash-flow-to-asset features carry little within-industry information here, and their coverage differs by region of the history (Korean value and quality are dark in the first years).

## 11. Not established

* That any feature predicts forward returns, has been validated, or should be used for selection, weighting or a portfolio.
* That the within-industry readings are PIT-exact: the industry history is a reconstruction and terminal securities are unclassified.
* That these readings survive an independent sample, a multiplicity correction, or a change of benchmark, taxonomy, horizon or weighting.
* That a sealed prior result was wrong or right: the comparison is interpretive, on a different sample, and the sealed studies were not rerun.

## 12. Limitations

Outcome-exposed single sample; reconstructed industry history; peer sets of four to a few dozen names make the leave-one-out benchmark noisy; weekly signals overlap; large caps only; partial-distribution return basis (banks and high-dividend names unreliable); issue-cap accounting proxies; no multiplicity correction; any peer without a matured return makes a target unresolved; a within-industry rank removes industry composition, not size, mega-cap or sector-cycle effects inside an industry.
