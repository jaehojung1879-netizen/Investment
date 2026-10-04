# kr-industry-opportunity-anatomy-v1 — sealed exploratory result

**Status: `EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY`.** Descriptive historical associations on a partially reconstructed history. Not confirmatory, not validated, not production-ready, not prospective. The membership underneath ended `DATA_FOUNDATION_INSUFFICIENT_V4` under its own frozen gates; this study ran under a separately preregistered exploratory eligibility rule and that result is not relabelled.

This report is rendered from the committed exact result bytes by `scripts/render_kr_industry_anatomy_v1_report.py`. It reads numbers and recomputes nothing. The formal one-shot execution (run 37182657697) has been spent and cannot be rerun.

* Return basis: `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS` (adjusted index, partial observed distributions; not total shareholder return). Benchmark: `069500.KS`.
* Target: industry return (cohort and weights fixed at the signal date) minus the same-window benchmark return. Primary: CAP_WEIGHTED H126. Descriptive: H63, H252, EQUAL_WEIGHT.
* Statistic: per-date cross-sectional Spearman across eligible industries (IC) and top-minus-bottom tercile spread, then the mean over dates. Weekly signals overlap, so the number of independent observations is far smaller than the date counts shown.

## 1. Eligibility and coverage

| Sensitivity | industry-dates | eligible | ineligible (below 5 classified members) | eligible industries per date min / median / max |
|---|---:|---:|---:|---|
| FULL | 8540 | 5818 | 2722 | 6 / 10 / 12 |
| LEAVE_LARGEST_CONSTITUENT_OUT | 8540 | 4586 | 3954 | 5 / 8 / 10 |
| EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX | 8540 | 5818 | 2722 | 6 / 10 / 12 |

`meanClassifiedCoverage` in the raw result (about 0.068) is the average SHARE OF THE 120-NAME COHORT held by one industry, not membership coverage; overall classified coverage is the v4 figure (95.295% of 73,200 name-dates, terminal securities unclassified). An ineligible industry-date is INELIGIBLE, not zero.

Feature and target coverage (FULL, CAP_WEIGHTED H126; eligible industry-dates = 5818, target finite = 5644):

| Feature | feature finite | both finite | IC valid dates | tercile valid dates |
|---|---:|---:|---:|---:|
| BREADTH_ABOVE_MA_126 | 5164 | 5002 | 405 | 174 |
| BREADTH_POSITIVE_126 | 5159 | 4997 | 404 | 191 |
| BREADTH_REL_MOM_POSITIVE_126 | 5159 | 4997 | 404 | 211 |
| CONSTITUENT_COUNT | 5818 | 5644 | 565 | 178 |
| CONSTITUENT_DISPERSION_126 | 5159 | 4997 | 404 | 294 |
| DOWNSIDE_VOL_126 | 5159 | 4997 | 404 | 294 |
| MEDIAN_LOG_ADV60 | 5818 | 5644 | 565 | 408 |
| MEDIAN_bookToMarketProxy | 4718 | 4544 | 434 | 289 |
| MEDIAN_earningsYieldProxy | 4109 | 3935 | 334 | 188 |
| MEDIAN_negativeAccrualsToAssets | 4041 | 3867 | 333 | 186 |
| MEDIAN_netIncomeImprovementToAssets | 3608 | 3434 | 248 | 151 |
| MEDIAN_netIncomeToAssets | 4104 | 3930 | 334 | 188 |
| MEDIAN_ocfImprovementToAssets | 3503 | 3329 | 216 | 143 |
| MEDIAN_ocfToAssets | 4069 | 3895 | 337 | 189 |
| MEDIAN_ocfYieldProxy | 4069 | 3895 | 337 | 189 |
| REL_MOM_126 | 5159 | 4997 | 404 | 294 |
| REL_MOM_63 | 5525 | 5351 | 472 | 370 |
| TOP1_CAP_SHARE | 5818 | 5644 | 565 | 408 |
| TOP2_CAP_SHARE | 5818 | 5644 | 565 | 408 |

A date is valid for IC only with at least 8 eligible industries holding both values, and for the tercile spread with at least 9; fundamentals are missing far more often than price features, and missing is never zero.

## 2. Primary anatomy: CAP_WEIGHTED, H126 (all 19 features, no selection)

