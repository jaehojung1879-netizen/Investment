# Alpha information inventory v1 — data map

> **Read-only inventory. No factor weight, CHAMPION, selector, Kelly parameter,
> entry rule, regional allocation, macro multiplier, or production config is
> changed by this document.** No correlation with future returns, IC, or
> backtest performance was computed to produce any grade below. Grades reflect
> only: economic rationale, independent informativeness, point-in-time (PIT)
> correctness, historical reproducibility, coverage, ongoing acquirability,
> cost/license, and redundancy with information already in production or in
> the research-only feature matrix.

Companion documents: `alpha-information-inventory-v1.md` (executive report),
`alpha-information-inventory-v1-research-map.md` (what has already been
tested), `alpha-information-inventory-v1-gaps.md` (build priorities),
`alpha-information-inventory-v1-next-hypotheses.md` (pre-registered
candidates), `docs/results/alpha-information-inventory-v1.json`
(machine-readable version of this map).

Grade scale used throughout:

- **A — READY**: in repo or immediately usable, PIT-safe, sufficient history, free, no license issue.
- **B — REPAIRABLE**: data exists (in repo, or via a source already integrated for something else) but has a fixable timestamp/coverage/lineage/connectivity issue.
- **C — ACQUIRABLE**: not in repo yet, but an official/free historical PIT source exists and could be built.
- **D — PAID_OR_LICENSED**: useful, but reliable historical PIT requires payment or a license.
- **E — NOT_RESEARCHABLE_NOW**: no reliable historical PIT source, unstable definition, or severe survivorship gap.

Independence scale (economic judgment only, never a return correlation):
**HIGHLY_DISTINCT / PARTIALLY_DISTINCT / MOSTLY_REDUNDANT** against the 4
production sleeves (momentum/value/quality/lowvol, `pipeline/longterm.py:50`)
and the 31-feature research-only matrix (`pipeline/regional_alpha_features.py`,
see §1 below).

Time-axis buckets (economic judgment, not measured): **VERY_SHORT (1–21d)**,
**SHORT_MED (21–63d)**, **MEDIUM (63–126d)**, **MED_LONG (126–252d)**.

---

## 1. What "the 31 features" actually is

The number does not appear as a literal constant anywhere in the codebase.
It is reproducible by counting the eligible rows of
`regional_alpha_features.feature_manifest()` (`pipeline/regional_alpha_features.py:60-83`),
a **research-only module with zero production imports**
(its own docstring, `:1-4`; confirmed by grep — the only importer is
`regional_alpha_model.py`, itself an unexecuted challenger, see the research
map). Both regions land on exactly 31:

| Group | Count | Fields |
|---|---|---|
| PRICE | 21 | `return{21,63,126,252}`, `relative{21,63,126,252}`, `mom6`, `mom121`, `relative121`, `high52Distance`, `rsi14`, `ma200Distance`, `vol20`, `vol60`, `vol252`, `downsideVol252`, `maxDD252`, `beta252`, `volumeSurge5_60` |
| FUNDAMENTAL | 5 | `roe`, `operatingMargin`, `profitMargin`, `debtToEquity`, `earningsGrowth` |
| DELTAS (fundamental acceleration) | 4 | `delta_roe`, `delta_operatingMargin`, `delta_profitMargin`, `delta_earningsGrowth` |
| Region-specific 31st group | 1 | US: `relativeStrengthBreadth52w` (leadership). KR: `marketCap` (size). |

This is a **different construct** from: production's 4-factor `FACTOR_WEIGHTS`
(momentum .30 / value .25 / quality .25 / lowvol .20, 13 raw sub-inputs, see
§2), and the Opportunity radar's 28-column `FEATURE_COLUMNS` (19 level + 9
change features, see the research map). If "31 features" was intended to
mean something else, it was not found — this is the only construct in the
repository that produces that exact count, in either region.

`feature_manifest()`'s own `EXCLUDED` dict (`:36-42`) already withholds, with
reasons: `earningsYield`/`bookYield`/`fcfYield` →
`PER_SHARE_NUMERATOR_PRICE_BASIS_UNRESOLVED` (confirmed **still open today**,
§9); `fwdEarningsYield` → `HISTORICAL_CONSENSUS_UNAVAILABLE`; region-specific:
US `marketCap` → `MARKET_CAP_PIT_UNRESOLVED`; KR `fxBeta26w`/`absFxBeta26w` →
`FX_PUBLICATION_TIME_UNRESOLVED` (confirmed **not resolved, and reconfirmed
independently in this inventory**, §13).

---

## 2. Production alpha — the baseline every grade below is measured against

`pipeline/longterm.py:50`, `FACTOR_WEIGHTS = {momentum:.30, value:.25,
quality:.25, lowvol:.20}`. Raw sub-inputs (sector-neutral z, then blended):

| Sleeve | Weight | Raw inputs |
|---|---|---|
| momentum | .30 | `mom121` (12-1), `mom6` (6-month) |
| value | .25 | `earningsYield`, `fwdEarningsYield`, `bookYield`, `fcfYield` |
| quality | .25 | `roe`, `opMargin`, `profitMargin`, `earningsGrowth`, `−debtToEquity` (sector-exempt for Financials/Utilities/RealEstate/Holding) |
| lowvol | .20 | `−vol252` |

**Critical, non-obvious finding (verified by reading `longterm.py:221-262`
against `build.py:848` and `fundamentals.py`): the LIVE daily build's
value/quality/growth sleeve is fed from `fundamentals.py`
(Yahoo/yfinance, current-snapshot, explicitly no PIT history —
`fundamentals.py:9-14`, `longterm.py:35-39`). The PIT-safe DART/Finnhub
pipelines (`dart_fundamentals.py→dart_derive.py`,
`finnhub_fundamentals.py→finnhub_derive.py`) feed the identical
`score_cross_section` function, but only inside `historical_replay.py`'s
backtest/validation path — never the live site build.** "Used in alpha
scoring" therefore has two different, non-overlapping answers depending on
whether the question is about today's live score or the historical replay
that validates the model. Every row below states which applies.

