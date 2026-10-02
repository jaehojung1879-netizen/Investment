# KR factor anatomy v1 — market map

**EXPLORATORY / DEVELOPMENT / HYPOTHESIS-GENERATING. Korean history through 2026-09-14 is already outcome-exposed: nothing below validates, rescues or promotes any model, factor or portfolio, and nothing alters the sealed DEVELOPMENT_REJECT of kr-model-overlay-portfolio-v1.**

**Scope: SCOPE: point-in-time TOP-120 KRX market-capitalisation LARGE CAPS only (260 securities ever held that rank, 2013-2026). Nothing here describes the whole Korean market, mid caps or small caps.**

Return basis: `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS` — the stock's and the KODEX 200 benchmark's adjusted-index return over the same sessions, dividend-reinvested ONLY where the vendor served distributions. It is neither a pure price return nor a complete total shareholder return; high-dividend stocks (banks, financials) are NOT reliably represented. Total-return analysis: DATA_FOUNDATION_REQUIRED.

Structural/sector subgroup analysis: DATA_FOUNDATION_REQUIRED (no historical classification is back-applied from today).

## A. Executive map (PIT top-120 KOSPI large-cap universe, side by side, spec order)

| factor | family | H126 D10−D1 | H126 yrs positive | H126 label | H252 D10−D1 | H252 yrs positive | H252 label |
|---|---|---|---|---|---|---|---|
| bookToMarketProxy | VALUE | 0.0654 | 0.80 | BROADLY_POSITIVE_HISTORICAL_ASSOCIATION | 0.1361 | 0.90 | NO_CLEAR_MONOTONIC_PATTERN |
| earningsYieldProxy | VALUE | 0.0230 | 0.33 | UNSTABLE_OR_REGIME_DEPENDENT | 0.0627 | 0.44 | UNSTABLE_OR_REGIME_DEPENDENT |
| ocfYieldProxy | VALUE | -0.0413 | 0.11 | NO_CLEAR_MONOTONIC_PATTERN | -0.1108 | 0.33 | NO_CLEAR_MONOTONIC_PATTERN |
| netIncomeToAssets | QUALITY | 0.0092 | 0.56 | NO_CLEAR_MONOTONIC_PATTERN | 0.0321 | 0.44 | NO_CLEAR_MONOTONIC_PATTERN |
| ocfToAssets | QUALITY | 0.0009 | 0.33 | NO_CLEAR_MONOTONIC_PATTERN | -0.0150 | 0.44 | NO_CLEAR_MONOTONIC_PATTERN |
| negativeAccrualsToAssets | QUALITY | -0.0100 | 0.33 | NO_CLEAR_MONOTONIC_PATTERN | -0.0485 | 0.44 | NO_CLEAR_MONOTONIC_PATTERN |
| relative126 | CATALYST | 0.1033 | 0.73 | CONCENTRATED_IN_SPECIFIC_STRATA | 0.1124 | 0.64 | UNSTABLE_OR_REGIME_DEPENDENT |
| momentum121 | CATALYST | 0.0697 | 0.64 | UNSTABLE_OR_REGIME_DEPENDENT | 0.0794 | 0.55 | NO_CLEAR_MONOTONIC_PATTERN |
| ocfImprovementToAssets | CATALYST | 0.0197 | 0.62 | UNSTABLE_OR_REGIME_DEPENDENT | 0.0575 | 0.62 | NO_CLEAR_MONOTONIC_PATTERN |
| negativeDownsideVol126 | RISK | 0.0027 | 0.73 | NO_CLEAR_MONOTONIC_PATTERN | 0.0080 | 0.64 | NO_CLEAR_MONOTONIC_PATTERN |
| logAdv60 | RISK | 0.0262 | 0.45 | UNSTABLE_OR_REGIME_DEPENDENT | 0.0713 | 0.55 | UNSTABLE_OR_REGIME_DEPENDENT |

## B. Factor cards

### bookToMarketProxy

Book value of equity (total assets minus total liabilities, same statement, whole entity including minority interests) divided by the KRX market capitalisation at the signal close. Higher = cheaper relative to book. 순자산/시가총액: 높을수록 장부가 대비 저평가.

Caveat: Issue-cap accounting proxy: whole-entity book over one quoted issue's market cap. Preferred shares, holding-company structures and large minority interests distort it.

