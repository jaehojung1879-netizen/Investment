# Alpha data foundation v2 — remaining gaps

> No gap here is closed by this PR speculatively — each entry states
> exactly what is built, what is unproven, and what the concrete next step
> is (always: run a probe, never: build a model).

## STRUCTURAL — blocks a genuinely new study until resolved

| Gap | What this PR built | What remains | Next step |
|---|---|---|---|
| KR investor-type flow access | `pipeline/kr_investor_flow.py`, `scripts/probe_kr_investor_flow.py`, session/cookie/Referer handling researched from `pykrx`'s own source | Live confirmation that the researched session mechanism actually works against KRX's current portal | Run `probe_kr_investor_flow.py` via `workflow_dispatch` in Actions (this sandbox cannot reach `data.krx.co.kr` at all) |
| KR ownership events (5%-rule) access | `pipeline/dart_ownership_events.py`, `scripts/probe_dart_ownership_events.py` | Live confirmation of the `majorstock.json` field set (corroborated from third-party libraries, not a live response) and that the existing DART key is subscribed to API group DS004 | Run `probe_dart_ownership_events.py` via `workflow_dispatch` |
| KR short-selling access | `pipeline/kr_short_selling.py`, `scripts/probe_kr_short_selling.py` | Live confirmation of the exact `bld=` codes for `MDCSTAT301`/`MDCSTAT305` (researched via WebSearch description, not a direct page read) | Run `probe_kr_short_selling.py` via `workflow_dispatch` |
| KR macro (ECOS) | `pipeline/ecos_macro.py`, `config.json` schema fix for `itemCode` | An `ECOS_API_KEY` repo secret; live confirmation of the 9 series IDs and the `817Y002` item-code disambiguation | Provision the key, then a smoke-test workflow run (not built in this PR — no key to test against) |
| Guru 13F automated backfill | `pipeline/guru_13f_store.py`, `scripts/backfill_guru_13f.py`, `scripts/probe_guru_13f_access.py` | Whether SEC's 13F bulk dataset / EDGAR submissions API is reachable from this repo's actual GitHub Actions runners (strong prior evidence it is blocked, same as Form 4/8-K/bulk-financial-statements, but not freshly re-measured for this specific endpoint) | Run `probe_guru_13f_access.py` via `workflow_dispatch` |

## NICE_TO_HAVE — improves a future study, not required to start one

| Gap | Status |
|---|---|
| Accounting-quality coverage for `fcfToNetIncomePct`/`capexIntensityPct` on the KR side (4.31%/7.74%) | Real, measured, structural — Korean filers omit these line items far more than US filers omit their equivalents. Not fixable by this project (it is a filer-disclosure fact, not a parsing gap). |
| Dividend-event ticker coverage (28.2%) | Partly genuine non-dividend-payers, partly a real gap (confirmed on KO: the TTM rollforward needs the concept present in the ANNUAL filing, which it sometimes is not). Not disentangled in this PR. |
| Macro-context US axis history depth | Depends entirely on however far back `regime.py`'s existing FRED/CBOE fetch already reaches — not separately measured here since `macro_context.py` calls that fetch, not a new one. |

## NON_BLOCKING — unrelated to the current research question

- Historical sector classification (both regions) — see
  `docs/alpha-data-foundation-v2-sector-context.md`. `HISTORICAL_SECTOR_CONTEXT_UNRESOLVED`,
  not pursued further in this PR; KRX's own classification is being replaced
  this month regardless.
- True market microstructure (bid/ask, tick data) — confirmed absent
  everywhere in this repository already (`alpha-information-inventory-v1`);
  nothing in this PR's workstreams needed it.

## What actually unblocks the STRUCTURAL row

Every STRUCTURAL gap above has the identical shape: **code is built and
unit-tested; live access is unconfirmed because this session's sandbox
cannot reach any of the target domains (KRX, DART's DS004 endpoint, ECOS,
SEC) at all** — confirmed directly (`curl`/`WebFetch` to
`opendart.fss.or.kr`, `data.krx.co.kr`, `ecos.bok.or.kr`, `www.sec.gov`,
`data.sec.gov` all fail at the egress-proxy level from this environment).
None of this blocks GitHub Actions, which already successfully reaches KRX's
Open API, DART's statement endpoint, and Finnhub in production today — SEC
specifically is the one vendor with independent, already-measured evidence
of being blocked from Actions too (`AGENTS.md`'s Vendor refusal invariants,
v2.9). The single next action for every row above is a `workflow_dispatch`
run of its probe script, not further code, and not a data-access workaround
invented here.
