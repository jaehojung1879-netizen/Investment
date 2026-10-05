# kr-integrated-alpha-portfolio-v1 — final integrated KR architecture (development study)

> **PREREGISTRATION + HARNESS + SYNTHETIC TESTS ONLY. NO HISTORICAL OUTCOME HAS BEEN COMPUTED.**
> `scientificStatus: EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`. This is an architecture comparison on Korean history that is already outcome-exposed,
> built from three sealed, outcome-exposed component studies. It has no prospective validity. Nothing in it is called validated, predictive, confirmed or production.

## 1. Why the project moves from components to integration

The market risk model, the industry anatomy and the stock within-industry anatomy are sealed. Each answered a narrow question in isolation. The remaining
question is not "which component is best" but **which combination of those components is worth recording prospectively** — and a component can look useful alone
and add nothing (or hurt) once the others are present. So instead of building an Industry Model v1 and a Stock Model v1 first, this study compares six **fixed**
architectures on one calendar, one set of costs and one execution engine, then stops. It is intended to be the **last** large historical architecture study:
after its sealed result the default next step is prospective receipts, not another historical redesign.

## 2. The six architectures

| | MARKET OFF | MARKET C0 | MARKET C1 |
|---|---|---|---|
| **INDUSTRY OFF** | A. S | B. S+M0 | C. S+M1 |
| **INDUSTRY ON** | D. I+S | E. I+S+M0 | F. I+S+M1 |

The passive reference (069500.KS, the repository's accepted return basis) is reported **separately**. It is an adjusted-index return with partial observed
distributions: neither a price return nor a complete shareholder total return, and it is never called either.

## 3. What each layer is

**Stock-only (S) — always on, identical in all six.** Within its own industry (the frozen PIT industry membership v4, used *only* as the peer group, at least
5 classified members), each eligible stock gets `VALUE_SCORE` = mean of the within-industry percentiles of `bookToMarketProxy` and `earningsYieldProxy` (both
required, never substituted) and `STOCK_SCORE` = equal-weight mean of `VALUE_SCORE` and the within-industry percentile of `negativeDownsideVol126` (higher = calmer).
Excluded from the score: stock momentum, `logADV` as alpha (liquidity is investability only), and OCF improvement. Missing stays missing: a score needs every
primary component. The book is the top five by `STOCK_SCORE` (ties by ticker) among stocks that are tradable with ADV60 at least KRW 3bn.

**What Industry adds (I).** `INDUSTRY_SCORE` = 50% cross-industry percentile of `REL_MOM_126` + 50% of `BREADTH_ABOVE_MA_126` (the sealed anatomy's features, both
required). Every member stock inherits its industry's score and `COMBINED_SCORE` = 50% `STOCK_SCORE` + 50% `INDUSTRY_SCORE`. The 50/50 is fixed and untuned. It
changes **which names** are held and nothing else; with Industry OFF the industry contributes exactly zero.

**What Market adds (M).** Nothing about selection. The identical underlying S or I+S book is built first; the sealed Market Risk Model's multiplier
(1.0 / 0.7 / 0.4, C0 or C1, called directly) then **scales the already-selected book**. It never changes eligibility or order, and there is no leverage. It trades on
the model's own timing (weekly decision at the week-end close, trade at the next session's close, only when the multiplier changes) as a pure scale of the held
book — drifted proportions kept, no new name, no swap — executed by the same engine as every other trade.

**Why C0 and C1 are both retained.** C0 is the existing overlay; C1 is the sealed model's shadow challenger whose formal non-nomination is preserved. They are judged
**separately**; a C1-better-than-C0 fact that does not clear its own rule is reported and not promoted.

## 4. One portfolio engine

