# kr-alpha-atlas — KR information map

Rendered from `research_specs/kr-alpha-atlas-registry-v1.json` by `scripts/render_kr_alpha_atlas_map.py`. Do not edit by hand.

> readinessStatus describes data and PIT readiness only; existingResearchStatus describes prior DEVELOPMENT evidence on outcome-exposed KR history only. Neither is an investment verdict, and no prior positive development reading is confirmation.

Benchmark `069500.KS`; development cutoff 2026-09-14; reference universe `PIT_KRX_TOP120`.

## Summary

| Readiness | Features |
|---|---:|
| ALREADY_TESTED | 24 |
| DATA_BUILD_REQUIRED | 13 |
| DERIVABLE_FROM_EXISTING_DATA | 27 |
| NOT_FEASIBLE | 4 |
| PIT_UNSAFE | 6 |
| READY | 25 |
| SOURCE_BLOCKED | 7 |

| Prior evidence (development only) | Features |
|---|---:|
| BLOCKED | 10 |
| NOT_APPLICABLE | 11 |
| PRIOR_INCONCLUSIVE | 38 |
| PRIOR_NEGATIVE_DEVELOPMENT | 5 |
| PRIOR_POSITIVE_DEVELOPMENT | 4 |
| UNTESTED | 38 |

| Role | Features |
|---|---:|
| ALPHA_CANDIDATE | 70 |
| CONTEXT_CONDITIONING | 18 |
| CONTROL | 9 |
| COST_CAPACITY | 3 |
| ELIGIBILITY_FILTER | 2 |
| RISK_CONSTRUCTION | 4 |

## Universes

| Universe | Readiness | Evidence | Blocking reason |
|---|---|---|---|
| PIT_KRX_TOP120 | READY | krx_universe members_on_date; 260 securities ever held the rank 2013-2026; price panels and DART fundamentals exist for them |  |
| KOSPI_LIQUIDITY_QUALIFIED_BROAD | DATA_BUILD_REQUIRED | KRX sto/stk_bydd_trd is point-in-time for all KOSPI issues (930 issues on 2013-01-02) with MKTCAP and LIST_SHRS | price panels and DART fundamentals exist only for the 260 ever-top-120 securities; delisting and terminal economics outside them unaudited |
| KOSDAQ | SOURCE_BLOCKED | sto/ksq_bydd_trd answers Unauthorized API Call under the current key (vendor refusal invariants) | KOSDAQ daily statistics not authorized for the subscribed key |

## A. Price, momentum and reversal

Primary horizon H126; secondary H21 (short-term reversal is a different mechanism with a monthly half-life).

| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |
|---|---|---|---|---|---|---:|---|---|
| `A01_return1d` | One-day overreaction to liquidity or news reverses as liquidity providers are paid | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 21 | bid-ask bounce cannot be separated without quote data (E09) | compute in the Phase B matrix; Level 1 at H21 only |
| `A02_return5d` | Weekly reversal of liquidity-driven price pressure | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 21 |  | compute in the Phase B matrix |
| `A03_return21d` | One-month return: reversal at short horizon, start of momentum at longer ones | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1, kr-alpha-discovery-tournament-v1) | ALPHA_CANDIDATE | 21 |  | Level 1 at H21 (reversal reading) |
| `A04_return63d` | Quarter return; intermediate momentum | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1, kr-alpha-discovery-tournament-v1) | ALPHA_CANDIDATE | 126 |  | Level 1 at H126 |
| `A05_relative126` | Six-month return over 069500.KS: under-reaction to slowly diffusing news | PIT_SIGNAL_CLOSE | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, regional-alpha-model-v1, alpha-opportunity-model-v5, kr-model-overlay-portfolio-v1) | CONTROL | 126 | factor anatomy: CONCENTRATED_IN_SPECIFIC_STRATA (H126 D10-D1 +10.3pp, 73% of years positive); within industry WEAKENS_MATERIALLY | reuse the sealed anatomy readings; enters Level 2 as baseline B2, never re-measured at Level 1 |
| `A06_return252d` | Twelve-month return including the last month | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1) | ALPHA_CANDIDATE | 126 |  | Level 1 at H126 |
| `A07_momentum12_1` | Jegadeesh-Titman 12-1 momentum: skip the reversal month | PIT_SIGNAL_CLOSE | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, regional-alpha-model-v1, four-factor-signal-attribution-audit-v1) | CONTROL | 126 | factor anatomy UNSTABLE_OR_REGIME_DEPENDENT; within industry ABSORBED_TO_NEAR_ZERO | reuse sealed readings; Level 2 baseline only |
| `A08_momentum6` | Medium-term (6-month) momentum | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1) | ALPHA_CANDIDATE | 126 |  | Level 1 at H126; expected redundant with A05/A07 (redundancy map decides) |
| `A09_industryRelativeMomentum126` | Stock return minus its leave-one-out industry: stock-level leadership inside an industry | PIT_RECONSTRUCTED_MEMBERSHIP | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-stock-within-industry-anatomy-v1, kr-alpha-discovery-tournament-v1) | ALPHA_CANDIDATE | 126 | within-industry relative126 +0.028 (mean/se +1.1), 55% of years positive | reuse within-industry anatomy reading; Level 3 X3 component |
| `A10_residualMomentum126` | Momentum in the part of the return not explained by market and industry: firm-specific news diffusion | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 126 |  | compute in Phase B |
| `A11_distance52wHigh` | Anchoring to the 52-week high delays reaction to good news | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1, kr-alpha-discovery-tournament-v1) | ALPHA_CANDIDATE | 126 |  | Level 1 at H126 |
| `A12_momentumPersistence` | Share of the last 12 months with positive relative return: smooth versus lumpy momentum | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 126 |  | compute in Phase B |
| `A13_momentumAcceleration21` | Change in short-horizon momentum: new information arriving | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (alpha-opportunity-model-v5, opportunity-radar-model) | ALPHA_CANDIDATE | 21 |  | Level 1 at H21 |
| `A14_ma200Distance` | Price versus its 200-session trend | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1, kr-alpha-discovery-tournament-v1) | ALPHA_CANDIDATE | 126 |  | redundancy map only unless it separates from A06/A11 |

