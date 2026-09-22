# CHALLENGER-2 signal-source feasibility audit v1

> Research/documentation only. No portfolio backtest, no factor-weight
> optimisation, no candidate-vs-candidate performance comparison on
> `replay-v16`, no production change. `promotionEligible` stays `false` (the
> production CHAMPION has no other state to touch — this study never runs a
> selector). This PR selects and pre-registers a SIGNAL SOURCE for a future
> CHALLENGER-2 study; it does not build, score, or promote a ranking method.

## Why this study, and why now

`four-factor-signal-attribution-audit-v1` (#145) measured that none of the
four production sleeves (momentum, value, quality, lowvol) clears raw
significance at the pre-registered 126-day horizon, let alone Holm
correction, on `replay-v16`. That ledger has now been read by eleven prior
studies. The next legitimate move is not another axis inside the same four
sleeves on the same sample — `alpha-calibration-resolution-v1`,
`alpha-risk-separation-v1`, `lowvol-alpha-separation-v1` and
`entry-selection-separation-v1` already covered the calibration layer, the
risk denominator, the `lowvol` sleeve and the entry throttle, and none
separated. `docs/challenger-registry.md` reserves **CHALLENGER-2** for "a
genuinely different kind of ranking logic," not a parameter tweak, and this
study answers the prerequisite question a ranking-method design can't skip:
**what information source would that logic even rank on?**

## What this study is and is not

This is a **DATA + ECONOMIC HYPOTHESIS FEASIBILITY AUDIT**. It is not:

- a new portfolio backtest,
- a factor-weight optimisation,
- a performance comparison between candidate signals on `replay-v16`,
- a "pick the best-performing candidate" exercise,
- a production change of any kind.

The candidate is selected on economic rationale, orthogonality to the
existing four sleeves, PIT data quality, KR/US coverage, cost, and
implementation integrity — **never** on a historical return number. This is
the single most important discipline in this document, restated in Q9.

## Required reading (confirmed read before this report was written)

`AGENTS.md`, `README.md`, `docs/challenger-registry.md`,
`docs/challenger-2-research-prompt.md`, `pipeline/longterm.py`,
`pipeline/historical_replay.py`, `pipeline/historical_outcomes.py`,
`pipeline/portfolio_validation.py`, `pipeline/dart_fundamentals.py`,
`pipeline/dart_derive.py`, `pipeline/finnhub_fundamentals.py`,
`pipeline/finnhub_derive.py`, `pipeline/krx_prices.py`,
`pipeline/krx_universe.py`, `pipeline/sec_access.py`, `pipeline/fundamentals.py`,
`pipeline/config.py`, and the prior-study results named in the task
(`selection-value-decomposition-v1`, `signal-persistence-v1`,
`alpha-reliability-v1`, `alpha-risk-separation-v1`,
`entry-selection-separation-v1`, `lowvol-alpha-separation-v1`,
`alpha-calibration-resolution-v1`, `four-factor-signal-attribution-audit-v1`).
No already-settled axis from these studies is re-proposed under a new name.

## The five baseline candidates, plus none added

Sections 3–4 of the pre-registration name five candidates (A–E) and permit
up to two more if something clearly superior surfaces. Repository and
vendor research (below) did not surface a candidate that clears PIT +
KR/US + personal-scale bars more cleanly than the strongest of the five, so
**no additional candidates are added**. Two considered and rejected without
a full write-up: options-implied skew/IV (US institutional-cost data feeds,
no viable KR leg at personal scale) and insider Form 4 transactions (SEC
direct access is confirmed blocked for this repository as of 2026-09 — see
below — and no alternate vendor re-serves Form 4 the way Finnhub re-serves
10-Q/10-K). Padding the candidate list with these would not sharpen the
audit, per the pre-registration's own instruction not to widen it
gratuitously.

## What this repository's vendor connections actually look like today

Verified directly against `pipeline/` and `scripts/`, not assumed:

| Vendor | Env var | What it's used for today | Status (from this repo's own probes/AGENTS.md) |
|---|---|---|---|
| DART (`dart_fundamentals.py`, `dart_derive.py`) | `DART_API_KEY` | KR raw filings → PIT ratios (`roe`, `operatingMargin`, `profitMargin`, `debtToEquity`, `earningsGrowth`, value yields) | Working, production KR fundamentals source since `replay-v6`. Serves from 2015; 2013–2014 KR value/quality is dark by construction. |
| Finnhub (`finnhub_fundamentals.py`, `finnhub_derive.py`) | `FINNHUB_API_KEY` | US raw filings (`/stock/financials-reported`) → PIT ratios, same field shape as DART's | Working, production US fundamentals source since `replay-v15` (unsealed 2026-09-14). Measured: 676 US names carried PIT `roe`/`epsTtm` as of 2013-06-28 — full replay-span coverage now exists. |
| KRX (`krx_prices.py`, `krx_universe.py`) | `KRX_API_KEY` | KR prices and universe membership | Partial: `sto/stk_bydd_trd` open; `sto/ksq_bydd_trd`, `sto/stk_isu_base_info`, `idx/kosdaq_dd_trd` still refuse `Unauthorized API Call`. Access is granted per endpoint, not per key. |
| SEC (`sec_access.py`) | — (User-Agent only, no key) | Direct EDGAR reads (13F, some filing metadata) | **Confirmed blocked** as of 2026-09-04/09-13: every direct host (`data.sec.gov`, `www.sec.gov`, `efts.sec.gov`, bare `sec.gov`) returns 403 with byte-identical block pages across every header set and every egress address tried. Domain-level policy, not a header or address artefact. |
| FMP | `FMP_API_KEY` (probe scripts only) | Evaluated, **not adopted**, for US PIT fundamentals | Serves real statements with `filingDate`, but the measured historical-depth cap under this project's subscription tier does not reach before ~2025-06-27 — useless for a 2013-start replay. Superseded by Finnhub for this purpose. |