Only `vol252` of the 13 raw sleeve inputs survives on the sealed signal
record (via `risk.vol252Pct`); every other raw sub-input is computed
internally and never persisted (`four-factor-signal-attribution-audit-v1`,
cited in the research map) — this is why subfactor-level re-analysis of
already-sealed history requires reconstruction from percentiles, not raw
values.

---

## 3. Price / trend / leadership

All items below reference `features.py` (ML feature engine, feeds the
short-term model and `risk.py`/`entry.py`, never `FACTOR_WEIGHTS`),
`longterm.py` (production sleeve), and `regional_alpha_features.py`
(research-only, unexecuted challenger).

| Feature | Status | Grade | Where |
|---|---|---|---|
| 1D/5D/21D/63D/126D/252D return | EXISTS_IN_CODE (21/63/126/252 research-only; 5/10/20/60d in ML features) | A | `regional_alpha_features.py:31`; `features.py:79-80` |
| 12-1 momentum | EXISTS_IN_CODE — **production factor**, live and replay | A | `longterm.py:73-77,235,288` |
| 6M momentum | EXISTS_IN_CODE — **production factor** | A | `longterm.py:80-84,236` |
| Benchmark-relative return | EXISTS_IN_CODE (`rel_momentum` ML feature; `relative{n}` research; `beta_to` production) | A | `features.py:110-115`; `longterm.py:125-136` |
| Relative momentum | EXISTS_IN_CODE, ML-feature/entry-gate only, not in FACTOR_WEIGHTS | B | `features.py:112`; `risk.py:33` |
| Distance from 52w high | EXISTS_IN_CODE (ML `price_52w_high`; reported `pct52wHigh`; research `high52Distance`) | A | `features.py:132`; `risk.py:35,76` |
| Moving averages 5-200 | EXISTS_IN_CODE, ML feature engine only | A | `features.py:66-68` |
| RSI (14, 28) | EXISTS_IN_CODE, RSI-14 also feeds risk/entry gating; not FACTOR_WEIGHTS | A | `features.py:21-26,83-84`; `entry.py:43` |
| MACD | EXISTS_IN_CODE, ML feature only — **no alpha-score consumer found** | A (feature already exists) | `features.py:86-91` |
| Bollinger | EXISTS_IN_CODE, ML feature only | A | `features.py:93-99` |
| Price acceleration | DATA_NOT_AVAILABLE as a named field; COMPUTABLE from stored closes | C (trivial build) | — |
| Momentum acceleration (20/60d) | EXISTS_IN_CODE — Opportunity radar only, not FACTOR_WEIGHTS | A | `opportunity.py:61-62`; `historical_replay.py:642-649` |
| Gap (overnight) | EXISTS_IN_CODE — entry-timing only (worst-of-10 sessions) | A | `entry.py:52-58` |
| Close-location-in-range | DATA_NOT_AVAILABLE by that name; COMPUTABLE (High/Low/Close all stored both regions) | C | — |
| Overnight vs intraday return | PARTIAL — only the overnight leg exists; intraday (open→close) not computed anywhere | C | `entry.py:52-58` |
| Trend persistence | DATA_NOT_AVAILABLE; COMPUTABLE from stored MAs/closes | C | — |
| Relative-strength breadth (52w) | EXISTS_IN_CODE, research-only, **US only**, never in production | B (unexecuted) | `regional_alpha_features.py:67,279` |
| Drawdown recovery speed | DATA_NOT_AVAILABLE (only point-in-time max-DD magnitude exists); COMPUTABLE | C | `longterm.py:117-122` |
| Breakout / failed breakout | DATA_NOT_AVAILABLE; COMPUTABLE (52w-high proximity + volume both stored) | C | — |

Independence: momentum/trend features as a family are **MOSTLY_REDUNDANT**
with each other (RSI vs short momentum; MACD vs MA-crossovers) but
**PARTIALLY_DISTINCT** from the production momentum sleeve where the
construction differs (acceleration-of-momentum vs level-of-momentum).
Horizon: VERY_SHORT to MEDIUM depending on window.

---

## 4. Volume / liquidity shock

**Only one volume-derived feature is actually computed anywhere in the
codebase: `volumeSurge` (5-day avg volume / 60-day avg volume),
`build.py:123-138`.** It feeds `entry.py:87` and the Opportunity radar
(`opportunity.py`), never `FACTOR_WEIGHTS`. The research-only matrix computes
the identical ratio under a different name (`volumeSurge5_60`,
`regional_alpha_features.py:34,245`) and also never reaches production.
`volumeSurgeDelta` (change in surge) exists only inside the Opportunity
radar's change features.

Raw daily `Volume` **is** stored for every session in both regions (Yahoo
OHLCV; KRX bars carry `ACC_TRDVOL`, `krx_prices.py:96,182-190`), so every row
below not already computed is graded **C** (computable from data already in
the canonical store, needs only feature-engineering code — no new vendor),
never E:

| Feature | Status | Grade |
|---|---|---|
| Volume / 20D avg | COMPUTABLE (only the 5D/60D pair is actually computed) | C |
| Volume / 60D avg (standalone) | COMPUTABLE (exists only as the denominator of 5/60) | C |
| Volume 5D/20D | COMPUTABLE | C |
| Volume 5D/60D | **EXISTS_IN_CODE** | A |
| Volume z-score / percentile | COMPUTABLE (`longterm._percentile` machinery exists, never applied to volume) | C |
| Dollar volume (거래대금) | COMPUTABLE (Close × Volume both stored) | C |
| Dollar-volume / market cap (turnover) | COMPUTABLE (market cap stored separately) — **do not confuse with `turnoverPct` elsewhere in the repo, which means portfolio rebalancing turnover, an unrelated quantity** | C |
| Dollar-volume shock, shock persistence | COMPUTABLE | C |
| 1-day vs multi-day accumulation | COMPUTABLE | C |
| Volume-up+price-up / down / flat | COMPUTABLE | C |
| Volume-price divergence | COMPUTABLE | C |
| Close-near-high / low after high volume | COMPUTABLE (needs High/Low/Close/Volume, all stored) | C |
| Abnormal-range × volume, gap × volume | COMPUTABLE | C |
| Market-/sector-adjusted volume shock | COMPUTABLE (sector map exists, `sectors.py`) | C |
| Liquidity acceleration | COMPUTABLE | C |