## B. Value

Primary horizon H126; secondary H252 (valuation resolves over one to two reporting cycles).

| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |
|---|---|---|---|---|---|---:|---|---|
| `B01_bookToMarket` | Cheap assets: compensation for distress risk or mispricing of out-of-favour firms | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_POSITIVE_DEVELOPMENT (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, kr-model-overlay-portfolio-v1) | CONTROL | 126 | factor anatomy H126 BROADLY_POSITIVE_HISTORICAL_ASSOCIATION (D10-D1 +6.5pp, 80% of years); within-industry +0.086 (mean/se +2.9); 75% raw coverage of eligible name-dates. ISSUE_CAP_ACCOUNTING_PROXY: whole-entity accounts over one issue's cap; distorted for preferreds and holding companies; return basis understates high-dividend names | reuse sealed readings; Level 2 baseline B1 |
| `B02_earningsYield` | Cheap earnings | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, kr-model-overlay-portfolio-v1) | CONTROL | 126 | market-wide UNSTABLE_OR_REGIME_DEPENDENT; within industry +0.073 (+2.6); 61% raw coverage. ISSUE_CAP_ACCOUNTING_PROXY: whole-entity accounts over one issue's cap; distorted for preferreds and holding companies; return basis understates high-dividend names | reuse sealed readings |
| `B03_ocfYield` | Cheap operating cash flow | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_NEGATIVE_DEVELOPMENT (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, kr-model-overlay-portfolio-v1) | ALPHA_CANDIDATE | 126 | factor anatomy H126 D10-D1 -4.1pp, 11% of years positive; ISSUE_CAP_ACCOUNTING_PROXY: whole-entity accounts over one issue's cap; distorted for preferreds and holding companies; return basis understates high-dividend names | no new Level 1; redundancy map only |
| `B04_freeCashFlowYield` | Cheap free cash flow after maintenance capex | PIT_RECEIPT_DATED | DATA_BUILD_REQUIRED | UNTESTED | ALPHA_CANDIDATE | 126 | KR capex (유형자산의취득) present on 7.74% of KR filings and fcfToNetIncome on 4.31% (alpha-research-foundation-v2); kr-canonical-v2 raw-statement repair not landed | re-measure coverage after kr-canonical-v2 lands; exclude if still below the 60% floor |
| `B05_industryRelativeValue` | Cheap against industry peers: removes industry-wide valuation differences that are not mispricing | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_POSITIVE_DEVELOPMENT (kr-stock-within-industry-anatomy-v1, kr-integrated-alpha-portfolio-v1) | ALPHA_CANDIDATE | 126 | B/M and EY both SURVIVE the move to industry-relative targets; the outcome-exposed anatomy was read before H2 was designed | reuse sealed reading; Level 3 X1 component |
| `B06_ownHistoryValuation` | Cheap against its own past: mean reversion of a firm's own multiple | PIT_RECEIPT_DATED | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 126 |  | compute in Phase B; report its first measurable year |
| `B07_valuationChange126` | Change in book-to-market over 126 sessions: mostly price driven, so a value-momentum mix | PIT_RECEIPT_DATED | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 126 |  | redundancy map before any Level 1 reading |
| `B08_valueBusinessConfirmation` | H2: cheap within industry AND profitable, cash-backed, not deteriorating; separates mispricing from value traps | PIT_RECEIPT_DATED | DERIVABLE_FROM_EXISTING_DATA | PRIOR_INCONCLUSIVE (kr-model-overlay-portfolio-v1) | ALPHA_CANDIDATE | 126 |  | CANDIDATE_SIGNAL_FAMILY; Level 3 interaction X1 (docs/kr-alpha-signal-v2-design.md) |

## C. Profitability and accounting quality

Primary horizon H126; secondary H252 (accounting information resolves over one to two reporting cycles).

| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |
|---|---|---|---|---|---|---:|---|---|
| `C01_returnOnAssets` | Profitable firms earn more: risk or under-pricing of persistent profitability | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, kr-model-overlay-portfolio-v1) | CONTROL | 126 | factor anatomy NO_CLEAR_MONOTONIC_PATTERN; within industry +0.036 (+1.0); 61% raw coverage | reuse sealed readings |
| `C02_returnOnEquity` | Return on book equity | PIT_RECEIPT_DATED | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1, four-factor-signal-attribution-audit-v1) | ALPHA_CANDIDATE | 126 | undefined on negative equity (None, never a number) | Level 1 at H126 |
| `C03_operatingMargin` | Operating margin: pricing power | PIT_RECEIPT_DATED | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1) | ALPHA_CANDIDATE | 126 |  | Level 1 at H126 |
| `C04_profitMargin` | Net margin | PIT_RECEIPT_DATED | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1) | ALPHA_CANDIDATE | 126 |  | redundancy map first |
| `C05_ocfToAssets` | Cash profitability: earnings backed by cash | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, kr-model-overlay-portfolio-v1) | CONTROL | 126 | 60% raw coverage | reuse sealed readings |
| `C06_cashConversion` | Operating cash flow over net income: earnings quality | PIT_RECEIPT_DATED | DATA_BUILD_REQUIRED | UNTESTED | ALPHA_CANDIDATE | 126 | KR net income absent from 72% of 2024-2025 quarterly filings in the sealed store (v2.33); v5 removed ocfToNetIncomePct for an unapproved state contract | re-measure after kr-canonical-v2 lands |
| `C07_negativeAccruals` | Sloan accruals: earnings not backed by cash reverse | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_NEGATIVE_DEVELOPMENT (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, kr-model-overlay-portfolio-v1) | ALPHA_CANDIDATE | 126 | factor anatomy D10-D1 -1.0pp, 33% of years positive; within industry ABSORBED_TO_NEAR_ZERO | no new Level 1 |
| `C08_netIncomeMinusOcf` | Net income minus operating cash flow (scaled): the same accrual information as C07 | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_NEGATIVE_DEVELOPMENT (kr-factor-anatomy-v1) | ALPHA_CANDIDATE | 126 |  | none: covered by C07 |
| `C09_assetGrowth` | Investment factor: aggressive asset growth predicts lower returns | PIT_RECEIPT_DATED | READY | PRIOR_INCONCLUSIVE (alpha-opportunity-model-v5) | ALPHA_CANDIDATE | 126 | 96-97% coverage where filings exist; joint use only in v5 (INCONCLUSIVE) | Level 1 at H126 |
| `C10_liabilityGrowth` | Growth of total liabilities (부채총계, not interest-bearing debt) | PIT_RECEIPT_DATED | READY | PRIOR_INCONCLUSIVE (alpha-opportunity-model-v5) | ALPHA_CANDIDATE | 126 |  | Level 1 at H126 |
| `C11_shareDilution` | Change in shares outstanding net of treasury stock: issuers time equity sales | PIT_RECEIPT_DATED | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 126 | quarterly share counts carried forward from earlier filings where not restated (AS_FILED vs CARRIED_FORWARD published) | compute in Phase B |
| `C12_profitabilityPersistence` | Stability of profitability across consecutive filings | PIT_RECEIPT_DATED | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 126 |  | compute in Phase B |
| `C13_fundamentalAcceleration` | Filing-over-filing change in ROE, margins and growth | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_NEGATIVE_DEVELOPMENT (fundamental-acceleration-discovery-v1, regional-alpha-model-v1) | ALPHA_CANDIDATE | 126 |  | none; prospective sealing stays separate |
| `C14_ocfImprovement` | Trailing OCF above its level a year earlier: improving business | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, kr-model-overlay-portfolio-v1) | ALPHA_CANDIDATE | 126 | factor anatomy UNSTABLE_OR_REGIME_DEPENDENT; within industry +0.044 (+1.8) SURVIVES; 51% raw coverage | reuse sealed readings |
| `C15_capexIntensity` | Capex over assets: investment intensity | PIT_RECEIPT_DATED | DATA_BUILD_REQUIRED | UNTESTED | ALPHA_CANDIDATE | 126 | KR capex coverage 7.74% (alpha-research-foundation-v2) | re-measure after kr-canonical-v2 |
| `C16_grossProfitability` | Novy-Marx gross profits over assets | PIT_RECEIPT_DATED | DATA_BUILD_REQUIRED | UNTESTED | ALPHA_CANDIDATE | 126 | no gross-profit or cost-of-sales line in dart_fundamentals.WANTED_ACCOUNTS; raw-statement store (dart_raw_statements) keeps all rows but kr-canonical-v2 has not landed | add a canonical account rule in the data-foundation line, then measure coverage |

## D. Volume and trading activity

Primary horizon H21; secondary H63 (turnover level and liquidity trends are slower than shocks).

| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |
|---|---|---|---|---|---|---:|---|---|
| `D01_volumeSurge5_60` | Relative volume: attention and information arrival | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1, opportunity-radar-model) | ALPHA_CANDIDATE | 21 |  | Level 1 at H21, magnitude and rank side by side |
| `D02_logVolumeShock60` | Magnitude-preserving volume shock: a 15x day is not a 2x day | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (alpha-opportunity-model-v5) | ALPHA_CANDIDATE | 21 |  | Level 1 at H21; baseline B3 |
| `D03_tradingValueShock5_60` | KRW traded-value shock (price x volume): capital-weighted attention | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (kr-alpha-discovery-tournament-v1) | ALPHA_CANDIDATE | 21 |  | Level 1 at H21 |
| `D04_shockPersistence5d` | Number of recent high-volume days: sustained versus one-off attention | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (alpha-opportunity-model-v5) | ALPHA_CANDIDATE | 21 |  | Level 1 at H21 |
| `D05_turnoverToMarketCap60` | Traded value over market cap: investor disagreement and glamour (Lee-Swaminathan) | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 63 |  | compute in Phase B |
| `D06_priceVolumeDivergence` | Volume rising while price stalls (or the reverse) | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 21 |  | compute in Phase B |
| `D07_volumePriceAlignment` | Signed volume shock: heavy volume on up versus down days | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (alpha-opportunity-model-v5) | ALPHA_CANDIDATE | 21 |  | Level 1 at H21 |
| `D08_abnormalVolumeUpClose` | Volume shock with a close near the high: buying pressure absorbed | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 21 |  | compute in Phase B (KRX bars carry high/low) |
| `D09_abnormalVolumeDownClose` | Volume shock with a close near the low: distribution | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 21 |  | compute in Phase B |
| `D10_liquidityAcceleration` | Change in traded value (20 vs 120 sessions): a name entering or leaving investors' attention | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 63 |  | compute in Phase B |
| `D11_accumulationDistributionProxy` | Close-location value x volume: OHLCV accumulation PROXY, never investor-type flow | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 21 |  | compute in Phase B; label OHLCV_PROXY_NOT_INVESTOR_FLOW |