Max 5 holdings; no leverage; inverse-downside-volatility water-fill sizing under the 30% name cap and the 1% ADV capacity cap; an observed positive-volume
execution quote is required (otherwise the order is deferred); anchors every 21 KR sessions from the fixed 2015-01-01 origin (the first on or after 2017-01-01, the
overlay study's coverage date), executing at the anchor close on the preceding completed weekly signal. Costs are the prior KR design's: buy 15 bp, sell 45 bp,
plus square-root impact; ×2 and ×3 stress are descriptive. Holdings are 0 to 5. There is **no absolute "do not invest" threshold**; the book simply holds the top
eligible names under the common rules. A held name with no observed close, no observed zero-volume quote and no terminal economics **blocks that architecture's
path** (it never silently disappears and no successor is substituted). **No architecture has a trading rule of its own.**

**Depth.** Before any outcome, every anchor must leave at least **10** eligible stocks for the S book and for the I+S book (twice the book size) and rank at
least **5** industries; otherwise the run stops before the lock, spending nothing. The pre-lock gates report eligible stocks per date.

## 5. Cash yield is a sensitivity, not a model input

The primary path earns zero KRW on cash. The repository already holds one defensible full-span series: the Bank of Korea base rate as a dated step function
(`data/bok-policy-rates.json`, first event 2009, verified through 2026-09-07; the event date is the first calendar day the rate applies). It is frozen **before**
any portfolio outcome is read, with the rate in force on the previous session's calendar date applying to each session's return. Variants: zero, the proxy, and the
proxy minus a 0.50 pp annual haircut floored at zero (the source supports no negative investable rate). The sensitivity is an **accounting overlay on the finished
primary path** — it adds `cash weight × cash return` to each session — so it can never change a name, a weight, a market state, a trade, a cost, a layer decision or
the final architecture. KOFR is not assumed to have full-span history and no ECOS item code is guessed. If the file cannot be read the sensitivity is marked
`DATA_UNAVAILABLE` and the primary study is unaffected. It is a policy-rate proxy, not an investable deposit or bill index. Sharpe and Sortino are not reported: a
risk-free assumption would have to be defended and none is claimed.

## 6. Metrics (every architecture)

Return: cumulative and annualized net, benchmark excess, gross and cost drag. Risk: max drawdown, worst H63 and H126 portfolio return, annualized and downside
volatility, drawdown recovery duration. Implementation: turnover, replacements, cost, average holdings, cash share, concentration, average gross equity exposure.
Stability: chronological halves, calendar years, drawdown episodes, 1×/2×/3× costs. Attribution: Industry ON vs OFF, C0 vs OFF, C1 vs OFF, C1 vs C0, and whether the
market overlay's value differs with versus without Industry (a difference of differences; no interaction model). Overlapping windows are descriptive; there is no
significance test and no multiplicity correction.

## 7. Pre-registered decision (by layer; no grand winner)

Bands are inherited unchanged from the sealed market model's nomination (none invented here): **non-inferior** = net annualized return ≥ base − 0.50 pp **and**
|max drawdown| ≤ 1.10 × base's; **meaningful gain** = return ≥ base + 0.50 pp **or** |max drawdown| ≤ 0.90 × base's. A pair is `IMPROVES` (non-inferior with a gain),
`NON_INFERIOR_NO_MEANINGFUL_GAIN`, `TRADE_OFF` (fails non-inferiority on one axis but gains meaningfully on the other) or `WORSE`.

* **Industry:** `DEVELOPMENT_SUPPORTED` only if I+S vs S (market off) `IMPROVES` and neither E vs B nor F vs C is `WORSE`. A primary `TRADE_OFF` is reported as
  `PARETO_TRADE_OFF`. Otherwise `INDUSTRY_LAYER_NOT_SUPPORTED`.
* **Market:** C0 and C1 are each judged on the **same** underlying portfolio without the overlay. Return participation lost is "justified" only while it stays inside the
  non-inferiority band; a larger loss bought with a larger drawdown reduction is a risk-preference choice this study does not make and is reported as a trade-off. If
  neither clears: `MARKET_OVERLAY_NOT_SUPPORTED_FOR_FINAL_PORTFOLIO`.
* **Final architecture** is assembled mechanically: Industry supported → I+S else S; then the supported market candidate on that portfolio, else none. A genuine trade-off
  gives `NO_UNAMBIGUOUS_FINAL_ARCHITECTURE`; an incomplete needed path gives `NO_FINAL_ARCHITECTURE_BLOCKED_PATH`. There is no post-hoc tie-break and no weighted utility.

## 8. Prospective receipts (designed, not running)

Each future decision date writes one immutable receipt **before** any outcome: all input identities, the industry membership used, the registered feature values,
`STOCK_SCORE` / `INDUSTRY_SCORE` / `COMBINED_SCORE`, the eligible names, both underlying books, the C0 and C1 states and multipliers, **all six target portfolios**, the
spec SHA, the code identity, the creation time and a receipt digest. The six targets are derived (underlying × multiplier), so the shared-underlying identity cannot be
broken by a typo. The ledger is append-only; nothing is written or scheduled by this change.

## 9. Lifecycle

`workflow_dispatch` on merged `main` only → committed spec and every pin (prior sealed studies byte-for-byte, the market mappings against the model's own sealed spec,
the inherited portfolio values against the overlay study, the cash source, the raw-input artifact) → signal-time feature assembly and the registered gates (can stop
before anything is spent) → no prior result, marker or lock → durable exclusive lock (`refs/tags/kr-integrated-alpha-portfolio-v1-execution-lock` and `-<specSha256>`,
atomic POST, any existing ref refuses) → execution marker → first market value read → exactly one result artifact → automatic exact-byte **Draft** seal PR → a human merges.
A failure after the lock consumes the study; it is never silently rerun.

## 10. Governance

Last large historical architecture study before prospective collection. After an unfavourable result: no v1.1, no threshold sweep, no new factor blend, no new market rule,
no top-k search, no cap or cost change. No sealed prior study is rerun or modified; their bytes are pinned by hash.

## 11. Limitations

Outcome-exposed single sample reused by three prior studies; industry membership is a reconstruction (most classified name-dates rest on a no-change inference, the 22
terminal securities are unclassified); issue-cap accounting proxies; the return basis has only partial distributions (banks and high-dividend names are unreliable); the
market scale-trade uses drifted proportions and is an engineering choice of this study; weekly signals and 21-session windows overlap; only large caps; no multiplicity
correction. A final architecture is something to **record prospectively**, not something that has been shown to work.