**H126** — dates with deciles 518, outcome observations 51575

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.1214 | -0.1658 | 0.308 |
| D2 | -0.0739 | -0.1234 | 0.343 |
| D3 | -0.0737 | -0.1163 | 0.363 |
| D4 | -0.0511 | -0.1163 | 0.382 |
| D5 | -0.0470 | -0.1000 | 0.396 |
| D6 | -0.0523 | -0.0944 | 0.376 |
| D7 | -0.0515 | -0.0813 | 0.364 |
| D8 | -0.0676 | -0.0969 | 0.356 |
| D9 | -0.0454 | -0.0796 | 0.401 |
| D10 | -0.0560 | -0.0872 | 0.389 |

Calendar-year D10−D1: 2016: 0.2134, 2017: 0.0380, 2018: 0.0371, 2019: -0.1518, 2020: 0.1695, 2021: 0.1430, 2022: 0.0025, 2023: -0.0495, 2024: 0.2335, 2025: 0.0374, 2026: 0.1291

**H252** — dates with deciles 491, outcome observations 48420

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.2567 | -0.3244 | 0.263 |
| D2 | -0.1357 | -0.2472 | 0.317 |
| D3 | -0.1022 | -0.2212 | 0.322 |
| D4 | -0.1169 | -0.2348 | 0.348 |
| D5 | -0.0881 | -0.1925 | 0.370 |
| D6 | -0.0899 | -0.2057 | 0.353 |
| D7 | -0.0895 | -0.1615 | 0.346 |
| D8 | -0.1057 | -0.1701 | 0.339 |
| D9 | -0.1035 | -0.1739 | 0.369 |
| D10 | -0.1205 | -0.1806 | 0.349 |

Calendar-year D10−D1: 2016: 0.2526, 2017: 0.1368, 2018: 0.0445, 2019: -0.3272, 2020: 0.3773, 2021: 0.2735, 2022: 0.0055, 2023: 0.0493, 2024: 0.4491, 2025: 0.1155

### earningsYieldProxy

Trailing-twelve-month net income (당기순이익, whole entity) divided by KRX market capitalisation. Higher = more earnings per won of market value; loss-makers are negative. 이익수익률.

Caveat: Same issue-cap mismatch as book-to-market; a one-off gain inflates it, a one-off loss deflates it.

**H126** — dates with deciles 472, outcome observations 41090

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0725 | -0.1124 | 0.373 |
| D2 | -0.0779 | -0.1372 | 0.355 |
| D3 | -0.0811 | -0.1187 | 0.363 |
| D4 | -0.0547 | -0.1004 | 0.378 |
| D5 | -0.0500 | -0.1169 | 0.362 |
| D6 | -0.0712 | -0.1138 | 0.342 |
| D7 | -0.0605 | -0.0928 | 0.388 |
| D8 | -0.0409 | -0.0819 | 0.409 |
| D9 | -0.0475 | -0.0770 | 0.383 |
| D10 | -0.0495 | -0.0874 | 0.387 |

Calendar-year D10−D1: 2016: 0.0439, 2017: -0.0203, 2018: -0.0239, 2019: 0.0850, 2020: -0.1607, 2021: -0.0175, 2022: -0.0184, 2023: -0.0425, 2024: 0.0753, 2025: 0.3045, 2026: 0.1008

**H252** — dates with deciles 445, outcome observations 38076

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.1407 | -0.2169 | 0.355 |
| D2 | -0.1584 | -0.2798 | 0.358 |
| D3 | -0.1599 | -0.2252 | 0.339 |
| D4 | -0.1162 | -0.2128 | 0.317 |
| D5 | -0.0978 | -0.2013 | 0.321 |
| D6 | -0.1061 | -0.2432 | 0.306 |
| D7 | -0.1211 | -0.2190 | 0.347 |
| D8 | -0.0857 | -0.1765 | 0.382 |
| D9 | -0.0888 | -0.1628 | 0.359 |
| D10 | -0.0779 | -0.1664 | 0.353 |

Calendar-year D10−D1: 2016: -0.0362, 2017: -0.1405, 2018: 0.0447, 2019: 0.1047, 2020: -0.3121, 2021: -0.0520, 2022: -0.0364, 2023: -0.0309, 2024: 0.2014, 2025: 1.0862

### ocfYieldProxy

