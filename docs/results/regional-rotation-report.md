# Regional Rotation v1 attribution

**CHALLENGER — historical evidence only; no production promotion.**

Input: `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2` through 2026-09-14.
Frozen baseline: 252 **calendar** days; temperature 0.05; floor 0.15; quarterly fixed anchors.
Only outcomes with windowStart ≤ endDate < decisionDate enter each trailing score.

## Baseline comparison

| Portfolio | CAGR % | Excess pp/yr | Sharpe | Sortino | MDD % | Calmar | CVaR daily % | Vol %/yr | Turnover % | Cash % | Sum cost % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Combined CHAMPION | +10.338 | -3.635 | +0.744 | +1.072 | -29.264 | +0.353 | -1.565 | +11.446 | +56.100 | +22.461 | +23.395 |
| Static 50/50 | +8.661 | -2.349 | +0.801 | +1.170 | -19.095 | +0.454 | -1.132 | +8.334 | +42.370 | +38.662 | +19.598 |
| Dynamic Regional Rotation v1 | +8.938 | -1.917 | +0.817 | +1.199 | -19.956 | +0.448 | -1.159 | +8.509 | +42.110 | +38.725 | +19.762 |

CAGR is cost-adjusted. Excess = portfolio CAGR minus its own equity/cash-matched benchmark CAGR. Sharpe and Sortino use daily BOK risk-free excess. CVaR is the mean worst 5% daily net returns. Turnover excludes the initial purchase; sum cost is the sum of entry cost fractions, not annualized drag.

Matching: 155/155 fixed matured blocks. Complete: True. Missing blocks are never filled or renormalized.

## Incremental attribution and paired bootstrap confidence intervals

Raw deltas are challenger minus control. Positive MDD/CVaR deltas mean less-negative losses. Path CI jointly resamples whole net daily blocks (including original costs and RF). Its point estimate is the chronological full-path difference.

### diversificationRegionalReranking: Static 50/50 minus Combined CHAMPION

| Metric | Path Δ | Bootstrap mean | 95% CI | Paired blocks | Seed | Draws |
|---|---:|---:|---|---:|---:|---:|
| cagrPct | -1.677 | -1.746 | [-4.593, +0.955] | 155 | 11 | 2000 |
| annualizedExcessPct | +1.286 | +1.269 | [-1.188, +3.714] | 155 | 11 | 2000 |
| sharpe | +0.057 | +0.040 | [-0.192, +0.251] | 155 | 11 | 2000 |
| sortino | +0.098 | +0.066 | [-0.306, +0.399] | 155 | 11 | 2000 |
| mddPct | +10.168 | +7.902 | [-0.780, +16.259] | 155 | 11 | 2000 |
| calmar | +0.100 | +0.076 | [-0.311, +0.308] | 155 | 11 | 2000 |
| cvar95Pct | +0.433 | +0.429 | [+0.282, +0.656] | 155 | 11 | 2000 |

+10.168pp shallower drawdown

Cash/cost/benchmark deltas (pp, except turnover and summed cost in percentage points): averageCashPct +16.201, averageEquityPct -16.201, benchmarkCagrPct -2.963, averageTurnoverPct -13.730, sumTransactionCostPct -3.798, costDragCagrPp -0.336

- cagrPct: historical evidence is inconclusive
- annualizedExcessPct: historical evidence is inconclusive
- sharpe: historical evidence is inconclusive
- sortino: historical evidence is inconclusive
- mddPct: historical evidence is inconclusive
- calmar: historical evidence is inconclusive
- cvar95Pct: historical interval excludes zero; prospective evidence still required

Literal mean paired **block-metric** differences (separate estimand; not the full-path difference):