| Feature | IC mean | IC median | IC positive share | IC valid dates | HAC se (descriptive) | IC mean / se (descriptive) | tercile spread (pp) | tercile positive share | tercile valid dates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BREADTH_ABOVE_MA_126 | +0.059 | +0.065 | 0.59 | 405 | 0.050 | +1.2 | +3.2 | 0.61 | 174 |
| BREADTH_POSITIVE_126 | +0.023 | +0.037 | 0.54 | 404 | 0.050 | +0.5 | +2.7 | 0.63 | 191 |
| BREADTH_REL_MOM_POSITIVE_126 | -0.013 | -0.008 | 0.49 | 404 | 0.057 | -0.2 | +3.7 | 0.63 | 211 |
| CONSTITUENT_COUNT | +0.046 | +0.049 | 0.55 | 565 | 0.054 | +0.9 | -4.1 | 0.27 | 178 |
| CONSTITUENT_DISPERSION_126 | +0.069 | +0.038 | 0.55 | 404 | 0.056 | +1.2 | +4.5 | 0.63 | 294 |
| DOWNSIDE_VOL_126 | +0.003 | +0.016 | 0.51 | 404 | 0.060 | +0.1 | +3.1 | 0.61 | 294 |
| MEDIAN_LOG_ADV60 | +0.027 | +0.033 | 0.53 | 565 | 0.056 | +0.5 | +2.7 | 0.61 | 408 |
| MEDIAN_bookToMarketProxy | -0.059 | -0.045 | 0.46 | 434 | 0.072 | -0.8 | -0.3 | 0.60 | 289 |
| MEDIAN_earningsYieldProxy | +0.038 | +0.003 | 0.50 | 334 | 0.049 | +0.8 | -1.4 | 0.49 | 188 |
| MEDIAN_negativeAccrualsToAssets | +0.039 | +0.033 | 0.54 | 333 | 0.068 | +0.6 | +2.8 | 0.53 | 186 |
| MEDIAN_netIncomeImprovementToAssets | -0.185 | -0.214 | 0.26 | 248 | 0.062 | -3.0 | -10.1 | 0.19 | 151 |
| MEDIAN_netIncomeToAssets | -0.027 | +0.000 | 0.49 | 334 | 0.059 | -0.5 | -1.3 | 0.53 | 188 |
| MEDIAN_ocfImprovementToAssets | +0.009 | -0.029 | 0.48 | 216 | 0.070 | +0.1 | -5.1 | 0.36 | 143 |
| MEDIAN_ocfToAssets | +0.001 | -0.017 | 0.48 | 337 | 0.072 | +0.0 | +1.5 | 0.52 | 189 |
| MEDIAN_ocfYieldProxy | +0.136 | +0.119 | 0.60 | 337 | 0.067 | +2.0 | +4.7 | 0.66 | 189 |
| REL_MOM_126 | +0.066 | +0.079 | 0.60 | 404 | 0.056 | +1.2 | +5.4 | 0.67 | 294 |
| REL_MOM_63 | +0.045 | +0.047 | 0.53 | 472 | 0.048 | +0.9 | +2.4 | 0.56 | 370 |
| TOP1_CAP_SHARE | -0.054 | -0.027 | 0.46 | 565 | 0.053 | -1.0 | +1.3 | 0.56 | 408 |
| TOP2_CAP_SHARE | -0.013 | +0.000 | 0.50 | 565 | 0.053 | -0.2 | +2.6 | 0.62 | 408 |

The HAC standard error is Newey-West over the date series with lag ceil(H/5), labelled descriptive; the ratio is just the reported mean divided by the reported standard error. Most mean ICs sit within about one standard error of zero; the clear exceptions in the ratio column are discussed in section 6.

## 3. Horizons and lenses (IC mean; sign pattern across the six cells)