Trailing-twelve-month operating cash flow (영업활동현금흐름) divided by KRX market capitalisation. Higher = more operating cash per won of market value. 영업현금흐름 수익률.

Caveat: Cash flow timing (working capital, capex-heavy cycles) makes a single TTM figure noisy.

**H126** — dates with deciles 472, outcome observations 40785

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0414 | -0.0829 | 0.393 |
| D2 | -0.0600 | -0.1176 | 0.371 |
| D3 | -0.0666 | -0.1195 | 0.368 |
| D4 | -0.0595 | -0.1032 | 0.381 |
| D5 | -0.0860 | -0.1215 | 0.348 |
| D6 | -0.0617 | -0.1127 | 0.379 |
| D7 | -0.0606 | -0.0990 | 0.386 |
| D8 | -0.0404 | -0.0973 | 0.383 |
| D9 | -0.0431 | -0.0874 | 0.380 |
| D10 | -0.0827 | -0.1092 | 0.365 |

Calendar-year D10−D1: 2016: 0.1030, 2017: -0.0777, 2018: -0.0189, 2019: -0.0081, 2020: -0.0056, 2021: 0.0847, 2022: -0.0296, 2023: -0.0399, 2024: -0.1616, 2025: -0.1321, 2026: -0.1086

**H252** — dates with deciles 445, outcome observations 37743

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0466 | -0.1412 | 0.385 |
| D2 | -0.1428 | -0.2233 | 0.328 |
| D3 | -0.0814 | -0.2102 | 0.354 |
| D4 | -0.1360 | -0.2348 | 0.336 |
| D5 | -0.1689 | -0.2498 | 0.306 |
| D6 | -0.1541 | -0.2199 | 0.342 |
| D7 | -0.0615 | -0.1923 | 0.365 |
| D8 | -0.0671 | -0.2105 | 0.370 |
| D9 | -0.1089 | -0.2037 | 0.342 |
| D10 | -0.1574 | -0.2064 | 0.335 |

Calendar-year D10−D1: 2016: 0.1321, 2017: -0.0484, 2018: 0.0027, 2019: -0.1034, 2020: 0.0275, 2021: 0.1354, 2022: -0.2338, 2023: -0.1767, 2024: -0.3657, 2025: -0.3223

### netIncomeToAssets

Trailing-twelve-month net income divided by total assets: a return-on-assets style profitability measure. Higher = more profitable per won of assets. 총자산순이익률.

Caveat: Banks and other balance-sheet-heavy firms have structurally small ratios; identical numbers mean different things across company types.

**H126** — dates with deciles 472, outcome observations 41064

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0668 | -0.1077 | 0.376 |
| D2 | -0.0665 | -0.1104 | 0.375 |
| D3 | -0.0999 | -0.1261 | 0.300 |
| D4 | -0.0468 | -0.0823 | 0.404 |
| D5 | -0.0732 | -0.1112 | 0.346 |
| D6 | -0.0172 | -0.0752 | 0.416 |
| D7 | -0.0314 | -0.1034 | 0.388 |
| D8 | -0.0626 | -0.0900 | 0.392 |
| D9 | -0.0865 | -0.1164 | 0.358 |
| D10 | -0.0577 | -0.1109 | 0.380 |

Calendar-year D10−D1: 2016: -0.1543, 2017: 0.0046, 2018: 0.0130, 2019: 0.2299, 2020: -0.3637, 2021: -0.0948, 2022: -0.0716, 2023: -0.0444, 2024: 0.0862, 2025: 0.2994, 2026: 0.2784

**H252** — dates with deciles 445, outcome observations 38050

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.1366 | -0.2079 | 0.365 |
| D2 | -0.1322 | -0.2333 | 0.332 |
| D3 | -0.1750 | -0.2182 | 0.280 |
| D4 | -0.0806 | -0.1742 | 0.346 |
| D5 | -0.1333 | -0.2298 | 0.343 |
| D6 | -0.0447 | -0.1502 | 0.402 |
| D7 | -0.0631 | -0.1927 | 0.358 |
| D8 | -0.1278 | -0.2147 | 0.335 |
| D9 | -0.1573 | -0.2304 | 0.325 |
| D10 | -0.1045 | -0.2402 | 0.352 |

Calendar-year D10−D1: 2016: -0.2409, 2017: -0.1378, 2018: 0.1418, 2019: 0.3669, 2020: -0.6256, 2021: -0.1914, 2022: -0.1129, 2023: -0.1225, 2024: 0.1457, 2025: 1.2156