| Metric | Mean block Δ | Bootstrap mean | 95% CI | Pairs | Seed | Draws |
|---|---:|---:|---|---:|---:|---:|
| cagrPct | -4.485 | -4.519 | [-7.663, -1.481] | 155 | 11 | 2000 |
| annualizedExcessPct | +0.776 | +0.747 | [-2.378, +3.796] | 155 | 11 | 2000 |
| sharpe | -0.059 | -0.062 | [-0.287, +0.159] | 155 | 11 | 2000 |
| sortino | -0.116 | -0.120 | [-0.526, +0.305] | 155 | 11 | 2000 |
| mddPct | +0.624 | +0.619 | [+0.460, +0.809] | 155 | 11 | 2000 |
| calmar | -0.062 | -0.066 | [-2.169, +1.995] | 155 | 11 | 2000 |
| cvar95Pct | +0.265 | +0.264 | [+0.207, +0.333] | 155 | 11 | 2000 |

### dynamicTiming: Dynamic Regional Rotation v1 minus Static 50/50

| Metric | Path Δ | Bootstrap mean | 95% CI | Paired blocks | Seed | Draws |
|---|---:|---:|---|---:|---:|---:|
| cagrPct | +0.277 | +0.271 | [-0.557, +1.135] | 155 | 11 | 2000 |
| annualizedExcessPct | +0.431 | +0.443 | [-0.540, +1.457] | 155 | 11 | 2000 |
| sharpe | +0.015 | +0.016 | [-0.071, +0.107] | 155 | 11 | 2000 |
| sortino | +0.029 | +0.032 | [-0.104, +0.186] | 155 | 11 | 2000 |
| mddPct | -0.861 | -0.599 | [-2.565, +1.542] | 155 | 11 | 2000 |
| calmar | -0.006 | +0.004 | [-0.130, +0.181] | 155 | 11 | 2000 |
| cvar95Pct | -0.027 | -0.027 | [-0.060, +0.003] | 155 | 11 | 2000 |

-0.861pp deeper drawdown

Cash/cost/benchmark deltas (pp, except turnover and summed cost in percentage points): averageCashPct +0.063, averageEquityPct -0.063, benchmarkCagrPct -0.154, averageTurnoverPct -0.260, sumTransactionCostPct +0.164, costDragCagrPp +0.017

- cagrPct: historical evidence is inconclusive
- annualizedExcessPct: historical evidence is inconclusive
- sharpe: historical evidence is inconclusive
- sortino: historical evidence is inconclusive
- mddPct: historical evidence is inconclusive
- calmar: historical evidence is inconclusive
- cvar95Pct: historical evidence is inconclusive

Literal mean paired **block-metric** differences (separate estimand; not the full-path difference):

| Metric | Mean block Δ | Bootstrap mean | 95% CI | Pairs | Seed | Draws |
|---|---:|---:|---|---:|---:|---:|
| cagrPct | +0.486 | +0.473 | [-0.374, +1.362] | 155 | 11 | 2000 |
| annualizedExcessPct | +1.299 | +1.345 | [-0.469, +4.001] | 155 | 11 | 2000 |
| sharpe | +0.022 | +0.021 | [-0.071, +0.108] | 155 | 11 | 2000 |
| sortino | +0.089 | +0.088 | [-0.073, +0.258] | 155 | 11 | 2000 |
| mddPct | -0.027 | -0.027 | [-0.067, +0.014] | 155 | 11 | 2000 |
| calmar | +0.136 | +0.138 | [-0.511, +0.793] | 155 | 11 | 2000 |
| cvar95Pct | -0.009 | -0.009 | [-0.024, +0.006] | 155 | 11 | 2000 |

### totalArchitecture: Dynamic Regional Rotation v1 minus Combined CHAMPION

