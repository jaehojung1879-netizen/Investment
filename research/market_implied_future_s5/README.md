# S5 · Market-Implied Future & Risk Pricing Discovery

**SOURCE_ONLY / AUTHOR_VALIDATION_ONLY · no alpha test · no activation.**

Owner goal: 6–12 month net, risk-adjusted investment decisions vs SPY/KODEX 200.
S5 must NOT turn into another volatility overlay tournament or pure mathematical study.
S5-A = term and forward variance information; S5-B = physical variance forecast and
risk premium; S5-C = option-chain state-price density; S5-D = genuinely novel latent
structure; S5-E = economic feasible set vs market state pricing.
Only S5-A source/math infrastructure is implemented here. All outcome tests require
a separately approved protocol and new evidence, not a replay of a sealed result.

## Prior evidence and source boundary

- #367 exact head 7aa0b991: 128 evaluation rows, five independent drawdown events;
  VIX addition Brier 0.221 vs M1 0.213 and base rate 0.162; VIX/VIX3M unmeasured.
  Do not reopen that experiment or treat these as new signals.
- S2 #384 forced flows, S3/#383 protected firms and S4-B #388 physical feasible sets
  remain separate; read only permitted summary/registry. No protected dataset or
  historical future return joined.
- Official Cboe methodology:
  https://cdn.cboe.com/api/global/us_indices/governance/Volatility_Index_Methodology_Selected_SPX_Target_Expected_Volatility_Term_Indices.pdf
  sections 2.1, 3, 5 distinguish 9/30/93/184/366 calendar days, eligible options,
  and history vs launch. VIX9D/VIX3M launched Oct 2013, VIX6M Nov 2013,
  VIX1Y 2018; conservative full-year floors 2014/2019. VIX current methodology
  introduced 2003; conservative 2004 floor. Floors are not PIT proof.
- Cboe historical catalog:
  https://www.cboe.com/tradable-products/vix/vix-historical-data
  verified links VIX_History.csv and VIX9D_History.csv. Web retrieval rejected CSV;
  container DNS failed on the VIX URL. No original CSV bytes acquired.
- FRED official distributor tables https://fred.stlouisfed.org/data/VIXCLS
  and https://fred.stlouisfed.org/data/VXVCLS verified daily closes through Nov 24,
  2026 (last update Nov 25 08:37 CST). FRED CSV export routes and exact
  accepted schema remain to be tested on real bytes. No claim that historical
  Cboe/FRED values were published unchanged at each decision time.
- VIX6M/VIX1Y download paths unverified: not silently invented. Find official
  publication endpoints, verify response headers/bytes and license before
  registering. No proprietary full series copied into git.
- Federal Reserve papers:
  https://www.federalreserve.gov/econres/feds/expected-stock-returns-and-variance-risk-premia.htm
  https://www.federalreserve.gov/econres/feds/variance-risk-premia-asset-predictability-puzzles-and-macroeconomic-uncertainty.htm
  Documented historical VRP predictability tends to be strongest at short
  horizons, not proof of a 6–12m trading advantage. A short horizon signal
  can be an economic intermediate target, not a substitute for final horizon.

## Actual arithmetic check (public table transcription, not raw CSV)

Same-day values, units annualized percent, observed in the FRED HTML tables on
2026-11-27 KST. Do not treat as full raw archive, a release-time receipt,
or a forecast. Values computed using (93*v3^2 - 30*v30^2)/63 then square root.

| Session | VIX | VIX3M | 30–93d forward vol proxy |
|---|---:|---:|---:|
| 2026-11-18 | 24.56 | 24.29 | 24.16 |
| 2026-11-19 | 28.44 | 27.03 | 26.33 |
| 2026-11-20 | 35.89 | 30.94 | 28.28 |
| 2026-11-23 | 26.62 | 25.50 | 24.95 |
| 2026-11-24 | 26.36 | 25.47 | 25.04 |

The 20 Nov inversion was concentrated relatively toward the near end; both
near and forward volatility rose. Five observed dates are not an experiment.
Other maturity index data not admitted. No realized-return calculation.

## Math and nonidentification

W(T) = T/365 * (index/100)^2. F(a,b) = 365*(W(b)-W(a))/(b-a).
Different index option baskets and close clocks make this an approximate
forward-variance diagnostic, not a tradable forward swap. Negative F is
preserved and square-root vol is absent; missing adjacent endpoint is absent.
No interpolating absent nodes, forward-filling, or clipping negative values.

VRP = implied annualized decimal variance minus *ex-ante expected* realized
annualized variance for matched underlying/horizon/sampling conventions.
Realized future variance is a later outcome, not a feature. VIX minus
historical volatility is not the same quantity. This code checks only units
and domain; it does not certify any forecast receipt or estimate VRP from data.

With terminal payouts (70,100,130), q=(.25,.5,.25), discount .98, state prices
are (.245,.49,.245), and price=98. Physical p+=(.10,.50,.40) gives mean 109,
while p-=(.40,.50,.10) gives mean 91. Both are compatible with identical
state prices using positive SDF m_i=.98*q_i/p_i. The test reproduces the
opposite expected physical return signs. Even a full exact Q distribution
cannot identify P or intrinsic value without independent restrictions on
risk pricing/economic states. Do not substitute option-implied probabilities
for scenario probabilities in a DCF.

## Run

From repository root with Python 3.11+:
```sh
python -m research.market_implied_future_s5.acquire --out /tmp/s5-originals
python -m research.market_implied_future_s5.foundation --manifest /tmp/s5-originals/manifest.json
python -m pytest -q tests/test_market_implied_future_s5.py
```

Acquisition uses one bounded request per fixed known candidate, no redirect,
no retry, no access-control bypass. On 401/403/429 stop that symbol. All raw
files and attempt manifest live in a new external directory; retain exact
bytes privately where permitted. Hash proves byte identity, not authenticity.
Successful source admission is current-history only; no assumption of vintage.
A partial manifest can be inspected even when acquisition exits 2.
Census union is observed nonmissing dates, not exchange-calendar completeness;
exact common eligible sessions and launch/clock audits are next gate.

## Next gates (not executable authorizations)

1. Verify original source files and publication/methodology history, exact
   calendar coverage, actual first-live date and historical revisions. Compare
   Cboe and FRED duplicate distributor values, not independent evidence.
2. Independently specify a fixed ex-ante RV model, price source/total-return
   source, trading date after all closes/releases, 30/93/184/366-day targets,
   no future labels in features. Keep Q and P separate. For RV use SPX
   underlying returns, for investment use SPY total return; do not equate.
3. Assess effective nonoverlapping samples and block inference/power before
   exposure to new outcomes; split 1–3m intermediate and 6–12m primary.
   Compare against unconditional, price/vol baseline, exposure-matched ETF,
   costs, risk and drawdown. #367 five-event limitation not solved by more
   overlapping rows. Freeze direction, model, metrics, test family, MDE and
   stop rules before any new historical/forward experiment.
4. S5-C raw chain: enforce synchronized European SPX quotes, expiry/settlement
   conventions, bid/ask, forward and discount, no-arbitrage checks and tails;
   Q not P. Vendor licensing and affordable source gate. Do not treat VIX,
   SKEW or put/call as a full distribution.
5. S5-D mathematical discovery only after independent source gain: strictly
   causal transforms, no centered smoothing/wavelet edge leakage, latent
   filtered not smoothed states, change point detection delay, multiplicity
   and independent forward tests. S5-E same maturity/cash-flow claim,
   model uncertainty and SDF restrictions; no automatic valuation or trade.

Never promote SOURCE_ONLY to PASS_TO_PREREG solely on parser/test success.