## E. Liquidity and market microstructure

Primary horizon H126; secondary H21 (cost proxies and suspension checks act at the trading horizon).

| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |
|---|---|---|---|---|---|---:|---|---|
| `E01_amihudIlliquidity60` | Illiquidity premium: holders of illiquid names are paid for it (Amihud) | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (kr-alpha-discovery-tournament-v1) | ALPHA_CANDIDATE | 126 |  | Level 1 at H126; baseline B3 |
| `E02_logAdv60` | Size of daily trading: liquidity level | PIT_SIGNAL_CLOSE | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, kr-model-overlay-portfolio-v1) | CONTROL | 126 | factor anatomy UNSTABLE_OR_REGIME_DEPENDENT; within industry +0.041 (+1.6) | reuse sealed readings |
| `E03_capacityMedianTradedValue60` | How much can be traded without moving the price: capacity CONSTRAINT | PIT_SIGNAL_CLOSE | READY | NOT_APPLICABLE | COST_CAPACITY | 126 |  | portfolio layer only (order <= 1% of median traded value) |
| `E04_tradabilityGuard20` | Positive volume on each of the last 20 sessions: the name can actually be traded | PIT_SIGNAL_CLOSE | READY | NOT_APPLICABLE | ELIGIBILITY_FILTER | 126 |  | eligibility only |
| `E05_highLowSpreadProxy` | Corwin-Schultz style spread estimate from daily high/low: a COST proxy, not a quoted spread | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | NOT_APPLICABLE | COST_CAPACITY | 21 |  | compute in Phase B for the cost model only |
| `E06_volatilityConditionalOnVolume` | Abnormal range on abnormal volume: price impact of trading | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 126 |  | compute in Phase B |
| `E07_suspensionStaleRisk` | Unchanged close with zero volume: a suspension, often before a terminal event | PIT_SIGNAL_CLOSE | READY | NOT_APPLICABLE | ELIGIBILITY_FILTER | 21 |  | eligibility and terminal-event handling (tournament closure) |
| `E08_trueBidAskSpread` | Quoted bid-ask spread and depth | NO_SOURCE | NOT_FEASIBLE | NOT_APPLICABLE | COST_CAPACITY | 21 | no quote or order-book source exists in this repository and none was found free; daily OHLCV proxies (E05) are not a substitute | none; use E05 proxy with that label |

## F. Risk characteristics

Primary horizon H126; secondary none.

| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |
|---|---|---|---|---|---|---:|---|---|
| `F01_totalVolatility63` | Low-volatility anomaly: leverage-constrained investors overpay for volatile names | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1, kr-alpha-discovery-tournament-v1, alpha-opportunity-model-v5) | ALPHA_CANDIDATE | 126 |  | Level 1 at H126; decide alpha versus construction role |
| `F02_downsideVol126` | Downside volatility: crash-prone names | PIT_SIGNAL_CLOSE | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-factor-anatomy-v1, kr-stock-within-industry-anatomy-v1, kr-model-overlay-portfolio-v1, four-factor-signal-attribution-audit-v1) | CONTROL | 126 | market-wide NO_CLEAR_MONOTONIC_PATTERN; within industry +0.062 (+2.6); KR lowvol sleeve +0.0511 regional reading, not pooled | reuse sealed readings; portfolio-construction role decided in Level 4 |
| `F03_beta252` | Market beta: betting-against-beta | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1, kr-alpha-discovery-tournament-v1) | ALPHA_CANDIDATE | 126 |  | Level 1 at H126 |
| `F04_idiosyncraticVol` | Residual volatility after market and industry | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 126 |  | compute in Phase B |
| `F05_maxDrawdown252` | Trailing maximum drawdown | PIT_SIGNAL_CLOSE | READY | PRIOR_INCONCLUSIVE (regional-alpha-model-v1, kr-alpha-discovery-tournament-v1) | RISK_CONSTRUCTION | 126 |  | risk diagnostics in Level 4 |
| `F06_crashExposure` | Downside beta / co-skewness with 069500.KS | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | NOT_APPLICABLE | RISK_CONSTRUCTION | 126 |  | Level 4 risk diagnostics |
| `F07_benchmarkCorrelation252` | Correlation with 069500.KS: how much active risk a position adds | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | NOT_APPLICABLE | RISK_CONSTRUCTION | 126 |  | Level 4 risk diagnostics |
| `F08_bookConcentration` | Name, industry and covariance concentration of a 0-5 name book | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | NOT_APPLICABLE | RISK_CONSTRUCTION | 126 |  | Level 4 risk diagnostics |