| Metric | Path Δ | Bootstrap mean | 95% CI | Paired blocks | Seed | Draws |
|---|---:|---:|---|---:|---:|---:|
| cagrPct | -1.399 | -1.475 | [-4.358, +1.310] | 155 | 11 | 2000 |
| annualizedExcessPct | +1.717 | +1.712 | [-0.783, +4.194] | 155 | 11 | 2000 |
| sharpe | +0.072 | +0.056 | [-0.183, +0.283] | 155 | 11 | 2000 |
| sortino | +0.127 | +0.099 | [-0.284, +0.469] | 155 | 11 | 2000 |
| mddPct | +9.308 | +7.303 | [-1.231, +15.277] | 155 | 11 | 2000 |
| calmar | +0.095 | +0.080 | [-0.318, +0.394] | 155 | 11 | 2000 |
| cvar95Pct | +0.406 | +0.402 | [+0.256, +0.610] | 155 | 11 | 2000 |

+9.308pp shallower drawdown

Cash/cost/benchmark deltas (pp, except turnover and summed cost in percentage points): averageCashPct +16.265, averageEquityPct -16.265, benchmarkCagrPct -3.116, averageTurnoverPct -13.990, sumTransactionCostPct -3.633, costDragCagrPp -0.318

- cagrPct: historical evidence is inconclusive
- annualizedExcessPct: historical evidence is inconclusive
- sharpe: historical evidence is inconclusive
- sortino: historical evidence is inconclusive
- mddPct: historical evidence is inconclusive
- calmar: historical evidence is inconclusive
- cvar95Pct: historical interval excludes zero; prospective evidence still required

Literal mean paired **block-metric** differences (separate estimand; not the full-path difference):

| Metric | Mean block Δ | Bootstrap mean | 95% CI | Pairs | Seed | Draws |
|---|---:|---:|---|---:|---:|---:|
| cagrPct | -3.999 | -4.046 | [-7.192, -0.847] | 155 | 11 | 2000 |
| annualizedExcessPct | +2.075 | +2.092 | [-1.486, +5.694] | 155 | 11 | 2000 |
| sharpe | -0.038 | -0.041 | [-0.286, +0.198] | 155 | 11 | 2000 |
| sortino | -0.027 | -0.032 | [-0.485, +0.443] | 155 | 11 | 2000 |
| mddPct | +0.597 | +0.592 | [+0.430, +0.778] | 155 | 11 | 2000 |
| calmar | +0.074 | +0.072 | [-2.131, +2.371] | 155 | 11 | 2000 |
| cvar95Pct | +0.256 | +0.255 | [+0.194, +0.325] | 155 | 11 | 2000 |

## Robustness

Pre-specified OFAT; no winner or default selection.

| Variant | Lookback calendar days | Temperature | Floor | ΔCAGR vs static pp | ΔMDD vs static pp | ΔSharpe | US weight min–max | Max quarterly change |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| baseline | 252 | 0.05 | 0.15 | +0.277 | -0.861 | +0.015 | 0.317–0.803 | 0.183 |
| lookback-126 | 126 | 0.05 | 0.15 | -0.025 | -0.475 | -0.012 | 0.150–0.825 | 0.376 |
| lookback-504 | 504 | 0.05 | 0.15 | +0.170 | -0.121 | +0.014 | 0.317–0.655 | 0.183 |
| floor-0.10 | 252 | 0.05 | 0.1 | +0.277 | -0.861 | +0.015 | 0.317–0.803 | 0.183 |
| floor-0.25 | 252 | 0.05 | 0.25 | +0.294 | -0.861 | +0.017 | 0.317–0.750 | 0.183 |
| temperature-0.03 | 252 | 0.03 | 0.15 | +0.461 | -1.433 | +0.016 | 0.217–0.850 | 0.288 |
| temperature-0.10 | 252 | 0.1 | 0.15 | +0.142 | -0.426 | +0.011 | 0.405–0.669 | 0.095 |

cagrPct: positive 6/7, negative 1/7; range [-0.025, +0.461].

mddPct: positive 0/7, negative 7/7; range [-1.433, -0.121].

sharpe: positive 6/7, negative 1/7; range [-0.012, +0.017].

## Interpretation