This means: **any new candidate that can be built entirely from DART and/or
Finnhub's already-collected raw filings needs zero new vendor
integration, zero new cost, and inherits a PIT-timestamp discipline
(`availableFrom` = receipt/filing date) that is already built, tested, and
production-proven.** Any candidate that needs a genuinely new vendor
(analyst consensus, options data, short interest) starts from zero on all
of those axes.

## Candidate evaluation table

Performance columns are deliberately absent — see "What this study is not."

| Candidate | Economic rationale | Orthogonal to 4-factor | US PIT | KR PIT | History | Coverage | Cost | Complexity | Main leakage risk |
|---|---|---|---|---|---|---|---|---|---|
| A. Earnings revision | Market underreacts to analyst EPS/consensus revisions (distinct from realised growth) | Yes in principle — forward EXPECTATION change vs Quality's realised `earningsGrowth` LEVEL | Needs a NEW paid Finnhub "Estimates" add-on or FMP estimates (untested depth); no confirmed 2013-start history | **Blocked**: FnGuide/FnSpace is the de facto official KR consensus API, but its published terms explicitly forbid building a user's own database — the one thing PIT storage requires | Unconfirmed for either region | Estimate coverage skews to larger/more-covered names — a possible size confound | Paid (US); KR blocked regardless of price | MEDIUM–HIGH (new vendor, consensus reconciliation, revision-delta logic) | Vendor-side estimate revisions/methodology changes retroactively — "as of" semantics need vendor confirmation, not assumed |
| B. Estimate dispersion | Disagreement level/change relates to future return/uncertainty | Yes in principle — a distinct SECOND MOMENT of the same forward-looking object | Same dependency as A | Same block as A | Unconfirmed | Same size-coverage confound, sharper (dispersion needs multiple analysts per name) | Same as A | Same as A, plus dispersion-construction choices | Same as A |
| **C. Fundamental acceleration** | Rate-of-change in profitability/growth/margins carries information a static level does not (inflection vs level) | **Yes, and testable directly**: current Quality scores the LEVEL of `roe`/`operatingMargin`/`profitMargin`/`earningsGrowth` at one filing; acceleration is the CHANGE in those same ratios between consecutive filings — a different quantity by construction | **Built entirely from Finnhub data already collected**; `finnhub_derive.py`'s TTM rollforward already exists | **Built entirely from DART data already collected**; `dart_derive.py`'s TTM rollforward already exists | **Identical to the current Value/Quality sleeves' depth** — no new limitation | **Identical to current Value/Quality coverage** — same underlying rows | **Zero incremental** — same keys, same quota | LOW–MEDIUM — a new DERIVATION over existing per-filing history, no new collector | LOW — inherits the already-tested `availableFrom` discipline; both legs of a difference are independently PIT-stamped filings |
| D. Relative-strength breadth | Confirmation/persistence across horizons is a distinct "trend health" signal from raw momentum magnitude | **High risk of failing this gate** — built from the same daily price series Momentum already uses; a multi-horizon agreement measure is likely to correlate strongly with 12-1M/6M momentum by construction, and `four-factor-signal-attribution-audit-v1` already found standalone momentum's own IC near zero | Trivial (price data) | Trivial (price data) | Full existing price history | Full existing universe | Zero incremental | LOW | Minimal (prices are inherently dated) |
| E. Valuation change / re-rating | Multiple expansion/compression, especially conditional on earnings change, is distinct from static value LEVEL | Yes vs static Value, but **doubtful vs Candidate C once C exists** — "change conditional on earnings change" measures much of the same "improving fundamentals" object through the price/multiple lens instead of the earnings lens | Buildable from existing PIT earnings-yield/book-yield history + PIT prices | Same | Same as C | Same as C | Zero incremental | MEDIUM — isolating multiple re-rating from pure price momentum is a real design subtlety | LOW, same infra as C |