### ocfToAssets

Trailing-twelve-month operating cash flow divided by total assets. Higher = more operating cash generated per won of assets. 총자산영업현금흐름.

Caveat: Financial companies' operating cash flow is not comparable with industrial companies'.

**H126** — dates with deciles 472, outcome observations 40772

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0480 | -0.0804 | 0.391 |
| D2 | -0.0354 | -0.0873 | 0.374 |
| D3 | -0.0625 | -0.1048 | 0.356 |
| D4 | -0.0887 | -0.1194 | 0.362 |
| D5 | -0.0496 | -0.0794 | 0.410 |
| D6 | -0.0666 | -0.1145 | 0.352 |
| D7 | -0.0709 | -0.1154 | 0.373 |
| D8 | -0.0534 | -0.1004 | 0.387 |
| D9 | -0.0800 | -0.1179 | 0.351 |
| D10 | -0.0471 | -0.0882 | 0.398 |

Calendar-year D10−D1: 2016: 0.1252, 2017: -0.0763, 2018: -0.0110, 2019: 0.1061, 2020: -0.0808, 2021: 0.0524, 2022: -0.0770, 2023: -0.0604, 2024: -0.0130, 2025: 0.0798, 2026: 0.2732

**H252** — dates with deciles 445, outcome observations 37730

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0758 | -0.1629 | 0.371 |
| D2 | -0.0590 | -0.1562 | 0.366 |
| D3 | -0.0965 | -0.1956 | 0.318 |
| D4 | -0.1653 | -0.2398 | 0.330 |
| D5 | -0.0878 | -0.1915 | 0.359 |
| D6 | -0.1448 | -0.2239 | 0.326 |
| D7 | -0.1541 | -0.2371 | 0.307 |
| D8 | -0.1293 | -0.2256 | 0.346 |
| D9 | -0.1232 | -0.2098 | 0.375 |
| D10 | -0.0909 | -0.1955 | 0.366 |

Calendar-year D10−D1: 2016: 0.3199, 2017: -0.1037, 2018: 0.1123, 2019: 0.1686, 2020: -0.1761, 2021: 0.0314, 2022: -0.2718, 2023: -0.1685, 2024: -0.0528, 2025: 0.3927

### negativeAccrualsToAssets

(Operating cash flow minus net income) divided by total assets. Higher = profit more fully backed by cash (lower accruals); lower = profit that has not yet become cash. 발생액(음수) / 총자산.

Caveat: Large positive values can reflect depreciation-heavy or financing-linked cash flows, not only 'better earnings quality'.

**H126** — dates with deciles 472, outcome observations 39666

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0272 | -0.0865 | 0.397 |
| D2 | -0.0534 | -0.0965 | 0.391 |
| D3 | -0.0604 | -0.1018 | 0.354 |
| D4 | -0.0631 | -0.1060 | 0.379 |
| D5 | -0.0714 | -0.1121 | 0.360 |
| D6 | -0.1056 | -0.1290 | 0.337 |
| D7 | -0.0770 | -0.1162 | 0.359 |
| D8 | -0.0440 | -0.0984 | 0.383 |
| D9 | -0.0656 | -0.1111 | 0.389 |
| D10 | -0.0372 | -0.0823 | 0.404 |

Calendar-year D10−D1: 2016: 0.2391, 2017: -0.0199, 2018: -0.0389, 2019: 0.0117, 2020: 0.1710, 2021: 0.1396, 2022: -0.0115, 2023: -0.1660, 2024: -0.1000, 2025: -0.1314, 2026: 0.0716

**H252** — dates with deciles 445, outcome observations 36652

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0196 | -0.1558 | 0.366 |
| D2 | -0.0784 | -0.1901 | 0.379 |
| D3 | -0.1361 | -0.2118 | 0.336 |
| D4 | -0.1398 | -0.1957 | 0.353 |
| D5 | -0.1425 | -0.2304 | 0.305 |
| D6 | -0.2242 | -0.2725 | 0.279 |
| D7 | -0.1605 | -0.2403 | 0.325 |
| D8 | -0.0531 | -0.2136 | 0.355 |
| D9 | -0.1161 | -0.2233 | 0.358 |
| D10 | -0.0681 | -0.1736 | 0.402 |