## G. Investor flow and ownership

Primary horizon H21; secondary H63 (accumulation is read over weeks; disclosures resolve over a quarter).

| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |
|---|---|---|---|---|---|---:|---|---|
| `G01_foreignNetBuying` | Foreign investors' net buying: informed or flow-driven demand | NO_SOURCE | SOURCE_BLOCKED | BLOCKED | ALPHA_CANDIDATE | 21 | KRX data portal (MDCSTAT02302/02303) answered HTTP 400 LOGOUT on every candidate from Actions; the Open API key does not reach investor-type statistics (workflow-hygiene v2.25) | one bounded re-probe through the Probes dropdown only if the source condition changes |
| `G02_institutionalNetBuying` | Institutional net buying | NO_SOURCE | SOURCE_BLOCKED | BLOCKED | ALPHA_CANDIDATE | 21 | KRX data portal (MDCSTAT02302/02303) answered HTTP 400 LOGOUT on every candidate from Actions; the Open API key does not reach investor-type statistics (workflow-hygiene v2.25) | one bounded re-probe through the Probes dropdown only if the source condition changes |
| `G03_retailNetBuying` | Retail net buying (often a contrarian indicator) | NO_SOURCE | SOURCE_BLOCKED | BLOCKED | ALPHA_CANDIDATE | 21 | KRX data portal (MDCSTAT02302/02303) answered HTTP 400 LOGOUT on every candidate from Actions; the Open API key does not reach investor-type statistics (workflow-hygiene v2.25) | one bounded re-probe through the Probes dropdown only if the source condition changes |
| `G04_investorTypePersistence` | Persistence of investor-type flow over 5-20 sessions | NO_SOURCE | SOURCE_BLOCKED | BLOCKED | ALPHA_CANDIDATE | 21 | KRX data portal (MDCSTAT02302/02303) answered HTTP 400 LOGOUT on every candidate from Actions; the Open API key does not reach investor-type statistics (workflow-hygiene v2.25) | one bounded re-probe through the Probes dropdown only if the source condition changes |
| `G05_flowMomentumConfirmation` | Price leadership confirmed by foreign/institutional accumulation | NO_SOURCE | SOURCE_BLOCKED | BLOCKED | ALPHA_CANDIDATE | 21 | KRX data portal (MDCSTAT02302/02303) answered HTTP 400 LOGOUT on every candidate from Actions; the Open API key does not reach investor-type statistics (workflow-hygiene v2.25) | one bounded re-probe through the Probes dropdown only if the source condition changes |
| `G06_largeHolderAccumulation` | A disclosed 5%+ holder increasing its stake: identified capital committing | PIT_RECEIPT_DATED | DATA_BUILD_REQUIRED | BLOCKED | ALPHA_CANDIDATE | 21 | majorstock.json serves a rolling two years: collected receipts span 2024-09-24..2026-09-23 (1,285 events, 119 current names); older history needs an official filing-document parser (BLOCKED_HISTORICAL_DEPTH, docs/dart-ownership-history-replay-integrity-v1.md) | schedule prospective collection (separate change); no historical evaluation possible |
| `G07_largeHolderReduction` | A disclosed holder reducing or exiting | PIT_RECEIPT_DATED | DATA_BUILD_REQUIRED | BLOCKED | ALPHA_CANDIDATE | 21 | majorstock.json serves a rolling two years: collected receipts span 2024-09-24..2026-09-23 (1,285 events, 119 current names); older history needs an official filing-document parser (BLOCKED_HISTORICAL_DEPTH, docs/dart-ownership-history-replay-integrity-v1.md) | as G06 |
| `G08_shortSellingVolume` | Short-sale share of volume: informed pessimism | NO_SOURCE | SOURCE_BLOCKED | BLOCKED | ALPHA_CANDIDATE | 21 | KRX short-selling screens MDCSTAT301/305: bld codes unresolved and the portal unreachable; full bans 2020-03..2021-05 and 2023-11-05..2025-03-31 make the variable regime-dependent (kr_short_selling.regime_label) | Probes dropdown only |
| `G09_shortBalanceChange` | Change in outstanding net short position | NO_SOURCE | SOURCE_BLOCKED | BLOCKED | ALPHA_CANDIDATE | 21 | KRX short-selling screens MDCSTAT301/305: bld codes unresolved and the portal unreachable; full bans 2020-03..2021-05 and 2023-11-05..2025-03-31 make the variable regime-dependent (kr_short_selling.regime_label) | Probes dropdown only |

## H. Industry and cross-sectional structure

Primary horizon H126; secondary H63 (industry anatomy measured REL_MOM_63 as the shorter leadership reading).

| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |
|---|---|---|---|---|---|---:|---|---|
| `H01_industryRelMom126` | Industry leadership persists while its economics keep improving | PIT_RECONSTRUCTED_MEMBERSHIP | ALREADY_TESTED | PRIOR_POSITIVE_DEVELOPMENT (kr-industry-opportunity-anatomy-v1, kr-integrated-alpha-portfolio-v1, kr-alpha-discovery-tournament-v1) | CONTROL | 126 | IC +0.066 (mean/se +1.2) but year IC -0.18..+0.29; leave-largest-out tercile +5.4pp -> +0.1pp; integrated D trailed A 2017-2024 and led only in 2025-2026 (regime- and industry-concentrated) | reuse sealed readings; baseline B0 |
| `H02_industryRelMom63` | Shorter industry leadership | PIT_RECONSTRUCTED_MEMBERSHIP | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-industry-opportunity-anatomy-v1) | ALPHA_CANDIDATE | 63 |  | reuse sealed reading |
| `H03_industryBreadthAboveMA126` | Broad participation inside an industry: leadership not driven by one name | PIT_RECONSTRUCTED_MEMBERSHIP | ALREADY_TESTED | PRIOR_POSITIVE_DEVELOPMENT (kr-industry-opportunity-anatomy-v1, kr-integrated-alpha-portfolio-v1) | ALPHA_CANDIDATE | 126 | IC +0.059 (+1.2); formal INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED is regime- and industry-concentrated | reuse sealed reading |
| `H04_withinIndustryDispersion126` | Dispersion of member returns inside an industry: room for stock selection | PIT_RECONSTRUCTED_MEMBERSHIP | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-industry-opportunity-anatomy-v1) | CONTEXT_CONDITIONING | 126 | IC +0.069 (+1.2), survives leave-largest-out | reuse sealed reading; conditioning only |
| `H05_crossIndustryDispersion` | Dispersion across industry returns: how much industry allocation matters at T | PIT_RECONSTRUCTED_MEMBERSHIP | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | CONTEXT_CONDITIONING | 126 |  | compute in Phase B |
| `H06_industryConcentrationTop1` | Largest member's cap share inside an industry | PIT_RECONSTRUCTED_MEMBERSHIP | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-industry-opportunity-anatomy-v1) | CONTEXT_CONDITIONING | 126 |  | reuse sealed reading |
| `H07_leadershipPersistence` | Rank autocorrelation of industry leadership | PIT_RECONSTRUCTED_MEMBERSHIP | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | CONTEXT_CONDITIONING | 126 |  | compute in Phase B |
| `H08_equalVsCapWeightIndustry` | Equal-weight minus cap-weight trailing industry return: broad versus mega-cap-led moves | PIT_RECONSTRUCTED_MEMBERSHIP | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 126 |  | compute in Phase B |
| `H09_marketBreadth` | Share of top-120 names above their 200-session mean | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | CONTEXT_CONDITIONING | 126 |  | compute in Phase B (measured names and denominator published) |
| `H10_marketConcentrationTop2` | Samsung Electronics + SK Hynix share of the top-120 cap | PIT_SIGNAL_CLOSE | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | CONTEXT_CONDITIONING | 126 |  | compute in Phase B |
| `H11_industryEarningsContext` | Median net-income improvement inside an industry | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_NEGATIVE_DEVELOPMENT (kr-industry-opportunity-anatomy-v1) | ALPHA_CANDIDATE | 126 | IC -0.185 (mean/se -3.0), 248 valid dates | no new Level 1 |
| `H12_industryValuationContext` | Median book-to-market inside an industry | PIT_RECEIPT_DATED | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-industry-opportunity-anatomy-v1) | ALPHA_CANDIDATE | 126 | IC -0.059 (-0.8) | reuse sealed reading |

## I. Macro, FX and global exposures

Primary horizon H126; secondary none.

| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |
|---|---|---|---|---|---|---:|---|---|
| `I01_kospiTrendVolState` | 069500.KS below its 200-session mean and/or annualised vol63 > 25%: the FAST market layer | PIT_SIGNAL_CLOSE | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-market-risk-model-v1) | CONTEXT_CONDITIONING | 126 | market risk model v1: NO_CANDIDATE_NOMINATED_CONTROL_RETAINED | reuse sealed model; conditioning variable for X6 |
| `I02_vixLevel` | Global risk appetite (VIX level in its own past-only distribution): the TRANSITION market layer | PIT_SIGNAL_CLOSE | ALREADY_TESTED | PRIOR_INCONCLUSIVE (kr-market-risk-model-v1) | CONTEXT_CONDITIONING | 126 | the tournament excluded the FRED family as revised-history; VIX is a market close, used only as the sealed market model uses it | reuse sealed model |
| `I03_krTermSpread` | Korean 10y-3m slope: the SLOW layer (re-steepening after inversion) | REVISED_HISTORY | PIT_UNSAFE | PRIOR_INCONCLUSIVE (kr-market-risk-model-v1) | CONTEXT_CONDITIONING | 126 | ECOS series carry vintageStatus REVISED_HISTORY; a historical value is usable only from its retained fetch (kr_market_context) | prospective use only |
| `I04_krPolicyRate` | BOK base rate level and change | REVISED_HISTORY | DATA_BUILD_REQUIRED | UNTESTED | CONTEXT_CONDITIONING | 126 | config.json ecos.KR.BaseRate sourceStatus AMBIGUOUS_SOURCE (item code unresolved) | resolve the ECOS item code in the market-context line |
| `I05_krCreditSpread` | Corporate minus government 3y yield | REVISED_HISTORY | DATA_BUILD_REQUIRED | UNTESTED | CONTEXT_CONDITIONING | 126 | CorpBond_3Y sourceStatus AMBIGUOUS_SOURCE (817Y002 item code for the corporate series unresolved) | resolve item code |
| `I06_krInflation` | CPI / core CPI change | REVISED_HISTORY | PIT_UNSAFE | UNTESTED | CONTEXT_CONDITIONING | 126 | CPI AMBIGUOUS_SOURCE / CoreCPI DATA_LINEAGE_UNRESOLVED, revised history without release vintages | prospective only |
| `I07_krExportsActivity` | Exports, industrial production, leading index: export-cycle regime | REVISED_HISTORY | PIT_UNSAFE | UNTESTED | CONTEXT_CONDITIONING | 126 | Exports NOT_AVAILABLE; IndustrialProduction DATA_LINEAGE_UNRESOLVED; LeadingIndex revised without vintages | prospective only |
| `I08_usdKrw` | KRW/USD level and change | PUBLICATION_TIME_UNRESOLVED | PIT_UNSAFE | UNTESTED | CONTEXT_CONDITIONING | 126 | FX_PUBLICATION_TIME_UNRESOLVED (alpha-information-inventory-v1) | ECOS 731Y001 with a verified fixing time |
| `I09_fxBeta26w` | Stock-level exposure to KRW/USD | PUBLICATION_TIME_UNRESOLVED | PIT_UNSAFE | UNTESTED | ALPHA_CANDIDATE | 126 | FX_PUBLICATION_TIME_UNRESOLVED; excluded by regional_alpha_features | after I08 is resolved |
| `I10_semiconductorCycleSOX` | Philadelphia semiconductor index trend: global chip cycle for the KR electronics industry | NO_SOURCE | DATA_BUILD_REQUIRED | UNTESTED | CONTEXT_CONDITIONING | 126 | dashboard-only fetch; no pinned historical snapshot | snapshot with the benchmark acquisition rules |
| `I11_globalFinancialConditions` | US HY spread, real yields, NFCI | REVISED_HISTORY | PIT_UNSAFE | UNTESTED | CONTEXT_CONDITIONING | 126 | 10 of 28 FRED panel columns have no ALFRED vintages (macro vintage invariants v2.9) | none historically |
| `I12_commodityExposure` | Oil and metals price trends for commodity-sensitive industries | NO_SOURCE | DATA_BUILD_REQUIRED | UNTESTED | CONTEXT_CONDITIONING | 126 | no commodity price series is collected | optional; lowest priority |

## J. Events and alternative information

Primary horizon H21; secondary H63 (payout-policy events resolve over a quarter).

| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |
|---|---|---|---|---|---|---:|---|---|
| `J01_periodicFilingEvent` | Post-filing drift: prices under-react to the fundamental change a new periodic report reveals | PIT_RECEIPT_DATED | DERIVABLE_FROM_EXISTING_DATA | UNTESTED | ALPHA_CANDIDATE | 21 |  | compute in Phase B from receipt dates |
| `J02_dividendPolicyChange` | Dividend initiation, increase or cut: management's signal about durability | PIT_RECEIPT_DATED | DATA_BUILD_REQUIRED | UNTESTED | ALPHA_CANDIDATE | 63 | alotMatter.json not collected universe-wide; endpointConfidence CANDIDATE_UNCONFIRMED | bounded collection for the ever-top-120 list |
| `J03_buybackAnnouncement` | Treasury-share acquisition decision: managers buying when they see value | PIT_RECEIPT_DATED | DATA_BUILD_REQUIRED | UNTESTED | ALPHA_CANDIDATE | 21 | list.json disclosure families not collected universe-wide | bounded list.json collection; report-name match is a reading list, never a verdict |
| `J04_materialDisclosure` | Material events (capital raise, M&A, contracts) | PIT_RECEIPT_DATED | DATA_BUILD_REQUIRED | UNTESTED | ALPHA_CANDIDATE | 21 | as J03; M&A outcomes carry hindsight risk (terminal economics unresolved) | after J03 |
| `J05_shortSellingRegime` | Dated short-selling ban regimes | PIT_DATED_CALENDAR | READY | NOT_APPLICABLE | CONTEXT_CONDITIONING | 21 |  | conditioning marker only |
| `J06_searchAttention` | Search-volume attention | NO_SOURCE | NOT_FEASIBLE | NOT_APPLICABLE | ALPHA_CANDIDATE | 21 | no source with verified point-in-time history and permitted use | none |
| `J07_newsTextSentiment` | News or text sentiment | NO_SOURCE | NOT_FEASIBLE | NOT_APPLICABLE | ALPHA_CANDIDATE | 21 | no archived PIT news source; a large NLP project is out of scope | none |
| `J08_analystRevisions` | Consensus estimate revisions | NO_SOURCE | NOT_FEASIBLE | BLOCKED | ALPHA_CANDIDATE | 63 | FnGuide/FnSpace ToS-blocked; no free PIT history (alpha-information-inventory-v1) | none |

## Level 2 baselines

| Baseline | Features |
|---|---|
| B0_MARKET_INDUSTRY_PRICE_REFERENCE | `H01_industryRelMom126`, `A05_relative126` |
| B1_VALUE_PROFITABILITY | `B01_bookToMarket`, `B02_earningsYield`, `C01_returnOnAssets`, `C05_ocfToAssets` |
| B2_PRICE_MOMENTUM | `A05_relative126`, `A07_momentum12_1`, `A11_distance52wHigh` |
| B3_VOLUME_LIQUIDITY | `D02_logVolumeShock60`, `E01_amihudIlliquidity60`, `E02_logAdv60` |
| B4_COMBINED_SIMPLE | `H01_industryRelMom126`, `A05_relative126`, `A07_momentum12_1`, `B01_bookToMarket`, `B02_earningsYield`, `C01_returnOnAssets`, `C05_ocfToAssets`, `D02_logVolumeShock60`, `E01_amihudIlliquidity60` |