## The five gates, applied

**Gate 1 — PIT reproducibility (KR AND US).** A and B fail: KR-side analyst
consensus is not merely expensive, it is **ToS-blocked** for the one thing
this project needs (building a persistent PIT database) via the only
identified official Korean provider (FnGuide/FnSpace). Per the
pre-registration's own rule, a single-region-only candidate is
`REGION_LIMITED` and cannot be primary. **C, D and E pass** — all buildable
in both regions from data already flowing through this repository's
production vendors.

**Gate 2 — distinct information.** D is at serious risk of failing this
gate — a breadth/agreement construct built from the same price series
Momentum already scores is plausibly a relabelled momentum variant, exactly
the kind of disqualified example the pre-registration names ("단순 9M
momentum"). **C passes cleanly**: acceleration (a first difference across
filings) is a different mathematical and economic object from the level
Quality already scores, and this is falsifiable directly once the signal is
computed (low correlation with the level factor is an empirical prediction
the next study will check, not an assumption made here). **E passes against
the 4-factor** but is weaker against C specifically, once C exists.

**Gate 3 — sufficient historical depth for independent validation.** C and
E inherit exactly the depth the current Value/Quality sleeves already have
(US: full 2013–present since `replay-v15`; KR: dark 2013–2014, DART-backed
from 2015). No new depth problem is introduced. A/B have no confirmed
historical depth from either candidate estimates vendor.

**Gate 4 — realistic cost.** A and B require an ongoing paid subscription
on the US leg even before accounting for the KR block. C, D and E cost
**zero incremental** — same vendors, same keys, same quota already in use.

**Gate 5 — implementation integrity (no lookahead).** C inherits the
`availableFrom`/receipt-date discipline `dart_derive.py`/`finnhub_derive.py`
already enforce and this project has already spent significant effort
proving correct (TTM rollforward rule, filing-date-not-period-end rule,
quarterly-vs-cumulative column rule). A and B would need this proven from
scratch against a vendor never yet integrated. D and E are also clean on
this gate.

**Result: A and B are disqualified at Gate 1 (`REGION_LIMITED`, KR
categorically blocked by data-provider terms, not merely cost). D is at
high risk of failing Gate 2 and is not selected. E passes every gate but is
weaker than C on Gate 2 once C exists, and its correct specification is
more subtle (isolating re-rating from pure price momentum). C is the only
candidate that clears every gate cleanly.**

## PROPOSED_CHALLENGER_2_SOURCE = Fundamental acceleration

The design for the next study is in
`docs/challenger-2-fundamental-acceleration-v1-design.md`. **No backtest is
run in this PR.**

## Answering the pre-registered questions (Q1–Q10)

**Q1. Which candidates differ most from the current 4-factor?** Earnings
revision and estimate dispersion (A, B) differ the most in principle
(forward expectations vs realised fundamentals) but fail Gate 1. Among the
gate-passing candidates, fundamental acceleration (C) differs most cleanly
and testably from Quality's static level.

**Q2. What is each candidate's economic hypothesis?** See the table's
"Economic rationale" column — underreaction to revisions (A), disagreement/
uncertainty (B), inflection over level (C), trend confirmation (D),
re-rating (E).

**Q3. Which candidates are PIT-implementable in both KR and US?** C, D, E.
A and B are US-only at best (`REGION_LIMITED`), and KR is not merely
harder but ToS-blocked for the identified official provider.

**Q4. Which candidates are the existing factors renamed?** D is the one at
real risk of this — a multi-horizon price-agreement measure built from the
same series Momentum already uses. It is not selected as primary for this
reason.