**Economic caveat carried forward from this inventory's own instructions,
stated without any return measurement:** collapsing volume shock to a
percentile rank alone can lose the distinction between a 2x and a 15x
volume day — the ordinal position may be similar while the economic event
is not. A raw or log-magnitude representation kept alongside the percentile
preserves that distinction; which representation to use is a construction
choice for the next study, not something this inventory decides.

Independence: volume/liquidity as a family is **HIGHLY_DISTINCT** from the
production sleeves (nothing in FACTOR_WEIGHTS touches volume at all) and
**PARTIALLY_DISTINCT** from the Opportunity radar's existing
`volumeSurge`/`volumeSurgeDelta` (same base ratio, but percentile-only,
never magnitude-preserving — see the research map's note on
`entry_state_incidence`-style overlap). Horizon: VERY_SHORT to SHORT_MED.

---

## 5. Market microstructure

**Confirmed: no true bid/ask, order-book, or intraday tick data source
exists anywhere in this repository.** Every price source
(`fundamentals.py`/yfinance, `korea_prices.py`/FinanceDataReader,
`krx_prices.py`/KRX Open API) is end-of-day OHLCV only. Grep for
bid/ask/tick/order-book/Level-2 across `pipeline/` returns no genuine hits.

| Feature | Status | Grade |
|---|---|---|
| Amihud illiquidity | COMPUTABLE_FROM_DAILY_OHLCV | C |
| Turnover (vol/shares out, $vol/mktcap) | COMPUTABLE (listed shares already stored) | C |
| Dollar volume | COMPUTABLE | C |
| Bid-ask spread proxy | **NOT_CURRENTLY_AVAILABLE** — no true spread; a High-Low proxy is not the same quantity | E (true spread) / C (High-Low proxy only) |
| High-low spread proxy | COMPUTABLE | C |
| Realized range | COMPUTABLE | C |
| Overnight gap | EXISTS_IN_CODE (entry-timing use only) | A |
| Intraday reversal proxy (Open vs Close) | COMPUTABLE | C |
| Zero-return days | COMPUTABLE, but note KRX's own suspension-day filter already **removes** zero-volume rows before this could be measured — would need the raw pre-filter rows (`krx_prices.py:257-264`) | C (with a caveat) |
| Price impact proxy | NOT_CURRENTLY_AVAILABLE in the true (trade-level) sense; a volume-scaled range proxy is computable | E (true) / C (proxy) |
| Volume-weighted price proxy (VWAP-like) | NOT_CURRENTLY_AVAILABLE as true VWAP; a crude OHLC-average proxy is computable | E (true) / C (proxy) |

No fake precision: anything requiring genuine intraday/tick data is graded
E outright. Horizon: VERY_SHORT.

---

## 6. Fundamental level

| Field | US source | KR source | PIT `availableFrom`? | Coverage note | Used today? |
|---|---|---|---|---|---|
| Revenue | `finnhub_derive.py` | `dart_derive.py` | Y both | KR dark 2013-14 (DART serves from 2015) | Live: N. Replay: Y (via margins) |
| Revenue growth | Collected raw (`fundamentals.py:30`) only | Not modeled | N/A | — | **N anywhere** — collected, never read by `longterm.raw_inputs` |
| EPS | `epsTtm` both derive modules | Y | Y | Same | Replay only; live uses Yahoo trailing/forward PE instead |
| Earnings growth | Y both | Y | Y | Same | **Y live** — production quality-sleeve input |
| Operating income (level) | Raw account both | Y | Y | Same | Replay only as level; live uses the ratio |
| Operating margin | Y both | Y | Y | Same | **Y live** — production quality-sleeve input |
| Net income (level) | Raw account both | Y | Y | Same | Replay only as level |
| Profit margin | Y both | Y | Y | Same | **Y live** — production quality-sleeve input |
| ROE | Y both | Y | Y | Same | **Y live** — production quality-sleeve input |
| ROA | **Not computed anywhere, either region** | — | — | — | N |
| Debt (level) | Raw (Assets−Equity or Liabilities chain) | Y (부채총계) | Y | Same | Replay only as level; **never exposed standalone in the derived output**, only the ratio survives |
| Debt/equity | Y both | Y | Y | Same | **Y live** — production leverage penalty (sector-exempt) |
| Cash (balance-sheet) | **Not collected either region** (only operating cash FLOW is) | Not collected | N/A | — | N |
| Operating cash flow | Y both | Y (with income-vs-cashflow column semantics resolved, `dart_derive.py:8-31`) | Y | Same | Replay only, intermediate for FCF |
| Free cash flow | Derived both regions | Y | Y | Same | Replay only via `fcfYield`; live uses Yahoo `fcfYield` instead |
| Assets (level) | Y both | Y (자산총계) | Y | Same | Replay only as level, not exposed standalone |
| Equity (level) | Y both | Y (자본총계) | Y | Same | Replay only, feeds ratios |
| Shares (with carry-forward basis) | Y (25.3% filings omit) | Y (rising Q1/Q3 omission since 2022, carried forward) | Y | Documented carry-forward discipline both regions | Replay only |
| Book value / share | Y both | Y | Y | Same | Replay only via `bookYield`; live uses Yahoo `priceToBook` |
| Valuation numerators (EPS/BVPS/FCF per share, PIT) | Y both | Y | Y | Value sleeve reported separately from quality (needs shares) | **Replay only — never reaches the live daily score** |

Grade for the whole group: **A for the raw collection mechanism itself**
(DART/Finnhub PIT pipelines are already built, tested, and sealed into
replay-v16); **B for the fact that the live build does not use them** — this
is a repairable lineage/wiring gap, not a missing-data gap.

Independence: **MOSTLY_REDUNDANT** with the production quality/value sleeves
by construction (this IS where those sleeves' values come from in the
replay path).

---

## 7. Fundamental acceleration / change

