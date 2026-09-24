# Alpha information inventory v1 — candidate next hypotheses

> **Pre-registered candidates only. No future-return relationship, IC, or
> backtest was computed to select or rank these.** They are ordered here for
> narrative convenience only — order is not a performance ranking, and none
> of these is a decision to build; that decision belongs to whoever
> pre-registers the next actual study. Decision categories are:
> `READY_TO_PREREGISTER`, `DATA_BUILD_FIRST`, `NOT_FEASIBLE`,
> `ALREADY_TESTED`, `NEEDS_PAID_DATA`.

**CORRECTED (v2):** the paragraph below, as originally written, named
`regional-alpha-model-v1` as unexecuted, zero-new-data first work. That was
a factual error — it was executed on 2026-09-23 and closed both regions at
`NO_MODEL_EVIDENCE` (see `docs/alpha-research-foundation-v2-errata.md`). It
is a concluded, closed study, not a queued action, and none of the five
hypotheses below re-uses its spent historical-discovery budget: each is
either a different construction over existing data (H1, H2, H5) or a
genuinely new information axis this matrix never had (H3, H4).

---

## H1 — Regime-conditional leadership (macro regime × stock price/momentum leadership)

**Economic logic**: a stock's relative price leadership may carry different
forward information depending on the macro backdrop it occurs in — e.g.
momentum persistence typically behaves differently when financial
conditions are easing versus tightening, and this repository's own prior
design work named several such combinations (momentum under easing
liquidity, quality under slowdown) as candidate hypotheses that were never
tested, not as hypotheses already rejected.

**Data available**: production's 6-axis US/global regime engine
(`regime.py`, already computed on every build) and the existing
momentum/leadership features (`mom121`, `mom6`, `relMomentum`,
`momentum20Acceleration`/`momentum60Acceleration` from the Opportunity
radar). **No new data source is required for the US arm** — this is purely
new interaction-testing code over data every build already produces.

**Difference from prior research**: confirmed genuinely absent by grep — no
file in `pipeline/` or `scripts/` combines any regime axis with any
momentum/acceleration feature in an interaction test. `historical_calibration.regime_interaction()`
tests region×bucket×regime (a *portfolio-outcome* interaction), not a
stock-level feature×regime interaction — a different question.

**US/KR applicability**: US arm is immediately testable. **KR arm is
blocked** — Korea has zero regime-axis representation (see the gaps
document, §2); this hypothesis cannot be tested for Korea until the ECOS
layer is built.

**Expected horizon**: MEDIUM (63–126d) — regime state changes slowly, and
this is a leadership-persistence question, not a very-short-term shock
question.

**Biggest risk**: the six regime axes were built for a portfolio-level
"how should Kelly/cash be adjusted" question, not for a stock-level
interaction; some axes (e.g. `earningsCredit`, a single derived yield-curve
sign) may have too little cross-sectional variation over the sample to
support a meaningful interaction test at all — this itself would need to be
measured (sample-size/variation check) before committing to a full study,
exactly as `dynamic-breadth-v1`'s own axis-measured-before-the-ladder
discipline requires.

**Decision category**: `READY_TO_PREREGISTER` (US arm only). KR arm is
`DATA_BUILD_FIRST` (contingent on the ECOS build in the gaps document).

---

## H2 — Volume/liquidity shock with magnitude preserved, conditioned on fundamental health

**Economic logic**: an unusual volume event may be more informative when it
occurs in a name with healthy fundamentals (confirmation) than in one
without (potential distress-driven or news-driven noise) — and the
magnitude of the shock (2x average volume vs 15x) may itself carry
information a percentile rank alone discards.