| Feature | CAP H63 | CAP H126 | CAP H252 | EW H63 | EW H126 | EW H252 | signs |
|---|---:|---:|---:|---:|---:|---:|---|
| BREADTH_ABOVE_MA_126 | +0.020 | +0.059 | +0.020 | -0.009 | +0.051 | +0.035 | +++-++ |
| BREADTH_POSITIVE_126 | -0.004 | +0.023 | -0.019 | -0.019 | +0.049 | +0.018 | -+--++ |
| BREADTH_REL_MOM_POSITIVE_126 | -0.004 | -0.013 | -0.039 | -0.015 | +0.016 | -0.004 | ----+- |
| CONSTITUENT_COUNT | +0.059 | +0.046 | +0.035 | +0.062 | +0.089 | +0.090 | ++++++ |
| CONSTITUENT_DISPERSION_126 | +0.055 | +0.069 | -0.005 | +0.053 | +0.078 | +0.019 | ++-+++ |
| DOWNSIDE_VOL_126 | +0.014 | +0.003 | -0.026 | +0.017 | -0.014 | -0.017 | ++-+-- |
| MEDIAN_LOG_ADV60 | +0.027 | +0.027 | +0.062 | +0.017 | +0.013 | +0.049 | ++++++ |
| MEDIAN_bookToMarketProxy | -0.056 | -0.059 | +0.001 | -0.051 | -0.086 | -0.008 | --+--- |
| MEDIAN_earningsYieldProxy | +0.046 | +0.038 | +0.010 | +0.022 | -0.009 | -0.044 | ++++-- |
| MEDIAN_negativeAccrualsToAssets | -0.026 | +0.039 | +0.118 | +0.004 | +0.101 | +0.179 | -+++++ |
| MEDIAN_netIncomeImprovementToAssets | -0.169 | -0.185 | -0.150 | -0.156 | -0.199 | -0.190 | ------ |
| MEDIAN_netIncomeToAssets | +0.037 | -0.027 | -0.090 | -0.018 | -0.047 | -0.102 | +----- |
| MEDIAN_ocfImprovementToAssets | -0.025 | +0.009 | -0.002 | -0.036 | -0.001 | -0.017 | -+---- |
| MEDIAN_ocfToAssets | +0.034 | +0.001 | -0.060 | +0.014 | +0.011 | -0.047 | ++-++- |
| MEDIAN_ocfYieldProxy | +0.097 | +0.136 | +0.160 | +0.076 | +0.108 | +0.154 | ++++++ |
| REL_MOM_126 | +0.038 | +0.066 | -0.010 | +0.031 | +0.091 | +0.035 | ++-+++ |
| REL_MOM_63 | +0.009 | +0.045 | +0.021 | -0.007 | +0.051 | +0.061 | +++-++ |
| TOP1_CAP_SHARE | -0.051 | -0.054 | -0.074 | -0.085 | -0.122 | -0.157 | ------ |
| TOP2_CAP_SHARE | -0.037 | -0.013 | -0.026 | -0.072 | -0.092 | -0.110 | ------ |

Features whose IC sign is identical in all six cells (rule-based, not chosen after looking): CONSTITUENT_COUNT, MEDIAN_LOG_ADV60, MEDIAN_netIncomeImprovementToAssets, MEDIAN_ocfYieldProxy, TOP1_CAP_SHARE, TOP2_CAP_SHARE.

Rank agreement between the cap-weighted and equal-weight relative returns of the same industries (per-date Spearman, mean over dates): H63 0.845 over 565 dates, positive on 1.00 of them; H126 0.860 over 565 dates, positive on 1.00 of them; H252 0.861 over 539 dates, positive on 1.00 of them.

## 4. Chronology (IC mean by signal year, CAP_WEIGHTED H126; dates in brackets)