Already researched — see the research map for the full result
(`fundamental-acceleration-discovery-v1`, CASE D — no discovery evidence, at
64.95% pooled coverage, |ρ|=0.118 to Quality-level). Listed here only for
completeness of the raw-material inventory, not as an open item:

| Candidate | Status |
|---|---|
| Filing-over-filing ROE/opMargin/profitMargin/earningsGrowth acceleration | **ALREADY_TESTED** — `fundamental_acceleration.py` (shared PIT resolver), scored in `fundamental_acceleration_discovery.py` |
| Sales growth acceleration | NOT_FEASIBLE_DATA_MISSING — no revenue-acceleration field derived (revenue itself is collected, but growth/acceleration on it is not modeled anywhere) |
| Margin expansion (level, not acceleration) | Same raw fields as tested acceleration; a level-based variant was **not** the tested construction |
| Multi-quarter persistence of any acceleration signal | NOT TESTED — `fundamental_acceleration_discovery.py` uses only the single most-recent consecutive filing pair, never a longer persistence window |

---

## 8. Accounting quality (largely unused group)

Feasibility judged strictly on raw fields actually present in
`dart_fundamentals.WANTED_ACCOUNTS` and `finnhub_derive`'s
FLOWS/EQUITY/LIABILITIES/ASSETS/SHARE_COUNTS chains — never assumed from
what would be logical to have.

| Candidate | Status | Grade |
|---|---|---|
| Operating cash flow / net income | **FEASIBLE** | B (raw exists, not derived as a field) |
| FCF / net income | **FEASIBLE** | B |
| Accruals (NI − OCF, scaled) | **FEASIBLE** | B |
| Receivables growth vs revenue growth | **NOT_FEASIBLE_DATA_MISSING** — no receivables line collected either region | E |
| Inventory growth vs revenue growth | **NOT_FEASIBLE_DATA_MISSING** | E |
| Asset growth | **FEASIBLE** (level collected, growth is a level diff) | B |
| Debt growth | **FEASIBLE** (level collected but not exposed standalone in derived output today — needs a schema addition, not a new source) | B |
| Share dilution / share-count change | **FEASIBLE** (carry-forward basis already tracked) | B |
| Gross margin stability | **NOT_FEASIBLE_DATA_MISSING** — no COGS/gross-profit line collected | E |
| Operating margin stability (variance) | **FEASIBLE** (multiple periods per ticker already stored) | B |
| Cash conversion | **FEASIBLE** | B |
| Working-capital deterioration | **NOT_FEASIBLE_DATA_MISSING** — no current-assets/liabilities/receivables/inventory/payables collected | E |
| Capex intensity (capex/revenue) | **FEASIBLE** (capex and revenue both collected) | B |

Independence: **HIGHLY_DISTINCT** from the current quality sleeve (which
measures profitability levels, not cash-flow-vs-earnings quality or balance
sheet growth) — this is the single largest genuinely-unused-but-feasible
group found in this inventory.

---

## 9. Valuation

| Feature | Status | file:line | Grade |
|---|---|---|---|
| Earnings yield | EXISTS_IN_CODE (live: trailing PE; PIT: epsTtm) | `longterm.py:208-218,238` | A (live) / B (PIT, unresolved basis — see below) |
| Forward earnings yield | EXISTS_IN_CODE, live only — PIT has no forward-consensus analog, explicitly `HISTORICAL_CONSENSUS_UNAVAILABLE` in research matrix | `regional_alpha_features.py:41` | A (live) / E (PIT) |
| Book yield | EXISTS_IN_CODE, live: Yahoo `priceToBook`; PIT: `bookValuePerShare` — flagged `PER_SHARE_NUMERATOR_PRICE_BASIS_UNRESOLVED` | `pit_data.py:499` | A (live) / B (PIT, open issue) |
| FCF yield | Same pattern | `pit_data.py:500` | A (live) / B (PIT, open issue) |
| EV/EBITDA | **NOT_FEASIBLE** — no EBITDA or enterprise-value computation anywhere | — | E |
| Sales yield (P/S inverse) | **NOT_FEASIBLE** — no field found despite revenue being collected | — | E |
| Valuation percentile | EXISTS_IN_CODE | `historical_replay.py:610` | A |
| Valuation change (delta) | Only the blended `alphaPercentileDelta` exists; no standalone `valuePercentileDelta`, though a per-date `valuePercentile` is already stored so this is a downstream computation, not new collection | — | C |
| Own-history valuation | NOT_FEASIBLE for the live path (no persisted history); COMPUTABLE from the PIT replay ledger, not currently coded | — | C |
| Sector-relative valuation | EXISTS_IN_CODE — this is literally how the value sleeve is built | `longterm.py:152-171,289` | A |

**`PER_SHARE_NUMERATOR_PRICE_BASIS_UNRESOLVED` — verified current status:
still present, still open, real code path, not stale documentation.** Grep
confirms it exists today only in `regional_alpha_features.py:38-40`,
excluding `earningsYield`/`bookYield`/`fcfYield` from the research-only
matrix because the price to divide the PIT per-share numerator by (which
close, which date, which currency basis) has not been settled. No other
module references this literal string; it is not resolved anywhere else in
the codebase.

---

## 10. Analyst expectations / market consensus

| Item | US | KR |
|---|---|---|
| EPS/revenue estimates, revisions, dispersion | **Grade D — PAID_OR_LICENSED.** Finnhub free-tier endpoints (`recommendation-trends`, `price-target`, `company-eps-estimates`) exist but read as current-snapshot or shallow rolling-window products — no confirmed `from`/`to` historical query, and two independently-surfaced sources disagree on retention (~4 months vs 12-24 months), neither a stable 2013–2026 PIT panel. `price-target` returns only a single latest-consensus object, no history. Finnhub maintains a **separate paid pricing page specifically for "stock estimates,"** corroborating the repo's own prior design-doc suspicion (`docs/us-alpha-research-design-v1.md`) rather than overturning it. | **Grade E.** `docs/challenger-2-signal-source-feasibility-v1.md` already found the Korean analyst-consensus equivalent (FnGuide/FnSpace) ToS-blocked for building a persistent database at all — a harder block than a cost problem. Not re-tested here; accepted as authoritative. |
| Earnings surprise | Bundled with the above — same D grade, same reasoning | Same E |
| Recommendation changes | `recommendation-trends` exists but same shallow-window caveat | Same E |