## Level 3 interactions (declared before outcomes; at most 6)

| Interaction | Features | Economic argument | Negative control | H | Status |
|---|---|---|---|---:|---|
| X1_valueByBusinessConfirmation | `B05_industryRelativeValue`, `B08_valueBusinessConfirmation` | cheapness with a sound business is mispricing; cheapness with a deteriorating one is a value trap (H2, CANDIDATE_SIGNAL_FAMILY) | the same confirmation contrast among expensive names | 126 | READY_TO_REGISTER |
| X2_momentumByAbnormalVolume | `A05_relative126`, `D05_turnoverToMarketCap60` | Lee-Swaminathan: turnover tells whether momentum is early (low turnover) or late (high turnover) | turnover interacted with a permuted momentum rank | 126 | READY_TO_REGISTER |
| X3_industryLeadershipByStockStrength | `H01_industryRelMom126`, `A09_industryRelativeMomentum126` | a leader inside a leading industry versus a laggard riding the industry | stock strength inside lagging industries | 126 | READY_TO_REGISTER |
| X4_priceLeadershipByInvestorAccumulation | `A05_relative126`, `G01_foreignNetBuying` | leadership confirmed by identified capital is less likely to be noise | OHLCV accumulation proxy (D11) in place of investor flow | 21 | BLOCKED (G01_foreignNetBuying) |
| X5_volatilityByLiquidity | `F01_totalVolatility63`, `E01_amihudIlliquidity60` | the low-volatility effect may live only in liquid names where arbitrage is cheap | volatility interacted with a permuted liquidity rank | 126 | READY_TO_REGISTER |
| X6_marketRegimeByRelativeMomentum | `I01_kospiTrendVolState`, `A05_relative126` | momentum crashes cluster in market rebounds after stress | the same split on a lagged (one-year-old) regime label | 126 | READY_TO_REGISTER |

## Prior studies

| Study | Verdict | Evidence class | Measured individually | Used jointly | Result |
|---|---|---|---:|---:|---|
| kr-factor-anatomy-v1 | DESCRIPTIVE_MAP | EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY | 12 | 0 | `docs/results/kr-factor-anatomy-v1-result.json` |
| kr-industry-opportunity-anatomy-v1 | DESCRIPTIVE_MAP | EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY | 7 | 0 | `docs/results/kr-industry-opportunity-anatomy-v1-result.json` |
| kr-stock-within-industry-anatomy-v1 | DESCRIPTIVE_MAP | EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY | 13 | 0 | `docs/results/kr-stock-within-industry-anatomy-v1-result.json` |
| kr-model-overlay-portfolio-v1 | DEVELOPMENT_REJECT | DEVELOPMENT_ON_OUTCOME_EXPOSED_HISTORY | 0 | 11 | `docs/results/kr-model-overlay-portfolio-v1-result.json` |
| kr-integrated-alpha-portfolio-v1 | INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED; NO_UNAMBIGUOUS_FINAL_ARCHITECTURE | EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY | 0 | 3 | `docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-completed-audit.json` |
| kr-alpha-discovery-tournament-v1 | BLOCKED_BY_DATA_INTEGRITY | EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY | 0 | 11 | `docs/results/kr-alpha-discovery-tournament-v1-result.json` |
| kr-market-risk-model-v1 | NO_CANDIDATE_NOMINATED_CONTROL_RETAINED | EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY | 3 | 0 | `docs/results/kr-market-risk-model-v1-result.json` |
| regional-alpha-model-v1 | NO_MODEL_EVIDENCE | HISTORICAL_DISCOVERY_CLOSED_ON_EXISTING_FEATURE_SET | 0 | 16 | `docs/alpha-research-foundation-v2-errata.md` |
| alpha-opportunity-model-v5 | INCONCLUSIVE | HISTORICAL_DISCOVERY_ON_AN_EXPOSED_SAMPLE | 0 | 8 | `docs/results/alpha-opportunity-model-v5-result.json` |
| fundamental-acceleration-discovery-v1 | CASE_D_NO_DISCOVERY_EVIDENCE | HISTORICAL_DISCOVERY | 1 | 0 | `docs/results/fundamental-acceleration-discovery-report.json` |
| four-factor-signal-attribution-audit-v1 | WEAK_AND_REGION_SIGN_UNSTABLE | HISTORICAL_AUDIT | 0 | 3 | `docs/results/four-factor-signal-attribution-audit-report.json` |
| opportunity-radar-model | REJECTED_ACCEPTANCE_FAILED | HISTORICAL_DISCOVERY | 0 | 2 | `docs/alpha-information-inventory-v1-research-map.md` |

## Multiple testing (declared before outcomes)

- Level 1: `BENJAMINI_YEKUTIELI_FDR_Q0.10_WITHIN_FAMILY`
- Level 2: `HOLM_FWER_0.05_ACROSS_FAMILY_ABLATIONS`
- Level 3: `HOLM_FWER_0.05_ACROSS_INTERACTIONS`
