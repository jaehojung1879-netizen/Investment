# alpha-opportunity-model-v3: data-repair plan

This is a plan, not an implementation. It resolves none of v3's blockers.
Nothing here was fitted, labelled or valued. Where a source is described as
working, the evidence is a probe already recorded in this repository.
Everything else is marked **unverified**.

Evidence: `docs/results/alpha-opportunity-model-v3-survivorship-audit.json`
(input-only, byte-reproducible) and
`research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz`.

## Path

| Step | What | May become READY? |
|---|---|---|
| v3 | design + diagnosis, sealed `BLOCKED_BY_DATA_INTEGRITY` | **No.** v3 is never unblocked in place |
| data-foundation repair | separate PRs that collect and seal the inputs below; no alpha outcome is read | n/a (data only) |
| v4 | new immutable preregistration over the repaired, sealed inputs | Only after identity, survivorship, total-return lineage, sample depth and sealed execution inputs are each re-audited input-only with the v3 rules |

No alpha outcome may be inspected before v4 is sealed. A repair that fixes only
one region makes a region-scoped v4 possible. That is a change of scope and
must be preregistered as such, not inherited from v3.

## US

### What is missing (identity-resolved audit)

| | Count |
|---|---|
| index members ever (identity-resolved) / current / departed | 827 / 503 / 324 |
| departed members with **no usable history** (own or verified-rename) | **212** (65.4% of departed; 0% of current) |
| · exit reason unresolved from sealed evidence | 181 |
| · symbol's only panel belongs to a later security (reuse) | 29 |
| · acquired, from the sealed corporate-action book (ESRX) | 1 |
| · verified rename whose successor has no panel (CDAY→DAY) | 1 |
| departed members priced by their own history / via a verified rename | 99 / 13 |
| securities in the panel that ever stop trading | **0** |
| current symbols whose panel starts after their membership began (earlier issuer or later listing, e.g. FOXA) | 7 |

### What a repair needs

1. Daily prices for former, acquired and delisted members, **keyed by a
   security identifier** (not a bare ticker, since tickers are reused).
2. A historical identity map: symbol × date → issuer/security, covering
   renames before 2023. The upstream constituent file carries CIK only from
   2023-04-13.
3. Splits and cash distributions for the same securities, as-of dated.
4. Terminal treatment for every exit: cash consideration, stock consideration
   and successor, or the delisting price and any post-delisting value.
5. PIT lineage: every value dated by when it was knowable; no value restated
   from later vintages.

### Sources