| Feature | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BREADTH_ABOVE_MA_126 | +0.14 (53) | +0.04 (52) | +0.22 (44) | -0.15 (29) | +0.01 (48) | +0.20 (53) | -0.14 (21) | -0.12 (46) | +0.01 (43) | n/a | +0.39 (16) | n/a |
| BREADTH_POSITIVE_126 | +0.16 (53) | -0.01 (52) | +0.30 (44) | -0.20 (29) | -0.12 (48) | +0.08 (53) | -0.04 (21) | -0.18 (46) | +0.02 (43) | n/a | +0.25 (15) | n/a |
| BREADTH_REL_MOM_POSITIVE_126 | +0.12 (53) | -0.03 (52) | +0.25 (44) | -0.31 (29) | -0.06 (48) | +0.11 (53) | -0.20 (21) | -0.26 (46) | -0.07 (43) | n/a | +0.27 (15) | n/a |
| CONSTITUENT_COUNT | +0.19 (53) | -0.09 (52) | +0.14 (51) | -0.06 (52) | +0.05 (52) | -0.14 (53) | -0.14 (52) | -0.05 (52) | +0.12 (52) | +0.04 (39) | +0.43 (48) | +0.35 (9) |
| CONSTITUENT_DISPERSION_126 | +0.28 (53) | -0.07 (52) | +0.04 (44) | +0.06 (29) | +0.10 (48) | +0.19 (53) | -0.03 (21) | +0.10 (46) | -0.19 (43) | n/a | +0.21 (15) | n/a |
| DOWNSIDE_VOL_126 | -0.12 (53) | +0.02 (52) | +0.15 (44) | +0.03 (29) | -0.07 (48) | +0.17 (53) | -0.05 (21) | +0.14 (46) | -0.35 (43) | n/a | +0.22 (15) | n/a |
| MEDIAN_LOG_ADV60 | -0.18 (53) | +0.26 (52) | +0.21 (51) | +0.16 (52) | +0.34 (52) | +0.16 (53) | -0.32 (52) | +0.01 (52) | -0.14 (52) | -0.15 (39) | -0.05 (48) | -0.33 (9) |
| MEDIAN_bookToMarketProxy | n/a | +0.08 (33) | -0.09 (51) | -0.26 (26) | -0.58 (43) | +0.09 (53) | +0.24 (52) | +0.16 (52) | -0.13 (28) | -0.32 (39) | -0.11 (48) | +0.34 (9) |
| MEDIAN_earningsYieldProxy | n/a | n/a | +0.25 (34) | +0.10 (19) | -0.16 (43) | -0.17 (53) | +0.05 (52) | +0.01 (52) | -0.23 (21) | +0.43 (8) | +0.29 (43) | +0.46 (9) |
| MEDIAN_negativeAccrualsToAssets | n/a | n/a | -0.11 (34) | -0.08 (19) | +0.36 (43) | +0.30 (53) | +0.09 (51) | -0.18 (52) | +0.11 (21) | -0.73 (8) | -0.11 (43) | -0.04 (9) |
| MEDIAN_netIncomeImprovementToAssets | n/a | n/a | -0.05 (6) | n/a | -0.21 (43) | -0.46 (53) | -0.16 (52) | -0.06 (50) | +0.11 (21) | n/a | +0.16 (14) | -0.56 (9) |
| MEDIAN_netIncomeToAssets | n/a | n/a | +0.00 (34) | -0.18 (19) | +0.17 (43) | -0.33 (53) | -0.16 (52) | +0.12 (52) | -0.07 (21) | +0.23 (8) | +0.12 (43) | +0.08 (9) |
| MEDIAN_ocfImprovementToAssets | n/a | n/a | +0.43 (6) | n/a | +0.11 (43) | -0.05 (53) | +0.28 (24) | -0.23 (46) | -0.07 (21) | n/a | +0.23 (14) | -0.08 (9) |
| MEDIAN_ocfToAssets | n/a | n/a | +0.15 (38) | -0.29 (19) | +0.40 (43) | +0.14 (53) | -0.16 (51) | -0.21 (52) | +0.08 (21) | -0.53 (8) | -0.07 (43) | +0.02 (9) |
| MEDIAN_ocfYieldProxy | n/a | n/a | +0.42 (38) | -0.21 (19) | -0.09 (43) | +0.29 (53) | +0.26 (51) | +0.28 (52) | +0.18 (21) | -0.34 (8) | -0.16 (43) | +0.08 (9) |
| REL_MOM_126 | +0.22 (53) | +0.09 (52) | +0.29 (44) | -0.18 (29) | +0.03 (48) | +0.15 (53) | -0.04 (21) | -0.09 (46) | -0.09 (43) | n/a | +0.18 (15) | n/a |
| REL_MOM_63 | +0.09 (53) | +0.04 (52) | +0.16 (50) | -0.15 (42) | +0.03 (48) | +0.24 (53) | -0.21 (39) | -0.01 (52) | -0.12 (43) | +0.37 (21) | +0.20 (18) | +0.69 (1) |
| TOP1_CAP_SHARE | -0.05 (53) | +0.11 (52) | +0.01 (51) | -0.06 (52) | +0.21 (52) | +0.04 (53) | -0.20 (52) | +0.17 (52) | -0.29 (52) | -0.46 (39) | -0.23 (48) | +0.12 (9) |
| TOP2_CAP_SHARE | -0.05 (53) | +0.23 (52) | +0.09 (51) | -0.07 (52) | +0.26 (52) | +0.10 (53) | -0.15 (52) | +0.08 (52) | -0.19 (52) | -0.34 (39) | -0.21 (48) | +0.04 (9) |

