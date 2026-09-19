# Benchmark-relative alpha v1 validation

## Research question

Can a concentrated stock-selection rule earn positive return over the regional
total-return benchmark **after realistic implementation costs**, without using
future information or repeatedly tuning historical parameters?

This is a research-only Challenger. It does not change CHAMPION, production
selection, Kelly, macro policy, `paperTrading`, or `liveValidated`.

## Benchmark meaning

- US stocks: SPY total return translated to KRW with the same USD/KRW path.
- KR stocks: KODEX 200 (`069500.KS`) total return.
- Cash: the same BOK policy-rate proxy.
- Each active path is compared with the benchmark carrying the same regional
  and cash exposure. The difference therefore isolates stock selection rather
  than rewarding a strategy for holding more US, KR, or cash.
- The matched benchmark is frictionless. This is deliberately conservative:
  active selection must overcome all of its own costs before claiming alpha.

## Cost model

`spreadBps` is a full spread, so a round trip costs
`2 × commission + spread + sell tax`. The old expected-cost and single-name
outcome paths incorrectly charged two full spreads even though the realized
portfolio path charged half on each leg. All three now use one definition.

The v1 research base case assumes a KRW 10 million trade:

| Region | Commission | Full spread | Sell levy/tax |
|---|---:|---:|---:|
| US | 5bp per side | 6bp | conservative 0.30bp |
| KR | 1.5bp per side | 8bp | historical statutory schedule, 30bp down to 15–20bp |

US Section 31 fees vary by effective date. The SEC's official advisory index
records those changes; for example FY2025 moved from $27.80 per million to zero
and FY2026 later moved to $20.60 per million. The constant 0.30bp here is a
conservative approximation, not a broker quote. KR taxes are resolved by the
trade date rather than applying today's rate to 2013. Commissions and spreads
remain explicit modeling assumptions because they depend on broker, order type,
liquidity, and notional.

Sources: [SEC fee-rate advisories](https://www.sec.gov/rules-regulations/fee-rate-advisories),
[FY2026 Section 31 advisory](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2),
[Korean Securities Transaction Tax Enforcement Decree](https://www.law.go.kr/법령/증권거래세법시행령).

FX conversion cost is excluded. Replacing a US stock with another US stock does
not require reconverting the whole sleeve; cross-region cash transfer is a
separate implementation question and is not silently assigned to every trade.

## Frozen challenger rule

`benchmark-relative-alpha-v1` uses only outcomes whose `outcomeEndDate` is on
or before the signal date.

1. Within each region and alpha bucket, calculate the expanding mean gross
   benchmark excess from matured 126-session outcomes.
2. Shrink it toward zero using the existing effective-date/prior-strength rule.
3. Subtract one realistic round-trip cost and require expected net benchmark
   excess to be positive.
4. Rank remaining names by expected net excess per downside-risk unit, with the
   existing entry-state multiplier and the same name/sector/region constraints.
5. On a regular replacement date, retaining an incumbent receives only the
   immediate sell-plus-replacement-buy friction that would be avoided.
6. Make regular replacement decisions on the first fixed 21-session evaluation
   anchor of each calendar quarter. Between them, carry the actual drifted
   terminal weights instead of re-targeting monthly.

There is no parameter search and no best-variant selection. The rule is frozen
before prospective evidence and remains a Challenger regardless of this result.

## Historical result

All results use the same 155 replay-v16 blocks over 13.684 years.

| Portfolio | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Annual turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Combined CHAMPION | 12.242% | 1.463pp | 10.779% | 13.972% | -3.194pp | 0.779 | -29.231% | 6.313× |
| Existing calibrated challenger | 12.979% | 1.386pp | 11.593% | 12.639% | -1.046pp | 0.757 | -24.563% | 4.564× |
| Benchmark-relative alpha v1 | 10.654% | 0.423pp | 10.232% | 11.719% | -1.488pp | 0.639 | -23.923% | 1.299× |

The Combined CHAMPION's realistic cost drag is lower than the former 1.904pp,
but its gross stock selection already trails the matched benchmark by 1.730pp.
Fees were overstated, but they were not the main cause of underperformance.

The existing calibrated challenger contains the useful clue: it earns +0.340pp
gross benchmark-relative CAGR, then loses 1.386pp to implementation. The new
quarterly rule cuts cost dramatically, but its blunt holding schedule and
positive-alpha cash gate give up more gross return than they save.

The new rule's mean 21-session net alpha is -0.144%, with paired block bootstrap
95% CI [-0.808%, +0.478%] (155 blocks, 2,000 draws, seed 11). The interval
contains zero, so historical evidence is inconclusive; the negative full-path
point estimate is not evidence of positive alpha.

## Decision and next direction

**BENCHMARK_NOT_BEATEN.** None of the tested selectors has positive net
annualized excess. The low-cost benchmark remains the rational default based on
this evidence, and no production promotion is justified.

The next research direction is narrowly identified but not retrospectively
selected as a winner: preserve the existing calibrated benchmark-relative
signal, review it on the fixed calendar, and replace an incumbent only when the
challenger's expected net alpha advantage clears a pre-frozen switching-cost
and uncertainty hurdle. That is a hysteresis/hold-buffer question, not a reason
to add factors, optimize a large parameter grid, or freeze all trading until
quarter-end. It must be specified before new shadow observations and judged
prospectively.

## Reproduction and invariants

Run `scripts/run_benchmark_alpha_replay.py` against the pinned replay-v16 ledger.
`.github/workflows/benchmark-alpha.yml` checks out sealed commit
`b71d8cb5ce21815980d28b606852f9294d43cc53` read-only, runs tests, validates
the ledger byte hash, and uploads the JSON/Markdown result. The runner refuses
to write inside the ledger. CHAMPION and production configuration remain
unchanged.