Dynamic minus static isolates allocation-rule changes on identical sleeves, including induced cash, benchmark and trading-cost changes. Static minus combined bundles independent reranking, regional diversification, concentration and cash/risk-budget effects; these components are not separately identified by three portfolios.

## Sharpe repair

The old blend discarded dailyDates/dailyGrossNav/dailyBenchmarkNav/dailyRiskFreeNav and terminal holdings, falling back to legacy endpoint metrics with Sharpe/Sortino=None. Daily NAV and drifted terminal holdings now survive blending; all portfolios use PV._path_metrics.

## Limitations

- Historical post-design replay, not prospective evidence.
- No parameter optimization or automatic promotion.
- Individual portfolio benchmarks vary with regional equity and cash weights.
- IID block bootstrap may understate persistent-regime uncertainty.
- OFAT results include previously observed history and are stability diagnostics only.

## Regional allocation history

| Decision date | US trailing score % | KR trailing score % | Raw US | Raw KR | Final US | Final KR |
|---|---:|---:|---:|---:|---:|---:|
| 2013-01-07 | N/A | N/A | +0.500 | +0.500 | +0.500 | +0.500 |
| 2013-04-11 | -1.773 | +2.075 | +0.317 | +0.683 | +0.317 | +0.683 |
| 2013-07-16 | -0.531 | +1.626 | +0.394 | +0.606 | +0.394 | +0.606 |
| 2013-10-22 | +0.189 | +0.505 | +0.484 | +0.516 | +0.484 | +0.516 |
| 2014-01-24 | -0.643 | +0.560 | +0.440 | +0.560 | +0.440 | +0.560 |
| 2014-04-29 | -0.904 | -0.270 | +0.468 | +0.532 | +0.468 | +0.532 |
| 2014-07-07 | -1.113 | +0.467 | +0.422 | +0.578 | +0.422 | +0.578 |
| 2014-10-13 | -0.543 | +1.918 | +0.379 | +0.621 | +0.379 | +0.621 |
| 2015-01-14 | -0.412 | +2.118 | +0.376 | +0.624 | +0.376 | +0.624 |
| 2015-04-21 | +0.064 | +1.605 | +0.424 | +0.576 | +0.424 | +0.576 |
| 2015-07-23 | -0.010 | +1.104 | +0.445 | +0.555 | +0.445 | +0.555 |
| 2015-10-27 | -0.205 | +0.595 | +0.460 | +0.540 | +0.460 | +0.540 |
| 2016-01-29 | +0.526 | +0.729 | +0.490 | +0.510 | +0.490 | +0.510 |
| 2016-04-06 | +0.789 | +0.132 | +0.533 | +0.467 | +0.533 | +0.467 |
| 2016-07-12 | +0.168 | +0.183 | +0.499 | +0.501 | +0.499 | +0.501 |
| 2016-10-17 | +0.772 | -0.261 | +0.551 | +0.449 | +0.551 | +0.449 |
| 2017-01-19 | -0.362 | -0.234 | +0.494 | +0.506 | +0.494 | +0.506 |
| 2017-04-25 | -1.756 | -0.428 | +0.434 | +0.566 | +0.434 | +0.566 |
| 2017-08-01 | -0.534 | -0.268 | +0.487 | +0.513 | +0.487 | +0.513 |
| 2017-10-10 | -0.244 | -0.724 | +0.524 | +0.476 | +0.524 | +0.476 |
| 2018-01-11 | -0.467 | -1.157 | +0.534 | +0.466 | +0.534 | +0.466 |
| 2018-04-18 | +0.324 | +0.085 | +0.512 | +0.488 | +0.512 | +0.488 |
| 2018-07-25 | +0.264 | +2.394 | +0.395 | +0.605 | +0.395 | +0.605 |
| 2018-10-31 | +0.528 | +1.102 | +0.471 | +0.529 | +0.471 | +0.529 |
| 2019-01-04 | +0.906 | +1.063 | +0.492 | +0.508 | +0.492 | +0.508 |
| 2019-04-11 | +0.058 | +0.404 | +0.483 | +0.517 | +0.483 | +0.517 |
| 2019-07-17 | -0.303 | +0.159 | +0.477 | +0.523 | +0.477 | +0.523 |
| 2019-10-22 | +0.307 | -0.248 | +0.528 | +0.472 | +0.528 | +0.472 |
| 2020-01-28 | +0.171 | -1.359 | +0.576 | +0.424 | +0.576 | +0.424 |
| 2020-04-29 | -1.209 | -0.917 | +0.485 | +0.515 | +0.485 | +0.515 |
| 2020-07-02 | -1.657 | -0.940 | +0.464 | +0.536 | +0.464 | +0.536 |
| 2020-10-07 | -2.111 | -0.337 | +0.412 | +0.588 | +0.412 | +0.588 |
| 2021-01-11 | -1.128 | -1.103 | +0.499 | +0.501 | +0.499 | +0.501 |
| 2021-04-16 | -1.552 | -0.743 | +0.460 | +0.540 | +0.460 | +0.540 |
| 2021-07-20 | -1.550 | -0.867 | +0.466 | +0.534 | +0.466 | +0.534 |
| 2021-10-26 | -0.150 | +1.066 | +0.439 | +0.561 | +0.439 | +0.561 |
| 2022-01-27 | +0.366 | +1.349 | +0.451 | +0.549 | +0.451 | +0.549 |
| 2022-04-05 | +1.574 | +1.194 | +0.519 | +0.481 | +0.519 | +0.481 |
| 2022-07-12 | +0.631 | +1.016 | +0.481 | +0.519 | +0.481 | +0.519 |
| 2022-10-17 | +1.772 | +0.905 | +0.543 | +0.457 | +0.543 | +0.457 |
| 2023-01-19 | +1.932 | +0.948 | +0.549 | +0.451 | +0.549 | +0.451 |
| 2023-04-25 | +0.680 | +0.043 | +0.532 | +0.468 | +0.532 | +0.468 |
| 2023-07-31 | -0.062 | -1.509 | +0.572 | +0.428 | +0.572 | +0.428 |
| 2023-10-05 | -0.639 | -1.526 | +0.544 | +0.456 | +0.544 | +0.456 |
| 2024-01-09 | -1.250 | -0.273 | +0.451 | +0.549 | +0.451 | +0.549 |
| 2024-04-16 | -0.999 | +2.261 | +0.343 | +0.657 | +0.343 | +0.657 |
| 2024-07-23 | -2.242 | +0.004 | +0.390 | +0.610 | +0.390 | +0.610 |
| 2024-10-30 | -0.831 | -0.522 | +0.485 | +0.515 | +0.485 | +0.515 |
| 2025-01-02 | -0.462 | +1.763 | +0.391 | +0.609 | +0.391 | +0.609 |
| 2025-04-11 | +0.856 | +3.790 | +0.357 | +0.643 | +0.357 | +0.643 |
| 2025-07-22 | +0.325 | +2.176 | +0.409 | +0.591 | +0.409 | +0.591 |
| 2025-10-28 | -0.751 | +0.294 | +0.448 | +0.552 | +0.448 | +0.552 |
| 2026-01-30 | -0.686 | -3.248 | +0.625 | +0.375 | +0.625 | +0.375 |
| 2026-04-07 | +0.145 | -5.376 | +0.751 | +0.249 | +0.751 | +0.249 |
| 2026-07-13 | +0.489 | -6.550 | +0.803 | +0.197 | +0.803 | +0.197 |

## Invariants

Sealed ledger SHA-256 tree before/after: `365dddb1387f1644693c8d458dd824ed8c039d850a4227de5756570664b9a7cc` / `365dddb1387f1644693c8d458dd824ed8c039d850a4227de5756570664b9a7cc`.
Sealed CHAMPION rows are read-only; production selector, Kelly, macro, runMode and liveValidated are unchanged.