Outcome-window slices (decided by entry and exit dates, boundaries fixed in the spec; IC mean and valid dates):

| Feature | FULL | PRE-2025 windows | 2025-or-later windows | touches 2026 |
|---|---:|---:|---:|---:|
| BREADTH_ABOVE_MA_126 | +0.059 (405) | +0.045 (389) | +0.391 (16) | +0.133 (9) |
| BREADTH_POSITIVE_126 | +0.023 (404) | +0.014 (389) | +0.249 (15) | +0.087 (9) |
| BREADTH_REL_MOM_POSITIVE_126 | -0.013 (404) | -0.024 (389) | +0.270 (15) | +0.131 (9) |
| CONSTITUENT_COUNT | +0.046 (565) | +0.003 (486) | +0.312 (79) | +0.350 (35) |
| CONSTITUENT_DISPERSION_126 | +0.069 (404) | +0.063 (389) | +0.211 (15) | +0.087 (9) |
| DOWNSIDE_VOL_126 | +0.003 (404) | -0.005 (389) | +0.222 (15) | +0.312 (9) |
| MEDIAN_LOG_ADV60 | +0.027 (565) | +0.054 (486) | -0.143 (79) | -0.170 (35) |
| MEDIAN_bookToMarketProxy | -0.059 (434) | -0.044 (355) | -0.129 (79) | +0.047 (35) |
| MEDIAN_earningsYieldProxy | +0.038 (334) | -0.027 (275) | +0.339 (59) | +0.325 (33) |
| MEDIAN_negativeAccrualsToAssets | +0.039 (333) | +0.086 (274) | -0.180 (59) | +0.085 (33) |
| MEDIAN_netIncomeImprovementToAssets | -0.185 (248) | -0.192 (225) | -0.118 (23) | -0.438 (15) |
| MEDIAN_netIncomeToAssets | -0.027 (334) | -0.060 (275) | +0.128 (59) | +0.260 (33) |
| MEDIAN_ocfImprovementToAssets | +0.009 (216) | -0.003 (193) | +0.108 (23) | +0.013 (15) |
| MEDIAN_ocfToAssets | +0.001 (337) | +0.028 (278) | -0.124 (59) | +0.132 (33) |
| MEDIAN_ocfYieldProxy | +0.136 (337) | +0.197 (278) | -0.149 (59) | -0.014 (33) |
| REL_MOM_126 | +0.066 (404) | +0.062 (389) | +0.178 (15) | +0.167 (9) |
| REL_MOM_63 | +0.045 (472) | +0.027 (442) | +0.297 (30) | +0.185 (10) |
| TOP1_CAP_SHARE | -0.054 (565) | -0.016 (486) | -0.283 (79) | +0.009 (35) |
| TOP2_CAP_SHARE | -0.013 (565) | +0.029 (486) | -0.269 (79) | -0.030 (35) |

The 2025-or-later and 2026 slices rest on very few dates for the price features (for example REL_MOM_126: 15 and 9) because forward windows must be complete by the development cutoff; they are descriptive only.

## 5. Mega-cap and concentration sensitivities (CAP_WEIGHTED H126; IC mean / tercile pp; IC dates, tercile dates)