**Q5. What is each candidate's biggest leakage/survivorship risk?** A/B:
vendor-side retroactive revision of consensus figures with unconfirmed "as
of" semantics. C: none beyond the already-solved receipt-date discipline,
provided both legs of any difference independently satisfy
`availableFrom <= asOfDate` (see the design doc's explicit rule). D:
minimal. E: multiple-re-rating definitions that accidentally reduce to
price momentum if not carefully isolated.

**Q6. How much is buildable with free/already-available APIs alone?** C, D
and E are 100% buildable today with zero new vendor integration and zero
incremental cost. A/B require a new paid dependency on the US leg alone.

**Q7. Is there enough historical depth for independent validation?** C and
E inherit the current Value/Quality sleeves' depth exactly (see Gate 3). A
and B have no confirmed depth on either identified vendor.

**Q8. What is the pre-registered CHALLENGER-2 source?** Fundamental
acceleration (C).

**Q9. Why — and specifically not because of a historical return number?**
Because it is the only candidate that (a) measures something the current
composite genuinely cannot see (rate of change vs level — Quality has no
memory of a name's own trajectory), (b) is buildable in BOTH regions from
vendors this repository has already integrated, tested, and paid the
integration cost for, (c) introduces zero new cost, survivorship, or
lookahead risk beyond what is already solved, and (d) has a historical
depth identical to sleeves already in production, meaning any future
result is not gated on a brand-new, unproven collection effort. No
`replay-v16` return number was computed for any candidate in this study —
that is the entire point of Gate-based, not score-based, selection.

**Q10. Under what conditions would this candidate be abandoned?** If, once
computed in the CHALLENGER-2 design's own diagnostic stage (never a
backtest), the acceleration measure turns out to be highly correlated with
the existing Quality level factor (failing the Gate-2 prediction this
report makes but does not yet verify), if the PIT-difference construction
cannot be made leak-free in practice once implemented, or if coverage
collapses once acceleration's two-filing requirement is applied (a name
needs TWO consecutive PIT filings, not one, which could bind harder than
the level factor's single-filing requirement — an open question the design
doc flags as the first thing to measure).

## Independent validation design (summary — full design in the CHALLENGER-2 doc)

Per the pre-registration's explicit priority order:

1. **Truly new prospective data** — the primary validation path. The
   acceleration signal is computed going forward from a date after this
   PR, sealed before any human sees its value, and scored only once its
   126-day horizon matures.
2. **An unused historical period/universe** — **not available**. Reported
   honestly rather than stretched: `four-factor-signal-attribution-audit-v1`
   already tested the FULL 2013–2026 span for standalone factor IC, so no
   sub-period of `replay-v16` is meaningfully "untouched" from a
   factor-efficacy perspective, even though the acceleration TRANSFORM
   itself has never been computed before.
3. **An independent external dataset** — **not available** at personal
   scale with this project's existing universe/benchmark construction.
4. **`replay-v16`, discovery-only** — used as a bridge while the
   prospective window matures: computing the signal and its basic
   cross-sectional properties (coverage, distribution, correlation with the
   existing level factor) on the sealed ledger is legitimate DISCOVERY, but
   is explicitly barred from being read as confirmatory evidence, exactly
   as this repository's own discipline requires for a contaminated sample.

## Secondary deliverable: 4-factor PIT instrumentation proposal

A schema proposal for storing raw subfactor inputs on FUTURE signal
records — never a historical ledger rewrite — is in
`docs/four-factor-pit-instrumentation-proposal-v1.md`. Notably, Candidate C
does **not** depend on this proposal at all: `FundamentalStore` already
retains full per-filing history (`PIT_FUNDAMENTALS_V1` rows are append-only
and keyed by ticker × fiscal year × report code), so acceleration is a new
DERIVATION over already-collected data, not a new collection.

## Production discipline

- No `FACTOR_WEIGHTS`, `CHAMPION`, selector, config, or portfolio-weighting
  change.
- No paper/live promotion change.
- No new signal connected to production ranking.
- `promotionEligible: false` (unchanged — this study never runs a
  selector).
- `docs/challenger-registry.md` is **not** modified by this PR: per its own
  "Adding a row" rule, a CHALLENGER-N row is added only once a ranking
  method is actually scored through `selection_null`, which has not
  happened here — this PR selects a SIGNAL SOURCE, not a ranking method.

## Verification

This PR is documentation/research only — no `pipeline/` or `scripts/` code
changed. Per AGENTS.md's own instruction to verify proportionally to the
change: `ruff check .`, `python -m compileall pipeline` and `pytest -q`
were still run to confirm the repository's baseline is unaffected (all
pass, unchanged from `main`). No sealed replay result is touched or
regenerated; no seed generation or artifact validation is relevant, since
no code or production artifact changed.

## What this study does NOT establish

- Not a backtest, not a factor comparison, not a performance claim about
  any candidate.
- Not a production change of any kind.
- Not a `CHALLENGER-2` registry entry — that follows only once a ranking
  method built on this source is actually scored.
- This PR does not start the CHALLENGER-2 study itself. Per the
  pre-registration's explicit instruction, it stops here for review.