Calendar-year D10−D1: 2016: 0.4371, 2017: 0.0447, 2018: 0.0062, 2019: -0.0560, 2020: 0.2875, 2021: 0.2157, 2022: -0.0701, 2023: -0.3457, 2024: -0.1782, 2025: -0.5517

### relative126

The stock's adjusted-index return minus the KODEX 200 benchmark's over the 126 sessions ending at the signal close: the prior benchmark-relative run-up (higher) or slide (lower). 직전 126거래일 벤치마크 대비 상대수익률.

Caveat: Measured on the same adjusted-index basis as the outcome (dividends included only where the vendor served them).

**H126** — dates with deciles 583, outcome observations 68867

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0900 | -0.1125 | 0.354 |
| D2 | -0.0796 | -0.1013 | 0.366 |
| D3 | -0.0686 | -0.0983 | 0.377 |
| D4 | -0.0621 | -0.0890 | 0.391 |
| D5 | -0.0590 | -0.0877 | 0.391 |
| D6 | -0.0608 | -0.0885 | 0.376 |
| D7 | -0.0519 | -0.0834 | 0.386 |
| D8 | -0.0524 | -0.0907 | 0.391 |
| D9 | -0.0321 | -0.0766 | 0.397 |
| D10 | 0.0133 | -0.0588 | 0.409 |

Calendar-year D10−D1: 2015: 0.1053, 2016: -0.0107, 2017: 0.0271, 2018: -0.0532, 2019: 0.0552, 2020: 0.0119, 2021: 0.0098, 2022: -0.0297, 2023: 0.1824, 2024: 0.3277, 2025: 0.4425, 2026: 0.4585

**H252** — dates with deciles 556, outcome observations 65453

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.1661 | -0.2321 | 0.303 |
| D2 | -0.1439 | -0.2041 | 0.335 |
| D3 | -0.1005 | -0.1756 | 0.368 |
| D4 | -0.1019 | -0.1683 | 0.371 |
| D5 | -0.1003 | -0.1695 | 0.377 |
| D6 | -0.0966 | -0.1810 | 0.355 |
| D7 | -0.1027 | -0.1696 | 0.355 |
| D8 | -0.1205 | -0.1853 | 0.346 |
| D9 | -0.0898 | -0.1863 | 0.349 |
| D10 | -0.0537 | -0.1513 | 0.362 |

Calendar-year D10−D1: 2015: -0.0270, 2016: -0.0202, 2017: 0.0489, 2018: -0.0719, 2019: 0.0520, 2020: -0.1350, 2021: 0.0053, 2022: 0.0615, 2023: 0.3426, 2024: 0.7245, 2025: 0.3345

### momentum121

Stock adjusted-index return from 252 sessions ago to 21 sessions ago (twelve-minus-one-month price momentum, skipping the most recent month). Higher = stronger prior trend. 12-1개월 모멘텀.

Caveat: Overlaps in time with relative126; the two are related but not identical.

**H126** — dates with deciles 583, outcome observations 67962

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0824 | -0.1088 | 0.371 |
| D2 | -0.0666 | -0.0965 | 0.381 |
| D3 | -0.0667 | -0.0951 | 0.374 |
| D4 | -0.0580 | -0.0859 | 0.392 |
| D5 | -0.0647 | -0.0939 | 0.381 |
| D6 | -0.0508 | -0.0772 | 0.399 |
| D7 | -0.0458 | -0.0722 | 0.404 |
| D8 | -0.0371 | -0.0789 | 0.388 |
| D9 | -0.0466 | -0.0952 | 0.377 |
| D10 | -0.0126 | -0.0807 | 0.390 |

Calendar-year D10−D1: 2015: 0.1274, 2016: -0.1397, 2017: 0.0149, 2018: -0.0400, 2019: 0.0430, 2020: -0.0821, 2021: 0.0063, 2022: -0.0155, 2023: 0.1676, 2024: 0.3839, 2025: 0.2702, 2026: 0.2346