**⚠ Explicit overlap disclosure — read before proceeding.** The Opportunity
model already blended `volumeSurge`, `volumeSurgeDelta`,
`momentum20Acceleration`/`momentum60Acceleration`, and `valuePercentile`/
`qualityPercentile` through 7 model families including LightGBM, on 260,020
rows, with a sealed holdout — and it was **rejected** (negative decile
monotonicity, failed the baseline-beat check; see the research map §5).
**This hypothesis is only defensible as a distinct study if its
construction differs materially from what was already tried**: specifically,
(a) preserving raw or log volume-shock magnitude instead of collapsing to a
percentile, and (b) a hand-specified conditional/threshold interaction
(e.g., "volume shock counts only above N and only when quality percentile
exceeds M") rather than an ML blend that lets the model find its own
combination. If a future study cannot state this distinction explicitly and
concretely, it should not be run — it would be redoing already-rejected
work under a new name, which is the exact failure mode this inventory exists
to prevent.

**Data available**: all raw daily Volume/Close/High/Low is already stored
for both regions; the magnitude-preserving features themselves (dollar
volume, dollar-volume shock, log-scaled surge, sector-adjusted shock) are
none of them currently coded — see the data map §4's exhaustive
COMPUTABLE-but-not-built list.

**Difference from prior research**: the construction (magnitude-preserving,
hand-specified interaction) as opposed to the information (which
substantially overlaps the rejected Opportunity blend).

**US/KR applicability**: both regions — raw OHLCV/volume exists for both,
and the fundamental-health conditioning variables (quality percentile) are
already produced for both in the replay path.

**Expected horizon**: VERY_SHORT to SHORT_MED (1–63d) — volume shocks are
short-lived events.

**Biggest risk**: given the overlap above, the most likely outcome is that
this reproduces the Opportunity model's rejection under a different
construction — which would still be a valid, useful, and reportable result
(a second independent test of the same underlying information, per this
repository's own discipline of not hiding a repeated-negative result), but
should not be presented as if it were untested information.

**Decision category**: `DATA_BUILD_FIRST` (new feature-engineering code,
no new vendor) — **with the overlap caveat above carried into the
pre-registration itself.**

---

## H3 — Korean investor-flow confirmation of price leadership

**Economic logic**: sustained foreign or institutional net buying alongside
existing price leadership (momentum) may be a more durable signal than
price leadership alone — "someone with capital and information is
accumulating," a genuinely different information channel (who is trading)
from anything currently used (what the price/fundamentals say).

**Data available**: none currently — this is the KR investor-flow
structural gap (gaps document §1). A real, free, official source is known
to exist (KRX per-stock investor-type net-buying statistics) but is not
reachable from this project's current network/API-key configuration.

**Difference from prior research**: **HIGHLY_DISTINCT** — no investor-flow
signal of any kind exists anywhere in this repository's KR research
(confirmed: the 31-feature research matrix has zero flow fields; the
Opportunity model has zero flow fields; production has zero flow fields).

**US/KR applicability**: KR only. A comparable US per-stock daily
investor-type breakdown does not exist as a data product (13F is quarterly,
45-day-lagged, and covers a tiny explicit manager watchlist — not a
substitute).

**Expected horizon**: SHORT_MED to MEDIUM (21–126d) — accumulation patterns
are typically read over weeks, not single days.

**Biggest risk**: the data build itself. The known mechanism
(`data.krx.co.kr`'s public statistics loader) was already found unreachable
from this project's sandbox by a prior probe (`scripts/probe_krx_index_membership.py`);
this hypothesis cannot proceed to any measurement until either KRX
Open-API access is broadened or a reachable-network build path is found.

**Decision category**: `DATA_BUILD_FIRST`.

---

## H4 — Korean large-holdings disclosure (5%-rule) as an ownership-change signal

**Economic logic**: a change in a large shareholder's disclosed position
(accumulation, reduction, exit) is a distinct behavioral signal from price
momentum, fundamentals, or aggregate investor flow — it identifies a
*specific, identified* holder's conviction change, closer in spirit to (but
structurally different from, since it is disclosure-triggered rather than
quarterly-snapshot) the US 13F concept this repository already has, applied
to Korea for the first time.

**Data available**: not currently collected, but the mechanism is the
**lowest-effort build in this entire inventory** — DART's own developer
guide documents a dedicated API group (지분공시 종합정보, `DS004`) with
`rcept_no`/`rcept_dt` receipt-date fields, the *exact same* PIT mechanism
`dart_fundamentals.py`'s `receipt_date()` already parses for financial
statements. This is a new module reusing an already-proven pattern, not a
new-vendor integration.

**Difference from prior research**: **HIGHLY_DISTINCT** — ownership
concentration/disclosure behavior is not represented anywhere in current KR
research (the 31-feature matrix has no ownership field at all).

**US/KR applicability**: KR only, by construction (this is a Korea-specific
disclosure regime; the US analog is Form 4/13D-13G, a completely different
filing system already separately graded in the data map §13, Grade C,
blocked by the SEC-wide access issue).

**Expected horizon**: SHORT_MED to MEDIUM (21–126d).

**Biggest risk**: coverage and materiality — 5%-rule disclosures are
triggered only above a threshold and only by a subset of shareholder types;
the resulting signal may be sparse (few names, few dates) relative to the
5-name concentrated book this repository's production selector holds, and
that sparsity would need to be measured (not assumed) before this could
support a cross-sectional ranking.

**Decision category**: `DATA_BUILD_FIRST`, flagged as the cheapest build in
this inventory.

---

## H5 — US dividend-change / distribution-policy signal

**Economic logic**: a change in a company's dividend policy (initiation,
increase, cut) is often read by market participants as management's own
signal about the durability of earnings — a distinct economic claim from
current profitability levels (which the existing quality sleeve already
measures) or price momentum.

**Data available**: **the only candidate in this inventory where the raw,
PIT-safe data is already sitting in the canonical store today.**
`finnhub_fundamentals.py`'s `UNIT_ANCHORS[PER_SHARE]` list already includes
`CommonStockDividendsPerShareDeclared`, collected and sealed as part of the
already-backfilled US PIT fundamentals store (replay-v15+). No new vendor,
no new PIT-timing research is required — only a new derived field
(period-over-period dividend-per-share change) analogous to what
`finnhub_derive.py` already does for other ratios.

**Difference from prior research**: **PARTIALLY_DISTINCT** — corporate
payout policy is economically adjacent to, but not identical to, the
existing profitability/leverage quality sleeve; it has never been tested as
its own signal.

**US/KR applicability**: US only, as scoped here (the raw field exists in
the US Finnhub store; whether an equivalent field is collected on the KR
DART side was not confirmed in this inventory and would need its own check
before extending this hypothesis to Korea).

**Expected horizon**: MEDIUM to MED_LONG (63–252d) — dividend-policy changes
are typically slow-moving, quarterly-cadence signals.

**Biggest risk**: this is a narrow, single-event signal rather than a broad
new information axis — it may be too sparse (dividend changes are
infrequent events for most names in a given window) to support a
standalone cross-sectional factor on its own, and might be more usefully
framed as an addition to the existing quality sleeve than as a new
standalone "conditional alpha" model. That framing decision belongs to
whoever pre-registers this study, not to this inventory.

**Decision category**: `READY_TO_PREREGISTER`.

---

## Summary table

| # | Hypothesis | Region(s) | New data needed? | Overlap with prior research | Horizon | Decision |
|---|---|---|---|---|---|---|
| H1 | Regime-conditional leadership | US now, KR blocked | No (US) | None found (confirmed absent) | MEDIUM | `READY_TO_PREREGISTER` (US) / `DATA_BUILD_FIRST` (KR) |
| H2 | Volume/liquidity magnitude × fundamental health | US + KR | No (feature-engineering only) | **Substantial — see explicit caveat** | VERY_SHORT–SHORT_MED | `DATA_BUILD_FIRST`, overlap-flagged |
| H3 | KR investor-flow × price leadership | KR only | Yes (KRX access) | None found (confirmed absent) | SHORT_MED–MEDIUM | `DATA_BUILD_FIRST` |
| H4 | KR large-holdings (5%-rule) ownership change | KR only | Yes (new DART module, low effort) | None found (confirmed absent) | SHORT_MED–MEDIUM | `DATA_BUILD_FIRST` |
| H5 | US dividend-change signal | US only | No (data already collected) | Partial (adjacent to quality sleeve) | MEDIUM–MED_LONG | `READY_TO_PREREGISTER` |

No hypothesis above was selected, ordered, or filtered using any measured
relationship to future returns. Two (`H1`-US, `H5`) require no new data
collection at all; the remaining three are scoped exactly to the structural
gaps named in the gaps document. `ALREADY_TESTED` and `NEEDS_PAID_DATA`
categories are not represented among the final five because the candidates
that would have fallen there (analyst estimate revisions, options data,
credit ratings) are documented as closed/paid in the data map and gaps
document instead of being carried forward as live candidates.