| Feature | FULL | leave largest constituent out | exclude Samsung Electronics and SK Hynix |
|---|---:|---:|---:|
| BREADTH_ABOVE_MA_126 | +0.059 / +3.2 (405, 174) | +0.044 / +0.1 (200, 70) | +0.042 / +3.2 (405, 171) |
| BREADTH_POSITIVE_126 | +0.023 / +2.7 (404, 191) | +0.052 / -0.5 (200, 68) | +0.022 / +2.8 (404, 188) |
| BREADTH_REL_MOM_POSITIVE_126 | -0.013 / +3.7 (404, 211) | +0.008 / +0.3 (200, 76) | -0.020 / +2.4 (404, 206) |
| CONSTITUENT_COUNT | +0.046 / -4.1 (565, 178) | +0.070 / +1.7 (361, 75) | -0.011 / -4.0 (565, 156) |
| CONSTITUENT_DISPERSION_126 | +0.069 / +4.5 (404, 294) | +0.118 / +5.6 (200, 98) | +0.048 / +4.3 (404, 294) |
| DOWNSIDE_VOL_126 | +0.003 / +3.1 (404, 294) | -0.032 / +3.5 (200, 98) | -0.033 / +1.9 (404, 294) |
| MEDIAN_LOG_ADV60 | +0.027 / +2.7 (565, 408) | +0.111 / +5.4 (361, 158) | -0.002 / +2.4 (565, 408) |
| MEDIAN_bookToMarketProxy | -0.059 / -0.3 (434, 289) | +0.176 / +9.0 (90, 14) | -0.053 / -1.2 (434, 289) |
| MEDIAN_earningsYieldProxy | +0.038 / -1.4 (334, 188) | -0.131 / -25.1 (44, 4) | +0.003 / -3.3 (334, 188) |
| MEDIAN_negativeAccrualsToAssets | +0.039 / +2.8 (333, 186) | +0.351 / -4.0 (27, 4) | +0.029 / +1.3 (329, 175) |
| MEDIAN_netIncomeImprovementToAssets | -0.185 / -10.1 (248, 151) | -0.295 / -7.9 (37, 4) | -0.193 / -10.3 (239, 145) |
| MEDIAN_netIncomeToAssets | -0.027 / -1.3 (334, 188) | -0.413 / -23.6 (44, 4) | -0.096 / -4.0 (334, 188) |
| MEDIAN_ocfImprovementToAssets | +0.009 / -5.1 (216, 143) | -0.113 / -14.7 (20, 4) | +0.038 / -2.4 (208, 133) |
| MEDIAN_ocfToAssets | +0.001 / +1.5 (337, 189) | +0.125 / -20.6 (27, 4) | -0.035 / -0.9 (333, 185) |
| MEDIAN_ocfYieldProxy | +0.136 / +4.7 (337, 189) | +0.524 / +15.1 (27, 4) | +0.113 / +5.0 (333, 185) |
| REL_MOM_126 | +0.066 / +5.4 (404, 294) | +0.071 / +0.1 (200, 98) | +0.071 / +5.4 (404, 294) |
| REL_MOM_63 | +0.045 / +2.4 (472, 370) | -0.018 / +1.2 (259, 122) | +0.040 / +2.4 (472, 370) |
| TOP1_CAP_SHARE | -0.054 / +1.3 (565, 408) | -0.037 / +3.4 (361, 158) | -0.102 / +0.2 (565, 408) |
| TOP2_CAP_SHARE | -0.013 / +2.6 (565, 408) | -0.032 / +2.4 (361, 158) | -0.043 / +2.3 (565, 408) |

Leaving the largest constituent out shrinks the eligible cross-section (see section 1), so its fundamental columns have only a handful of tercile dates and are not informative.

Concentration strata by top-1 cap share (fixed cutoff 0.35; IC mean and valid dates within each stratum, minimum 5 industries):

| Feature | top-1 share below 0.35 | top-1 share at or above 0.35 |
|---|---:|---:|
| BREADTH_ABOVE_MA_126 | +0.031 (309) | +0.066 (185) |
| BREADTH_POSITIVE_126 | -0.002 (308) | +0.045 (184) |
| BREADTH_REL_MOM_POSITIVE_126 | -0.020 (308) | -0.030 (185) |
| CONSTITUENT_COUNT | +0.054 (387) | -0.124 (231) |
| CONSTITUENT_DISPERSION_126 | +0.125 (308) | +0.107 (185) |
| DOWNSIDE_VOL_126 | -0.150 (308) | +0.237 (185) |
| MEDIAN_LOG_ADV60 | -0.014 (387) | +0.015 (231) |
| MEDIAN_bookToMarketProxy | -0.186 (240) | +0.092 (230) |
| MEDIAN_earningsYieldProxy | -0.022 (169) | +0.166 (203) |
| MEDIAN_negativeAccrualsToAssets | +0.198 (159) | -0.075 (191) |
| MEDIAN_netIncomeImprovementToAssets | -0.258 (117) | -0.238 (199) |
| MEDIAN_netIncomeToAssets | +0.079 (169) | -0.049 (203) |
| MEDIAN_ocfImprovementToAssets | +0.011 (104) | -0.199 (163) |
| MEDIAN_ocfToAssets | +0.205 (161) | -0.117 (195) |
| MEDIAN_ocfYieldProxy | +0.016 (161) | +0.309 (195) |
| REL_MOM_126 | +0.054 (308) | +0.131 (185) |
| REL_MOM_63 | -0.011 (351) | +0.140 (213) |
| TOP2_CAP_SHARE | -0.105 (387) | +0.205 (231) |