No free, official (SEC/FRED-tier) route exists for either region because
analyst estimates are private brokerage output, not government-filed data —
this is a structural, not a collection, limitation.

---

## 11. Earnings / corporate events

| Sub-event | Official free PIT source | Grade | Notes |
|---|---|---|---|
| Earnings announcement date | SEC EDGAR 8-K Item 2.02, filing-accepted timestamp, since 2001/2004 | **C** | Blocked today by the SEC domain-wide 403 already proven in AGENTS.md's Vendor refusal invariants (v2.9) and two dedicated docs; `historical_replay.py:382-386,987-990` already documents this exact gap in production (`knownDeviationsFromProduction`: `earnings_calendar_unavailable_event_risk_branch_inactive`) |
| M&A, material agreements, guidance, buybacks | SEC 8-K Items 1.01/2.01/7.01/8.01 | **C** | Same access path; content is unstructured free text — needs NLP/keyword extraction on top, materially higher build complexity than a structured field |
| Stock splits | Already reflected in the existing as-traded/total-return price series (`price_adjustment.py`); a discrete announcement-date signal would need SEC 8-K Items 3.03/5.03 | **A** (return impact already handled) / **C** (discrete event signal) | |
| Dividend changes (increase/cut/initiation) | **Already partially collected, unusually.** `finnhub_fundamentals.py`'s `UNIT_ANCHORS[PER_SHARE]` already includes `CommonStockDividendsPerShareDeclared` — the raw per-filing dividend-per-share figure is already sitting in the PIT store this repo has already backfilled (replay-v15+) | **B — REPAIRABLE/immediately buildable** | The single most favorable, lowest-effort finding in this whole category: no new vendor, only a new derived field |
| Credit rating changes | No free official historical source found; NRSRO ratings are proprietary vendor output | **D/E** | Paid vendors (Bloomberg, Refinitiv, raters' own feeds) are the only route found |

Overall category grade if forced to one letter: **C**, dragged there by the
shared SEC-access blocker, with one genuinely bright spot (dividend changes,
B) and one genuinely closed one (credit ratings, D/E).

---

## 12. Investor flow — Korea (priority group)

| Item | Grade | Stock-level? | Basis |
|---|---|---|---|
| Per-stock investor-type net buying (외국인/기관 7종/개인, incl. 프로그램매매) | **B — REPAIRABLE** | Yes | Real, free, official (KRX Data Marketplace "투자자별 매매(개별종목)"; the `pykrx` library's documented mechanism confirms the schema). **Not** behind this repo's currently-subscribed KRX Open API key (`sto/stk_bydd_trd` only) — the mechanism is KRX's public statistics loader (`data.krx.co.kr/comm/bldAttendant/getJsonData.cmd`), which this repo's own `scripts/probe_krx_index_membership.py` already found returns HTTP 400/`LOGOUT` and is reported outside this sandbox's network allowlist. PIT-safe: same-day, end-of-trading, no restatement mechanism. Per-stock 차익/비차익 program-trading split not independently confirmed. Historical depth back to 2013 not independently confirmed within this task's no-bulk-download constraint. |
| Short-selling volume/value + net short balance (개별종목 공매도) | **B — REPAIRABLE**, with a hard regime-stability caveat | Yes | Same connectivity mechanism/blocker as above (`short.krx.co.kr`, same public portal family). **Regime instability confirmed**: full-market short-selling bans ~2020-03 to 2021 (exact end date disputed across sources, ~2021-05) and 2023-11-05 to 2025-03-31 (high-confidence, multi-source corroborated, paired with a structural NSDS reporting overhaul). Any factor built on this spans at least three regimes where the variable is either illegal-to-observe or measured under a materially different microstructure. |
| Large-holdings disclosure (대량보유 상황보고, 5%-rule equivalent) | **B — REPAIRABLE, lowest-effort build in this whole inventory** | Yes | **Same vendor, same key, same receipt-date PIT pattern already proven** by `dart_fundamentals.py`. OpenDART's own developer guide documents a dedicated API group (`DS004`, 지분공시 종합정보) with `rcept_no`/`rcept_dt` fields — the identical mechanism `dart_fundamentals.py`'s `receipt_date()` already parses. Not currently collected (confirmed: no `majorstock`-family call exists anywhere in the repo). |
| Foreign-ownership-limit history | **D/E-leaning, not confirmed researchable** | Yes (per-stock ceiling) | General regulatory framework found; no specific historical, machine-readable dataset of per-stock ownership-ceiling levels over time identified |
| KSD (Korea Securities Depository) as an independent source | **E** | — | Institutional description only; no KSD-specific open dataset for investor-behavior history identified; the actual mechanism for large-holdings data is DART/FSS, not KSD |

---

## 13. Investor flow / behavior — United States

| Item | Grade | Basis |
|---|---|---|
| 13F institutional holdings | **A — already in repo, but confirmed unused in alpha scoring** (`institutional_13f.py`; sole consumer is a UI dict key, `build.py:997,1118`) | Small explicit manager watchlist, up to 45-day filing lag, no cash/shorts/derivatives — coverage too sparse (a handful of managers) to backfill a 60-500 name cross-section even if wired in |
| Form 4 insider transactions (buy/sell, cluster buying, dollar value, role) | **C — ACQUIRABLE** (data-existence, not data-blocked) | SEC's own flattened structured extraction (`sec.gov/data-research/sec-markets-data/insider-transactions-data-sets`), quarterly TSV, **Jan 2006–present**, free, public domain. Fields (per WebSearch-surfaced schema, not independently byte-verified due to the SEC block): `ACCESSION_NUMBER`, `TRANS_DATE`, `TRANS_CODE`, `TRANS_SHARES`, `TRANS_PRICEPERSHARE`, role flags in a `REPORTINGOWNER` table. Blocked by the same SEC domain-wide 403 already proven in AGENTS.md; no free non-SEC re-server found (paid re-servers like `sec-api.io` exist, layered on the same filings). CIK↔ticker mapping needed (known-shape, repo already does this for the 13F registry, but non-trivial at universe scale). |
| Short interest (FINRA/Nasdaq/NYSE) | **C — ACQUIRABLE** | Two distinct free official channels: FINRA's consolidated catalog (Rule 4560, twice-monthly) and Nasdaq's own `nasdaqtrader.com` short-interest page (WebSearch snippet claims exchange-listed coverage since **2007**). One unresolved ambiguity across sources on whether FINRA's *consolidated* product covers OTC-only before 2021 vs exchange-listed data existing natively since 2007 via Nasdaq/NYSE's own pages — flagged as needing a live check, not adjudicated here. PIT correction needed: report is dated to a settlement date but published ~7-10 business days later; must record the **publication** date as `availableFrom`, exactly the same discipline `institutional_13f.py` already implements for report-date-vs-filing-date. Ticker-level directly, no CIK remapping needed. |
| Options data (implied vol, put/call ratio, unusual activity), per-equity, historical | **E — NOT_RESEARCHABLE_NOW** | CBOE publishes free market/index-level put/call ratios only; CBOE's own DataShop sells per-security historical options data as a **paid** product, confirming no free official per-equity route; third-party aggregators cap free depth at ~2 years or are non-Tier-1 |

---

## 14. Sector / industry context

| Item | Status | Grade |
|---|---|---|
| Current sector map + leverage-exemption list | EXISTS_IN_CODE, production, load-bearing | A (`sectors.py`, `longterm.py:233,293,296`) |
| Historical sector membership/classification changes | Not found anywhere in the repo as a dated/point-in-time map | E — no evidence of a backfillable point-in-time sector history; using today's classification for the whole 2013–2026 window would be exactly the kind of backfill this repository's PIT discipline forbids |
| Sector rotation (ETF-based RRG) | EXISTS_IN_CODE, `rotation.py`, **descriptive dashboard panel only**, never feeds `longterm.py`/`kelly_portfolio.py`/`opportunity.py` | A (exists) / not used in scoring |
| Sector rotation (member-median relative-momentum proxy) | EXISTS_IN_CODE, feeds the Opportunity radar's `sectorRotationImproved` feature only, explicitly disclaimed as a proxy distinct from `rotation.py`'s ETF-based read | A (exists, narrow use) |
| Sector-relative valuation/momentum percentiles | EXISTS_IN_CODE — this is how the production sleeves are already built | A |
| Intra-sector dispersion, sector leadership persistence, sector breadth | DATA_NOT_AVAILABLE as named fields; COMPUTABLE from the existing sector map + price history | C |

---

## 15. Market breadth / dispersion

| Item | US | KR |
|---|---|---|
| % above 200D/50D MA | **EXISTS_IN_CODE**, feeds `sentiment.py`'s fear/greed index, with the previously-known `None`-vs-`0.0` measurement-absence bug **now confirmed fixed** (denominator restricted to measurable names, both share and denominator published) | Same mechanism, same fix confirmed |
| Median cross-sectional momentum | EXISTS_IN_CODE, `sentiment.py` | Same |
| New highs / new lows | DATA_NOT_AVAILABLE as a named field; COMPUTABLE from stored universe price history | Same |
| Cross-sectional return dispersion / avg correlation | DATA_NOT_AVAILABLE; COMPUTABLE | Same |
| Equal-weight vs cap-weight divergence, top-10 concentration | DATA_NOT_AVAILABLE; COMPUTABLE (market caps already stored) | Same |
| Small vs large / cyclical vs defensive leadership | DATA_NOT_AVAILABLE; COMPUTABLE via existing sector map | Same |
| Breadth thrust | DATA_NOT_AVAILABLE; COMPUTABLE | Same |

Grade for the family: **C** (all computable from data already in the
canonical store; none currently coded beyond the two MA-breadth figures
already inside `sentiment.py`).

---

## 16. Macro / regime — United States

Production's 6-axis regime engine (`regime.py:75`: growth, inflation,
liquidity, financialConditions, riskAppetite, earningsCredit) is built
**entirely from US-domiciled/US-priced series** — all 21 `INDICATORS`
entries are FRED or CBOE (`regime.py:38-68`). Confirmed by
`docs/regional-alpha-research-separation-v1.md:171-181`: accurately
described as `US_GLOBAL_REGIME`, not a Korean regime.

| Indicator | Axis | Source | Fetch? | PIT/vintage | Used in production score? |
|---|---|---|---|---|---|
| CFNAI, Payrolls, Unemployment, Initial Claims | growth | FRED | Y | REVISED_HISTORY (no series is opted into ALFRED vintaging — `config.json` `macroVintageSeries: []` is empty) | Y |
| CPI, Core CPI, Core PCE (PPI pair is context-only, excluded from axis avg) | inflation | FRED | Y | REVISED_HISTORY | Y (CPI/Core CPI/Core PCE); PPI context-only |
| Breakeven 10Y, WTI | inflation | FRED | Y | REVISED_HISTORY (market-priced) | Y |
| Fed Assets, RRP, TGA, M2 | liquidity | FRED | Y | REVISED_HISTORY; **permanently unreachable for ALFRED vintaging** per AGENTS.md's Macro vintage invariants (v2.9) for several of these; TGA specifically flagged as a redefined series (1,408 vintage periods to 2013 vs 524 today) | Y |
| NFCI, ANFCI, HY spread, IG spread, Real 10Y, Broad Dollar | financialConditions | FRED | Y | REVISED_HISTORY | Y |
| VIX | riskAppetite | CBOE via Yahoo | Y | not FRED-sourced, not vintaged (n/a) | Y |
| Yield curve (10Y−2Y) | earningsCredit | **Derived** (`pit_data.DERIVED_MACRO_COLUMNS`) | Y (recomputed from inputs) | Recomputed from vintaged inputs when available | Y |
| FedFunds (DFF) | — | FRED | Y (fetched into panel) | REVISED_HISTORY | **NO — collected but never read by `regime.py`'s INDICATORS**, display-only in `macro.py`. Documented explicitly in `docs/regional-alpha-research-separation-v1.md:191-196`. |

AGENTS.md's Macro vintage invariants (v2.9) already conclusively closed the
ALFRED-vintaging question — **10 of 28 panel columns have no ALFRED
vintages at all**, and this is permanent by the vendor's own answer, not a
collection gap. Not re-tested here; cited as authoritative and settled.

---

## 17. Macro / regime — Korea

**ECOS fetch layer confirmed 100% dead code.** Exhaustive grep across
`pipeline/*.py` for "ecos" (case-insensitive) finds only config plumbing
(`config.py`, `macro.py`, `regime.py`, `kelly_portfolio.py`, `build.py`)
feeding a single boolean diagnostic flag (`build.py:1145`:
`"ecosEnabled": cfg.has_ecos`). **There is no HTTP fetch function anywhere
that calls `ecos.bok.or.kr`.** `datafeed.py` has exactly one macro fetch
function, `fetch_macro`, and it iterates `cfg.fred_series` only, never
`cfg.ecos_regions`. Confirmed independently by two agents in this inventory,
converging with two prior design docs
(`docs/kr-macro-regime-design-v1.md`, `docs/regional-alpha-research-separation-v1.md`)
that already stated this — this inventory verifies it in the current code
rather than trusting the docs' word.

| ECOS series in `config.json` | What it plausibly is (secondary-source only — not primary-verified, no `ECOS_API_KEY` in this sandbox) | Grade |
|---|---|---|
| `722Y001` (BaseRate) | 시장금리 table; item `0101000` commonly cited as BOK base rate | C |
| `817Y002` used for **both** `KTB_3Y` AND `CorpBond_3Y`| **Confirmed real ambiguity, independently corroborated, not fixed here.** Multiple secondary sources describe `817Y002` as a single broad "시장금리(일별)" table bundling 국고채(3/5/10/20/30y)/회사채(AA-,3y)/CD(91일) rates, distinguished only by `item_code1`–`item_code4` — a hierarchical sub-key `config.json`'s `ecos.KR` schema has **no field for at all**. Even if a fetch function existed today, it could not currently distinguish these two series from config alone. | C, with an open item-code ambiguity blocking use even after the fetch layer is built |
| `901Y009`/`901Y010` (CPI/Core CPI) | High-confidence per multiple sources | C |
| `901Y033` (Industrial Production) | Plausible | C |
| `901Y067` (LeadingIndex) | Described as a composite coincident/leading index family, exact identity not pinned down | C |
| `901Y011` (Exports) | Plausible | C |
| `101Y004` (M2) | Plausible | C |

All: **market/macro-level only, never stock-level** — none of these would
feed a per-ticker score directly, per this repo's own architecture
(macro never adds to single-stock alpha, per
`regional-alpha-research-separation-v1.md`).

| Additional KR macro source | Grade | Note |
|---|---|---|
| KOSIS (retail sales, CSI, BSI, employment detail, export detail e.g. semiconductors) | **C** | Free registration confirmed via KOSIS's own developer portal and community wrappers; series-by-series depth not independently verified |
| FSC/FSS regulatory data (beyond DART large-holdings, §12) | Mixed, see §12 | — |

---

## 18. FX exposure — Korea

**`fxBeta26w`/`absFxBeta26w` exclusion reconfirmed as still open, and found
to have gotten *more* certain, not less, since the earlier design doc.**
`docs/kr-alpha-research-design-v1.md` (pre-registration, before the feature
matrix was actually built) had said FX-beta's PIT semantics "pass, cleanly."
The superseding, actually-built research matrix
(`regional_alpha_features.py:88`) **excludes** it with reason
`FX_PUBLICATION_TIME_UNRESOLVED` — a stricter, more current verdict.

Two distinct sources answer the "clean daily-close timestamp aligned to the
KRX close" question differently:

1. **FRED `DEXKOUS`** (already fetched, display-only, `macro.py`) — a
   **noon-New-York** buying rate. Noon US-Eastern is ~1-2am the *next* KST
   calendar day. **Confirmed mismatched** to the 15:30 KST close a same-day
   FX-beta regression would need. Grade **A for access**, but the wrong
   series for this specific question — access is not the problem here.
2. **BOK ECOS `731Y001`** (매매기준율, Korea-domestic-market-timed,
   announced by 서울외국환중개) — a better-timed candidate per secondary
   sources, but its exact announcement time relative to the KRX close was
   **not independently confirmed live**, and it sits behind the same dead
   ECOS fetch layer as §17. Grade **C**, contingent on both the ECOS build
   and a live timing confirmation.

Stock-level only via the `fxBeta` derived construction, which remains
unimplemented; market-level (regime input) grade is the same as the ECOS
family above.

---

## 19. Commodity / global factor exposure (price-based rolling betas)

Not separately built anywhere in the repo. Economically defensible
candidates (oil, copper, gold, SOX, broad USD, US rates, a China proxy) are
all **COMPUTABLE_FROM_AVAILABLE_DATA** in principle (all are liquid,
free-to-fetch price series; `indices.py` already fetches several — SOX,
gold futures, dollar index, VIX — for display purposes only, never as a
stock-level beta input). Grade **C**. This inventory does not enumerate a
long list of candidate betas — per this study's own instruction, only
economically-explainable exposures are worth building, and none has been
built yet, so there is nothing "already tested" to report here; that
selection judgment belongs to whichever future study proposes a specific
name-level exposure and its rationale.

---

## 20. Alternative attention / sentiment

`pipeline/sentiment.py` is **not** news or search sentiment. Confirmed by
reading the module: it is a purely price/breadth/macro-derived per-region
"Fear & Greed"-style score (breadth above 200D/50D MA, %-Bull regime share,
median 63-day momentum, plus region-specific market gauges — VIX/HY
spread/yield-curve sign for US; USD/KRW level+change and the KR 10Y-3M curve
sign for KR). No news article, headline, or search-trend data is read
anywhere in this file or anything it calls.

**The specific `AGENTS.md` Measurement-absence defect (v2.11: 200-day
breadth publishing 0% instead of `None` when the cross-section had nothing
measurable) is confirmed FIXED in the current code** — the denominator is
restricted to measurable names, absence returns `(None, 0)` not `(0.0, 0)`,
every score component is guarded (`if breadth200 is not None: ...`), and the
output now publishes the denominator (`breadth200MeasuredNames`,
`universeNames`, `unmeasuredComponents`) alongside the share.

Genuine news/search/attention data (Google Trends, Naver DataLab, Reddit,
StockTwits, Wikipedia views) is **not implemented anywhere** in this repo.
Not independently probed live in this inventory (out of the priority
clusters assigned); provisional grade **C for existence of a free API**
(Google Trends and Naver DataLab both have free, keyless or
low-friction APIs) but **D/E-leaning for reliable historical PIT and
survivorship** — these products are widely known to have retroactive
smoothing/normalization behavior that is difficult to reconstruct
point-in-time; a dedicated feasibility check (schema + revision behavior)
would be needed before any grade firmer than C could be assigned, and this
inventory did not run one.

---

## 21. Expert / house view

`expert_consensus.py` produces a **theme-level** (e.g. "AI/Semiconductors,"
"Korea"), human-curated stance/dispersion/institution-count panel — never
per-ticker. Confirmed zero code path into any alpha-scoring module
(`longterm.py`, `opportunity.py`, any challenger study) — sole consumer is a
UI dict key. Not classifiable as an Alpha backtest feature (no ticker field
exists in its schema, and no historical time series is retained); it is a
macro/qualitative-overlay candidate at best, and even there has no
historical dataset to validate against. Grade **E for Alpha-backtest use**;
not graded for its existing UI-panel use, which is out of scope.

---

## 22. National pension / asset allocation

`national_pension.py` is confirmed **aggregate fund-wide asset-class
allocation only** (국내주식/국내채권/해외주식/해외채권/대체투자/단기자금
weights) — no per-ticker or per-manager breakdown exists in this feed.
Structurally cannot become a stock-level alpha input without an entirely
different, unbuilt name-level NPS holdings source (which is not this
module's job — 13F covers the closest analog for a *subset* of US names, at
too-sparse coverage to matter, per §13). Grade **E for stock-level use**;
not a substitute for, and not to be confused with, the KRX investor-flow
data in §12 which IS per-stock.

---

## 23. Master "collected but currently unused in alpha scoring" table

Alpha-scoring path defined as `longterm.score_cross_section` and its direct
callers (`build.py` live, `historical_replay.py` replay, and any challenger
study that imports it directly). `opportunity.py`/`trade.py` are a
*different* scoring surface (short-term ML radar / trade engine) and are
called out separately where relevant.

| Dataset | Module | Collected? | Used in alpha scoring? | Reason if unused | Notes |
|---|---|---|---|---|---|
| SEC 13F stock-level holdings | `institutional_13f.py` | Y | **N** | Module's own docstring: "a disclosure reader, not an investment signal" — deliberate | UI panel only |
| NPS asset-allocation weights | `national_pension.py` | Y | **N** | Aggregate-only, no ticker field | UI panel only |
| Expert/house-view consensus | `expert_consensus.py` | Y | **N** | Theme-level, no ticker mapping exists | UI panel only |
| `revenueGrowth` | `fundamentals.py:30` | Y (every build) | **N** | Not stated in code — simply never read by `longterm.raw_inputs` | Genuinely unused field inside an otherwise-used module |
| `dividendYield` | `fundamentals.py:34` | Y | **N** | Same | Same |
| MACD, Bollinger, RSI-28, most VIX/macro-stress ML features | `features.py` | Y (computed every build) | **N for FACTOR_WEIGHTS** | Different model's (short-term ML) feature set by construction | `risk.py`/`entry.py` read a narrower slice of the same frame for regime/entry gating |
| DART/Finnhub PIT fundamentals (full sleeve) | `dart_derive.py`, `finnhub_derive.py` | Y | **Replay-only; N for the live daily score** | Explicit design note (`longterm.py:35-39`): live uses Yahoo current-snapshot instead | The single most consequential "used-but-not-where-you'd-assume" finding in this inventory |
| Raw debt/asset/equity levels inside PIT derive modules | `dart_derive.py`, `finnhub_derive.py` | Y (held as intermediate values) | **N** — never exposed in the output `fields` dict, only the ratio survives | Not a missing-data gap — a missing-field-exposure gap | Blocks debt-growth/asset-growth factors without extra derivation work, not without new collection |
| KRX dated universe/market-cap snapshots | `krx_universe.py` | Y | **Partial** — feeds historical replay's PIT-correct KR universe; **not** used for the live daily universe (which resolves dynamically from today's FDR listing) | Live build has no need for a dated snapshot | Already the mechanism behind the KR survivorship fix in replay-v16 |
| `sec_access.py` classifier | `sec_access.py` | N/A (utility) | **N** | Diagnostic tool for vendor-refusal probes only, never imported by any collector or the replay chain | QA/ops tooling |

---

## Files read to build this map (for reference)

`pipeline/longterm.py`, `regional_alpha_features.py`, `regional_alpha_model.py`,
`opportunity.py`, `historical_replay.py`, `build.py`, `fundamentals.py`,
`features.py`, `quality.py`, `risk.py`, `trade.py`, `entry.py`, `universe.py`,
`universe_lists.py`, `replay_valuation.py`, `sec_access.py`,
`price_adjustment.py`, `institutional_13f.py`, `national_pension.py`,
`expert_consensus.py`, `sectors.py`, `krx_universe.py`, `krx_prices.py`,
`korea_prices.py`, `dart_fundamentals.py`, `dart_derive.py`,
`finnhub_fundamentals.py`, `finnhub_derive.py`, `sentiment.py`, `regime.py`,
`macro.py`, `datafeed.py`, `rotation.py`, `regional_rotation.py`,
`indices.py`, `direction.py`, `pit_data.py`, `provenance.py`; `config.json`;
`requirements.txt`; `AGENTS.md`; and the `docs/*.md` design/evaluation files
named throughout. No file was modified in the production of this map.
