# Benchmark-relative alpha v1

> Research-only CHALLENGER. Production selector and sealed replay are unchanged.

## Headline

| Portfolio | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Avg turnover | Annual turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Combined CHAMPION — realistic costs | 12.242% | 1.463pp | 10.779% | 13.972% | -3.194pp | 0.779 | -29.231% | 56.100% | 6.313x |
| Existing calibrated challenger — realistic costs | 12.979% | 1.386pp | 11.593% | 12.639% | -1.046pp | 0.757 | -24.563% | 43.370% | 4.564x |
| Benchmark-relative alpha v1 | 10.654% | 0.423pp | 10.232% | 11.719% | -1.488pp | 0.639 | -23.923% | 13.370% | 1.299x |

## Why costs were high

The Combined CHAMPION was evaluated every 21 sessions and made 154 rebalances. Average one-way turnover was 56.100%, approximately 6.313x NAV per year.

Correcting the cost model changes estimated CAGR drag from 1.904pp to 1.463pp; it does not rescue a selector whose gross stock picks trail the matched index.

Before costs, Combined CHAMPION trails its matched index by -1.730pp per year. That is a stock-selection problem, not a fee-estimation problem.

## New rule

- Rank on matured, shrunk regional-benchmark excess return after a realistic round-trip cost.
- Require expected net benchmark alpha to be positive.
- Make regular replacement decisions quarterly; carry drifted holdings between decisions.
- Keep an incumbent unless the replacement overcomes the immediate sell-plus-buy friction.
- No production promotion; prospective shadow evidence is still absent.

## Uncertainty

Mean matched-block net alpha is -0.144% with 95% CI [-0.808%, 0.478%], based on 155 paired blocks. A CI containing zero is inconclusive.

## Pairwise path differences

- New minus Combined CHAMPION: Δ annualized excess 1.706pp, 95% CI [-4.775pp, 8.324pp].
- New minus Existing calibrated challenger: Δ annualized excess -0.441pp, 95% CI [-5.872pp, 5.071pp].

## Cost-model scope

The matched benchmark is deliberately frictionless, while the active book pays costs. This is conservative for the alpha claim. ETF expense drag is already embedded in total-return prices. Broker-specific FX conversion is excluded because ordinary same-currency name replacement does not require converting the whole sleeve; cross-region FX implementation should be evaluated separately.

US Section 31 fees vary over time; the base case uses a conservative 0.30bp sell levy. KR statutory sell tax is applied by historical effective-date schedule. Commissions/spreads are explicit research assumptions, not a claim about every broker.

## Decision

**BENCHMARK_NOT_BEATEN** — Realistic costs improve every active path, but no tested selector has positive net annualized excess. The quarterly integrated rule reduces implementation drag but gives up too much gross selection return.

The evidence points to retaining the existing calibrated benchmark-relative signal and adding a pre-frozen incumbent replacement hurdle/hysteresis, rather than a blunt quarterly freeze or another factor search. This is a prospective challenger proposal, not a winner selected from this history.

This is a historical design diagnostic, not evidence to promote a selector. The next rule must be frozen before prospective shadow observations arrive.