## 6. Observed, hypothesised, not established

### Observed (descriptive, this sample only)

* Price-state features lean positive at H126: REL_MOM_126 IC +0.066, tercile +5.4 pp; BREADTH_ABOVE_MA_126 IC +0.059, tercile +3.2 pp; CONSTITUENT_DISPERSION_126 IC +0.069, tercile +4.5 pp. The ICs are small (a few hundredths) and positive on roughly 55–60% of dates. Positive-share and relative-momentum breadth variants are weaker or mixed (see section 2).
* REL_MOM_126 across horizons and lenses: IC +0.038, +0.066, -0.010, +0.031, +0.091, +0.035 (CAP H63/H126/H252, EW H63/H126/H252); the CAP H252 value is slightly negative, so the pattern is not uniform across horizons.
* Leaving the largest constituent out: REL_MOM_126 IC stays +0.071 but its tercile spread falls from +5.4 to +0.1 pp; CONSTITUENT_DISPERSION_126 keeps both (+0.118, +5.6 pp); excluding only Samsung Electronics and SK Hynix leaves REL_MOM_126 essentially unchanged (+5.4 pp).
* MEDIAN_netIncomeImprovementToAssets is negative in every cell (IC -0.185, tercile -10.1 pp at CAP H126), in both lenses, pre-2025 and 2025-or-later, and under both mega-cap sensitivities. MEDIAN_ocfImprovementToAssets does not show it (IC +0.009, tercile -5.1 pp).
* MEDIAN_ocfYieldProxy has the largest positive IC (+0.136, tercile +4.7 pp) and positive signs in all six cells, but its slices disagree: +0.197 over 278 pre-2025 dates against -0.149 over 59 later dates.
* Industry book-to-market did not reproduce the stock-level association: IC -0.059, tercile -0.3 pp at CAP H126, with mixed signs across cells.
* Descriptive IC / HAC-standard-error ratios at CAP H126: REL_MOM_126 +1.2, BREADTH_ABOVE_MA_126 +1.2, CONSTITUENT_DISPERSION_126 +1.2, MEDIAN_ocfYieldProxy +2.0, MEDIAN_netIncomeImprovementToAssets -3.0, MEDIAN_bookToMarketProxy -0.8. Only the two fundamental features exceed two in absolute value; with overlapping signals, about fourteen coarse industries and no multiplicity correction these are descriptive magnitudes, not tests.
* Cap-weighted and equal-weight future industry-return rankings agree strongly (section 3), so the rankings are not dominated by a single mega-cap.

### Plausible hypotheses (not tested here)

* Industry relative momentum and breadth may carry useful historical state information at multi-month horizons.
* Improving earnings measures may already be anticipated by prices, so improvement could lag rather than lead returns.
* Industry-level value may behave differently from stock-level value because industry aggregates mix quality and business-cycle composition.
* Concentration and the recent mega-cap regime may condition some effects (the strata and 2025-or-later slices differ from the pre-2025 pattern for several features).

### Not established

This study does NOT establish prospective predictability, causality, a profitable implementable industry-rotation strategy, optimal feature weights, optimal thresholds or any production allocation rule. Nothing here is an investment recommendation.

## 7. Limitations

* Exploratory, outcome-exposed single historical sample; 19 features × 6 target cells × 3 sensitivities × several slices with no multiplicity correction. No isolated number is confirmation.
* About 14 coarse industries (6–12 eligible per date); ICs and tercile spreads are noisy, and the tercile spread rests on far fewer valid dates than the IC.
* Weekly signals overlap; effective independent dates are roughly dates divided by H/5 (the result records them). The HAC standard errors are descriptive.
* The industry history is a reconstruction (current official anchor plus disclosed change events) that is not point-in-time exact; the 22 terminal securities are unclassified; most classified name-dates rest on a no-change inference.
* An industry-date is resolved only if every cohort member has a matured return, so some windows are unresolved rather than renormalised.
* Top-120 large caps only; the return basis has partial distributions, so banks and other high-dividend names are unreliable.
* No industry-specific cycle data and no revised macro history entered the study.