| Source | Access (measured here) | Delisted history | Corporate actions | Identifier | Cost | Reproducible | Suitability |
|---|---|---|---|---|---|---|---|
| Yahoo (current replay panel) | served | **none**: no priced US panel ever terminates; delisted tickers return nothing | splits and dividends for listed names | bare ticker; reused symbols return the later issuer | free | yes (sealed) | **Unsuitable** for survivorship |
| FMP `/stable/historical-price-eod/full` | control served in full (3,437 rows); 11 of 12 departed names returned **HTTP 402**, VIAC partial (Probes run #2, 2026-09-16) | exists behind a paid plan | not measured | not measured | paid (price not measured) | unknown | Candidate, **unverified** |
| polygon `/v2/aggs` | control served a 2-year window; departed names 403 "plan doesn't include this data timeframe" | exists behind a paid plan | not measured | not measured | paid (price not measured) | unknown | Candidate, **unverified** |
| stooq CSV | bot wall even for AAPL/JPM/XOM | — | — | — | free | — | Unusable |
| finnhub `/stock/candle` | 403 for this key, controls included | — | — | — | — | — | Unusable with current key |
| Alpha Vantage | `NO_KEY`, never asked | unknown | unknown | unknown | unknown | unknown | Not investigated |
| SEC EDGAR | domain-wide 403 from Actions (vendor-refusal invariants) | no prices | 8-K events (unreachable) | CIK | free | — | Blocked; identity only if reachable |
| CRSP / Sharadar / other delisting-inclusive masters | never probed in this repository | unknown here | unknown here | unknown here | paid | unknown | Not investigated |

**US historical execution remains blocked pending an external
delisted-inclusive market-data source.** Choosing and paying for one is a human
budget decision, and none is assumed here.

A successor v4 would need, at minimum:
- the 212 identities priced with their own history
- the 181 unresolved exits classified: rename, merger, acquisition or
  delisting
- terminal values sealed
- a re-run audit showing departed-only missingness no longer concentrated
  (rule 1) and terminations observed (rule 2)

Partial recovery does not qualify. The defect is that a whole class of company
is absent, not that some share of name-dates is missing.

## KR

### What is missing

| | Value |
|---|---|
| members ever / current / departed | 260 / 120 / 140; every one priced (KRX daily records include later-delisted issues) |
| terminated securities (panel stops > 45 days before cutoff) | 22 |
| terminated names with any dividend event | **0 of 22** (vs 215 of 238 continuing) |
| affected tradable member-dates | 3.74% (7.93% in 2013 → 0.76% in 2025) |
| missing forward endpoints (all on terminated names) | 22 at 21 sessions / 300 at 126 sessions |
| termination type | `TERMINATION_TYPE_UNRESOLVED` for all 22: no sealed source states it |

The cause is structural. `pipeline/korea_prices.py` takes distributions from
Yahoo "if Yahoo happens to carry the name", and Yahoo does not carry delisted
KR tickers. So the names that leave are price-return while survivors and the
069500.KS benchmark are total-return.

### Repair 1: dividend lineage for the 22

- **Source:** DART, which is already this repository's KR vendor, key and PIT
  mechanism (`dart_fundamentals`, `dart_ownership_events`). Candidates:
  - the periodic-report dividend section (`alotMatter`), which gives DPS per
    fiscal period, dated by the report's receipt date;
  - the 현금·현물배당결정 disclosures, which give the record date (배당기준일)
    and amount.
- **Why both:** total-return accumulation needs the **ex-date**, which
  `alotMatter` does not state. The decision disclosure's record date fixes it
  only through the exchange's settlement convention. That convention, and any
  change to the Korean dividend-record regime inside 2013–2026, must itself be
  sealed as a dated, sourced rule rather than assumed.
- **Status:** neither endpoint is collected or probed in this repository.
  **Unverified.**
- **Validation before use (outcome-free):**
  1. Run the same DART derivation on continuing names where Yahoo already
     serves distributions.
  2. Require agreement of amounts and ex-dates within a stated tolerance.
  3. Only then apply it to the 22.
  4. Refuse, and do not substitute, any name DART cannot serve.
- **PIT:** a distribution counts from its ex-date for returns. Its
  availability for any feature is the disclosure receipt date, never the
  fiscal period.

### Repair 2: terminal consideration

Dividends alone do not repair a terminated security: the audit shows 300
missing 126-session endpoints on these names. Each of the 22 needs its
termination classified from DART before a label can span the event:
- merger (합병)
- comprehensive share exchange or transfer into a holding company (주식교환·이전)
- tender offer or cash-out
- delisting with or without final consideration, e.g. insolvency

Sources are the DART 주요사항보고서 for each type, 공개매수신고서 and 상장폐지
disclosures. From them, seal the exchange ratio or cash per share and the
successor code, as `data/replay-corporate-actions.json` already does for ESRX.
No type is assumed here.

The audit table `krTerminations` lists all 22 with KRX names and last sessions.
Name-stem guesses at successors were measured and rejected as unreliable
(e.g. 삼성물산 ↔ 삼성제약 share a stem and are unrelated).

### Also noted, not blocking

- KR membership is missing one monthly snapshot (2017-10). The strictly-earlier
  lookup carries September through 2017-11-01; longest gap 61 days.
- `NOT_CONTINUOUSLY_TRADED` runs 0.2–1.7% of member-dates a year (halts). These
  are excluded by the tradability guard, not a survivorship defect.

## What stays unchanged in v4

The v3 alpha-layer contract (`expectedNetAlpha > 0` against the benchmark's 0)
carries over, as do the separately reported probability and uncertainty, the
model family, features, horizons and costs, the computed dependency closure,
and the audit rules. v4 changes inputs, not design.
