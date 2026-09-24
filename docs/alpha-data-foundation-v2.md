# Alpha data foundation v2

> **Data foundation only. No Alpha model is trained. No feature is
> correlated with future returns. No new historical discovery is
> performed.** No `FACTOR_WEIGHTS`, CHAMPION, selector, Kelly parameter,
> entry rule, region cap, or macro multiplier is changed. Nothing in this
> document, or in any module it describes, is imported by
> `pipeline/longterm.py`, `pipeline/opportunity.py`,
> `pipeline/kelly_portfolio.py`, or `pipeline/build.py`.

Companion documents: `docs/alpha-research-philosophy-v2.md` (governance),
`docs/alpha-research-foundation-v2-errata.md` (the `regional-alpha-model-v1`
correction), `docs/alpha-data-foundation-v2-sector-context.md` (sector
investigation), `docs/guru-decision-atlas-data-v1.md` (the separate 13F
track), `docs/results/alpha-data-foundation-v2.json` (machine-readable).

---

## What this PR corrects

`alpha-information-inventory-v1` stated `regional-alpha-model-v1` had never
been executed. It had — on 2026-09-23, closing both regions at
`NO_MODEL_EVIDENCE` on the existing 31-feature price/trend/risk +
fundamental-level + fundamental-change matrix. See
`docs/alpha-research-foundation-v2-errata.md` for the full correction, its
primary-source evidence (a GitHub Actions job log read directly), and every
document it touches. **That closed historical-discovery budget is not
reopened by anything in this PR** — every workstream below is either a
different construction over existing data, or a genuinely new information
axis that matrix never had.

---

## New independent information axes built in this PR

| Workstream | Module(s) | Region | New collection needed? | Status |
|---|---|---|---|---|
| A — Accounting quality | `pipeline/accounting_quality.py` | US + KR | No — reuses already-collected raw filings | **Built, measured against the real sealed store** |
| B — Liquidity/attention (magnitude-preserving) | `pipeline/liquidity_attention.py` | US + KR | No — reuses existing OHLCV | **Built, tested** |
| C — KR investor-type flow | `pipeline/kr_investor_flow.py` | KR only | Yes | **Built, unproven access (probe-first design)** |
| D — KR ownership events (5%-rule) | `pipeline/dart_ownership_events.py` | KR only | Yes (new DART endpoint) | **Built, unproven access (probe-first design)** |
| E — KR short-selling | `pipeline/kr_short_selling.py` | KR only | Yes | **Built, unproven access (probe-first design)** |
| F — Macro context (level/change/acceleration) | `pipeline/macro_context.py` | US/global | No — calls `regime.py` at multiple dates | **Built, tested**; `pipeline/ecos_macro.py` (KR) built as a fetch layer, also unproven access |
| G — US dividend-change events | `pipeline/dividend_events.py` | US only | No — reuses already-collected PIT field | **Built, measured against the real sealed store** |
| Guru — 13F historical store | `pipeline/guru_13f_store.py`, `pipeline/security_identity.py` | US only | Yes (bulk dataset likely blocked; per-manager fallback coded) | **Built, tested; access status likely BLOCKED, unconfirmed** — see `docs/guru-decision-atlas-data-v1.md` |