**H252** — dates with deciles 556, outcome observations 64592

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.1537 | -0.2215 | 0.325 |
| D2 | -0.0867 | -0.1693 | 0.372 |
| D3 | -0.1070 | -0.1675 | 0.373 |
| D4 | -0.0995 | -0.1661 | 0.383 |
| D5 | -0.1153 | -0.1897 | 0.344 |
| D6 | -0.0909 | -0.1720 | 0.358 |
| D7 | -0.0955 | -0.1441 | 0.377 |
| D8 | -0.1178 | -0.1820 | 0.340 |
| D9 | -0.1030 | -0.1916 | 0.335 |
| D10 | -0.0743 | -0.1914 | 0.338 |

Calendar-year D10−D1: 2015: -0.0415, 2016: -0.2205, 2017: 0.0245, 2018: -0.0429, 2019: 0.0220, 2020: -0.1981, 2021: -0.0713, 2022: 0.0720, 2023: 0.2748, 2024: 0.8318, 2025: 0.3018

### ocfImprovementToAssets

(Latest TTM operating cash flow minus the TTM one year earlier at the same reporting stage) divided by total assets. Positive = operating cash generation improved. 영업현금흐름 개선도.

Caveat: Structurally unobservable before 2018 under the frozen same-stage prior-year rule (fiscal-2015 interim filings lack the statement basis); coverage is reported per year.

**H126** — dates with deciles 420, outcome observations 34061

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0530 | -0.0947 | 0.372 |
| D2 | -0.0886 | -0.1207 | 0.344 |
| D3 | -0.0637 | -0.1021 | 0.393 |
| D4 | -0.1030 | -0.1419 | 0.330 |
| D5 | -0.0605 | -0.1185 | 0.350 |
| D6 | -0.1026 | -0.1433 | 0.341 |
| D7 | -0.0597 | -0.0950 | 0.398 |
| D8 | -0.0364 | -0.0709 | 0.429 |
| D9 | -0.0587 | -0.1088 | 0.382 |
| D10 | -0.0333 | -0.1176 | 0.385 |

Calendar-year D10−D1: 2017: -0.1454, 2018: 0.1019, 2019: 0.0502, 2020: 0.0362, 2021: 0.0186, 2022: -0.0024, 2023: -0.0012, 2024: -0.0946, 2025: 0.0778, 2026: 0.0757

**H252** — dates with deciles 393, outcome observations 31319

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.1094 | -0.1929 | 0.333 |
| D2 | -0.1342 | -0.2329 | 0.338 |
| D3 | -0.1406 | -0.2443 | 0.354 |
| D4 | -0.1899 | -0.2556 | 0.281 |
| D5 | -0.1493 | -0.2583 | 0.302 |
| D6 | -0.1816 | -0.2677 | 0.321 |
| D7 | -0.1737 | -0.2425 | 0.337 |
| D8 | -0.0646 | -0.1821 | 0.392 |
| D9 | -0.0845 | -0.2017 | 0.384 |
| D10 | -0.0519 | -0.2462 | 0.365 |

Calendar-year D10−D1: 2017: 0.0222, 2018: 0.2022, 2019: 0.0726, 2020: 0.1231, 2021: 0.0134, 2022: -0.0162, 2023: -0.1129, 2024: -0.0161, 2025: 0.3185

### negativeDownsideVol126

Minus the annualised downside semideviation (about zero, denominator all 126 sessions) of daily returns over the last 126 sessions. HIGHER = LOWER downside volatility (calmer). 하방변동성(음수): 높을수록 안정적.

Caveat: Direction is inverted relative to the plain volatility number: a high value here means a quiet stock.

**H126** — dates with deciles 583, outcome observations 68867

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0643 | -0.1227 | 0.348 |
| D2 | -0.0465 | -0.1043 | 0.366 |
| D3 | -0.0376 | -0.0915 | 0.375 |
| D4 | -0.0623 | -0.1077 | 0.375 |
| D5 | -0.0563 | -0.0943 | 0.378 |
| D6 | -0.0548 | -0.0863 | 0.390 |
| D7 | -0.0580 | -0.0943 | 0.383 |
| D8 | -0.0487 | -0.0823 | 0.392 |
| D9 | -0.0515 | -0.0783 | 0.408 |
| D10 | -0.0615 | -0.0722 | 0.422 |

Calendar-year D10−D1: 2015: 0.0223, 2016: 0.0774, 2017: 0.0021, 2018: 0.0404, 2019: -0.0768, 2020: -0.0513, 2021: 0.1631, 2022: 0.0040, 2023: 0.0033, 2024: 0.1264, 2025: -0.2557, 2026: -0.1250

**H252** — dates with deciles 556, outcome observations 65453

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.1328 | -0.2319 | 0.301 |
| D2 | -0.0956 | -0.2149 | 0.324 |
| D3 | -0.0661 | -0.2127 | 0.322 |
| D4 | -0.1139 | -0.2216 | 0.338 |
| D5 | -0.1165 | -0.1965 | 0.346 |
| D6 | -0.0826 | -0.1643 | 0.362 |
| D7 | -0.1223 | -0.1715 | 0.350 |
| D8 | -0.1159 | -0.1652 | 0.369 |
| D9 | -0.1031 | -0.1427 | 0.389 |
| D10 | -0.1248 | -0.1386 | 0.421 |

Calendar-year D10−D1: 2015: 0.1482, 2016: 0.1542, 2017: 0.0028, 2018: 0.0796, 2019: -0.2424, 2020: -0.0919, 2021: 0.2983, 2022: 0.1029, 2023: 0.1488, 2024: -0.1482, 2025: -0.5461

### logAdv60

Natural log of one plus the 60-session average KRX trading value (KRW). Higher = more liquid, which in a top-120 market-cap universe is also strongly associated with being larger. 60일 평균 거래대금(로그).

Caveat: Liquidity versus large-cap / institutional / index-membership proxy cannot be separated by this variable alone; see the size and liquidity section.

**H126** — dates with deciles 583, outcome observations 68621

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.0607 | -0.0875 | 0.406 |
| D2 | -0.0800 | -0.0973 | 0.361 |
| D3 | -0.0874 | -0.1095 | 0.353 |
| D4 | -0.0720 | -0.1034 | 0.363 |
| D5 | -0.0446 | -0.0826 | 0.402 |
| D6 | -0.0387 | -0.0949 | 0.384 |
| D7 | -0.0489 | -0.0849 | 0.382 |
| D8 | -0.0456 | -0.0740 | 0.384 |
| D9 | -0.0307 | -0.0821 | 0.400 |
| D10 | -0.0345 | -0.0880 | 0.404 |

Calendar-year D10−D1: 2015: -0.0660, 2016: 0.0735, 2017: 0.0853, 2018: -0.0990, 2019: 0.1778, 2020: 0.0923, 2021: -0.1497, 2022: -0.0117, 2023: -0.0493, 2024: -0.1389, 2025: 0.3469, 2026: 0.1758

**H252** — dates with deciles 556, outcome observations 65221

| decile | mean rel. | median rel. | beat benchmark |
|---|---|---|---|
| D1 | -0.1275 | -0.1799 | 0.365 |
| D2 | -0.1472 | -0.1861 | 0.358 |
| D3 | -0.1771 | -0.2232 | 0.314 |
| D4 | -0.1494 | -0.2098 | 0.327 |
| D5 | -0.0910 | -0.1717 | 0.355 |
| D6 | -0.0637 | -0.1823 | 0.347 |
| D7 | -0.0957 | -0.1756 | 0.347 |
| D8 | -0.0837 | -0.1540 | 0.356 |
| D9 | -0.0924 | -0.1745 | 0.355 |
| D10 | -0.0562 | -0.1559 | 0.386 |

Calendar-year D10−D1: 2015: -0.0283, 2016: 0.1872, 2017: 0.1011, 2018: -0.1176, 2019: 0.4967, 2020: 0.1009, 2021: -0.2025, 2022: 0.0074, 2023: -0.2567, 2024: -0.0834, 2025: 0.8291

## C. Structural anomaly section

- Regulated / public-enterprise sensitivity: DATA_FOUNDATION_REQUIRED (no dated authoritative list).
- Financial-company sensitivity: DATA_FOUNDATION_REQUIRED (no dated authoritative list).
- Price-return vs total-return: see header above; no dividend adjustment was fabricated.
- KEPCO (015760.KS) stays in every primary table; the leave-KEPCO-out figures are a labelled single-ticker sensitivity, not a classification claim.
- Pre-frozen representative financial cases (bank holdings and insurers) are extracted mechanically in `financialCaseStudies` with their distribution-coverage caveats; they are not a financial-sector classification.

## D. Winner / loser anatomy and E. Samsung / SK Hynix / KEPCO case studies

Mechanical selections with exact v1 decompositions are in the machine-readable results (`winnersLosers`, `caseStudies`). No narrative is attached by the execution code.