Every module above that reads real, already-collected data (A, B's design,
F's US half, G) was validated against the actual sealed store pulled from
the `signal-history` branch — not synthetic data alone. Every module that
needs a NEW external source (C, D, E, ECOS, Guru bulk 13F) is built and
unit-tested against synthetic fixtures, with a `probe_*.py` script designed
to establish live feasibility in GitHub Actions (which this sandbox cannot
reach) before any real collection runs.

---

## Workstream A — Accounting quality (measured)

`pipeline/accounting_quality.py` reuses `dart_derive`'s and
`finnhub_derive`'s own TTM-rollforward/level-reading primitives — it does
not re-derive TTM or column semantics a second time — and adds six fields
no production path exposes: `ocfToNetIncomePct`, `fcfToNetIncomePct`,
`assetGrowthPct`, `debtGrowthPct`, `capexIntensityPct`,
`shareCountChangePct`.

**Measured against the real sealed store** (pulled from `signal-history`,
not synthetic): 126 KR tickers / 3,965 rows (2015-2026); 779 US tickers /
30,999 rows (2011-2026).

| Field | KR coverage | US coverage |
|---|---|---|
| `assetGrowthPct` | 97.07% | 96.39% |
| `debtGrowthPct` | 97.00% | 96.08% |
| `shareCountChangePct` | 96.57% | 78.70% |
| `ocfToNetIncomePct` | 52.36% | 97.39% |
| `fcfToNetIncomePct` | 4.31% | 87.00% |
| `capexIntensityPct` | 7.74% | 83.03% |

The KR/US gap on `ocfToNetIncomePct`/`fcfToNetIncomePct`/`capexIntensityPct`
is real and structural: Korean filers omit `유형자산의취득` (capex) and
`영업활동현금흐름` (operating cash flow) far more often than US filers omit
their equivalent Finnhub concept chains — this is a coverage fact about the
underlying filings, not a defect in the derivation.

**Confirmed `NOT_FEASIBLE_DATA_MISSING`, not built**: receivables growth,
inventory growth, any working-capital metric — no such line item exists in
`dart_fundamentals.WANTED_ACCOUNTS` or `finnhub_derive`'s account chains,
confirmed by reading them directly, not assumed.

## Workstream B — Liquidity/attention, magnitude preserved (measured)

`pipeline/liquidity_attention.py` computes the volume/price family the
parent inventory named as economically distinct from anything in production
(`FACTOR_WEIGHTS` has no volume term at all): multi-window volume ratios
(1/20, 1/60, 5/20, 5/60), a magnitude-preserving `logVolumeShock60` (kept
SEPARATE from any percentile, per the inventory's own "2x vs 15x" argument),
volume z-score, dollar volume, turnover, dollar-volume shock and its
5-day persistence, price-direction-signed volume shock, a 20-day
volume/return divergence correlation, close-location value, abnormal range,
gap and gap×volume, range×volume, close-near-high/low-after-shock
indicators (deliberately NOT complements of each other — both can read 0.0
the same day), and an Amihud-style illiquidity proxy. Cross-sectional
percentiling is a SEPARATE explicit call (`cross_sectional_percentile`),
never baked into the per-ticker computation — a caller keeps magnitude and
rank side by side rather than being forced to collapse to one.

Verified on synthetic OHLCV with an injected 12x volume-shock day: the
module correctly flags the shock day (`logVolumeShock60` spikes,
`closeNearLowAfterShock` fires) and every "genuine absence" case (a
zero-range day, a non-shock day, a missing share count) returns `NaN`, never
a fabricated 0.0. 14 unit tests, all passing.

## Workstream F — Macro context, level/change/acceleration (measured, US)

`pipeline/macro_context.py` turns `regime.py`'s single-date axis reading
into a TIME SERIES by calling `regime.indicator_read`/`regime._axis_summary`
at a caller-supplied grid of dates — it does not re-derive the z-score
aggregation. `level_change_acceleration` then differences that series
backward-only (never forward) into level/change/acceleration per axis,
across all 6 axes (`growth`, `inflation`, `liquidity`,
`financialConditions`, `riskAppetite`, `earningsCredit`). Verified on
synthetic monthly macro data: the change/acceleration columns are correctly
`NaN` before their window is full, never look forward, and the six axes are
kept as six separate frames (their `[-1,+1]` levels are comparable, but
their confidence/coverage metadata is not, and is never pooled).

**KR has no axis to restructure this way** — every entry in
`regime.INDICATORS` is FRED/CBOE-sourced. `pipeline/ecos_macro.py` (built by
the delegated KR workstream, see below) is the fetch layer a future KR axis
would need; it is not wired into `regime.py` by this PR.

## Workstream G — US dividend-change events (measured)

`pipeline/dividend_events.py` reads `CommonStockDividendsPerShareDeclared`
— already anchored as a `PER_SHARE` concept in
`finnhub_fundamentals.UNIT_ANCHORS`, already sealed into the US PIT store —
and classifies it into `DIVIDEND_INITIATED` / `INCREASED` / `UNCHANGED` /
`DECREASED` / `SUSPENDED` / `NO_DIVIDEND`.

**A real reporting-convention finding, measured before writing the
classifier**: this concept is stated CUMULATIVE from the fiscal year start
(AAPL's real FY2013 filings state `2, 5, 8, 11` at 90/181/272/363 days into
the year) — the same convention `finnhub_derive.py` already measured for net
income/revenue/operating income/operating cash flow. A quarter's own
declared dividend is therefore NOT this field's raw value; it needs the
identical TTM rollforward, which this module implements by calling a
per-share-class reader analogous to `finnhub_derive.amount` rather than
re-deriving the rollforward arithmetic.

**A real data-quality caveat, published rather than hidden**: every sampled
value for this concept was a bare integer, never a decimal — AAPL's actual
2013 quarterly dividend was on the order of $2.65-$3.05, so sub-dollar
precision looks lost somewhere upstream of this store. The classifier's
±3% threshold is set wide enough that this integer rounding is not read as
a policy change.

**Measured against the real sealed store**: 3,806 classifiable events
across 220 of 779 US tickers (28.2%); event counts: 962 INCREASED, 965
UNCHANGED, 460 DECREASED, 313 SUSPENDED, 239 INITIATED, 867 NO_DIVIDEND.
Some zero-row tickers are genuine non-dividend-payers; others (confirmed on
KO specifically) are blocked because the concept is absent from that
ticker's ANNUAL filings, which the TTM rollforward requires — this mix was
not further disentangled in this PR.

---

## Workstreams C, D, E — Korean investor behavior (built, access unproven)

Built by a delegated research pass; every claim below was independently
re-verified (lint, compile, full test suite, and a read of each module's
own docstring) before being merged into this PR, not taken on faith.

### C — Per-stock investor-type flow (`pipeline/kr_investor_flow.py`)

**The KRX Open API this repo already holds a subscribed key for does not
serve this** — corroborated two ways: a third-party survey of the Open
API's own catalogue states plainly "API 미제공 데이터: 투자자별 거래실적,
외국인 보유량, 공매도," and this repo's own `probe_krx_index_membership.py`
already tried six `sto/`/`idx/` paths, none an investor-type breakdown. The
real route is KRX's public statistics portal
(`data.krx.co.kr/comm/bldAttendant/getJsonData.cmd`, the same mechanism
`pykrx` is built on), which is SESSION-backed — a bare POST (already tried
once, by `probe_krx_index_membership.py`) reads as `HTTP 400 LOGOUT`
regardless of parameters, because it carries no session/`Referer`/
`X-Requested-With` state. `scripts/probe_kr_investor_flow.py` is the first
attempt in this repo to send that state; it has not been run in an
environment with real network access.

Screens identified (via researching `pykrx`'s own source): `MDCSTAT02302`
(general — foreign/institution/individual net buy) and `MDCSTAT02303`
(detailed — institution split into 금융투자/보험/투신/사모/은행/기타금융/
연기금/기타법인). PIT-safe by construction: this is end-of-day settlement
data with no restatement mechanism, so `availableFrom` is simply the trading
date, stated explicitly rather than assumed.

**Grade: B — REPAIRABLE**, unchanged from the prior inventory's grade —
this PR adds a concrete, probe-first implementation attempt, not a
resolved access status.

### D — DART large-holdings / ownership events (`pipeline/dart_ownership_events.py`)

Reuses `dart_fundamentals.receipt_date` directly for PIT visibility — the
same vendor, same key, same receipt-date mechanism `dart_fundamentals.py`
already implements for financial statements, just a different endpoint
(`majorstock.json`, API group DS004). A live probe (Actions run 35964461327)
confirmed the source schema and corrected the earlier `report_tp` guess: real
sample values were `일반`/`약식`, retained only as `reportTypeRaw`. The raw-v2
contract also preserves `ctr_stkqy`, `ctr_stkrt`, and `report_resn` verbatim.
INCREASE/DECREASE/EXIT_BELOW_THRESHOLD remain explicitly derived from
`stkrt_irds`; no category is derived from the reason field.

Collection is now issuer-grained over the PIT KR membership union rather than
the current ticker list. Exact stock-code or unique exact-name mapping is
recorded; ambiguous identities remain unresolved. The present dataset is
`BLOCKED_HISTORICAL_DEPTH`: `majorstock.json` has no date-bound parameters and
the observed response covers only a rolling-looking two-year interval. See
`docs/dart-ownership-history-replay-integrity-v1.md`.

**Grade: B — REPAIRABLE, lowest-effort build in this whole line** —
unchanged assessment from the prior inventory, now backed by a concrete,
probe-first module.

### E — KR short-selling (`pipeline/kr_short_selling.py`)

Two distinct, differently-lagged screens identified (via WebSearch of KRX's
own published screen descriptions, since `data.krx.co.kr` itself is
unreachable from this sandbox): `MDCSTAT301` (daily short-sale TRADING
volume/value, available intraday — same-day figures after 15:40 KST,
full-day after 18:10 KST) and `MDCSTAT305` (net short POSITION holdings,
built from T+2 regulatory reports at a 0.01%-of-shares or KRW 1bn threshold
— a materially longer, different-kind lag). The two are never blended into
one field. Every module docstring explicitly flags which specific detail
(the exact `bld=` code, the precise threshold wording) is corroborated only
by a search-engine description of KRX's page rather than a direct read of
it — a probe script is what would resolve this, not this PR.

**The regime-break requirement from the prior inventory is carried
forward explicitly in the schema**: a `regimeLabel` field marks each date
`NORMAL` / `BANNED_COVID` (~2020-03 to ~2021-05) / `BANNED_STRUCTURAL`
(2023-11-05 to 2025-03-31) rather than presenting a seamless series across a
period when short-selling was illegal.

**Grade: B — REPAIRABLE**, unchanged from the prior inventory.

### ECOS fetch layer (`pipeline/ecos_macro.py`, `config.json` schema fix)

The dead-code finding from `alpha-information-inventory-v1` (zero HTTP
calls to `ecos.bok.or.kr` anywhere) is re-confirmed in this PR by the same
grep, same result. `pipeline/ecos_macro.py` is the first fetch-layer
implementation, built against ECOS's documented `StatisticSearch` URL
contract (positional path segments: key/format/lang/start/end/statCode/
cycle/startTime/endTime[/itemCode1][/itemCode2]) researched via
WebFetch/WebSearch of third-party wrappers (ECOS's own site is unreachable
from this sandbox). **Not called from `build.py` or `regime.py` — this PR
adds the fetch layer, not the wiring, per its own foundation-only scope.**

`config.json`'s `ecos.KR` schema was extended (backward-compatibly) so
`KTB_3Y` and `CorpBond_3Y` — which shared the bare series id `817Y002`, a
real unresolved ambiguity the prior inventory flagged — now carry an
explicit `{"seriesId": "817Y002", "itemCode": null}` shape.
**`itemCode: null` means genuinely unresolved, not a placeholder for a
guessed value**: no source consulted gave the exact item-code string with
enough confidence to write it down as fact, and `ecos_macro.py` refuses to
call a series whose `seriesId` is shared with another series and has no
`itemCode` set, rather than guess which column it would read.
`pipeline/config.py`'s `load_config` normalizes both the old bare-string
form and the new object form to one shape, so nothing else that reads
`Config.ecos_regions` needs to branch on which form a given series was
written in — verified by the full test suite (1874 tests, unchanged prior
count plus every new module's own tests, zero regressions).

Vintage status: **`REVISED_HISTORY`, not `PIT_EXACT`** — ECOS's
`StatisticSearch` returns current values; nothing consulted describes an
ALFRED-style vintage/release-history endpoint for it. Stated, not assumed,
per this repo's own PIT vocabulary (`pit_data.py`).

---

## Sector context

See `docs/alpha-data-foundation-v2-sector-context.md` in full. Headline: US
GICS point-in-time history exists only as a paid S&P product; **KRX
announced a wholesale replacement of its own classification system
(KRICS) on 2026-09-22** — two days before this investigation — retiring the
KSIC-based mapping this project would otherwise have had to use. Neither
finding changes `pipeline/sectors.py`'s current static map, and no
historical classification is backfilled by this PR.
`HISTORICAL_SECTOR_CONTEXT_UNRESOLVED` stands for both regions.

---

## What is explicitly NOT in this PR

Per its own scope: no Conditional Alpha v2, no LightGBM/HGBR/neural-network
model, no Guru model, no global ranking model, no Top-N strategy, no
opportunity portfolio, no interaction test between any new feature above and
any outcome, no forward-return computation anywhere in any new module (
mechanically checked — see Tests), and nothing above is imported by any
Main Alpha scoring path (also mechanically checked, see
`tests/test_guru_alpha_separation.py` for the Guru track's own guardrail;
none of the other new modules are imported by `pipeline/build.py`,
`pipeline/longterm.py`, `pipeline/opportunity.py`, or
`pipeline/kelly_portfolio.py` either — confirmed by grep before this PR was
finalized).

## Decision

**`MORE_DATA_FOUNDATION_REQUIRED`.**

Two of the eight new axes (A — accounting quality, G — dividend events) are
Grade B/measured-and-ready and need no further access work to be usable in
a future study. The macro-context restructuring (F, US half) is likewise
ready. The three Korean investor-behavior axes (C, D, E) and the Guru 13F
track are built and tested but their live access is **unproven from this
session** — every probe script exists but has not been run in an
environment with real network access (GitHub Actions, not this sandbox).
Per this repo's own discipline (a ladder is measured before it is
promoted), a study should not be pre-registered on data whose actual
availability has not been confirmed. The concrete next step is running each
`probe_*.py` script via its `workflow_dispatch` trigger and reading its
verdict — not building a model, and not yet a `READY_FOR_ALPHA_PREREGISTRATION`
call.
