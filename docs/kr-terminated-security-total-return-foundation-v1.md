# KR terminated-security total-return foundation (v1)

**Status: `BLOCKED_BY_SOURCE_ACCESS`.** This is a data-foundation build, not
an Alpha experiment. No historical outcome was computed. No return, IC,
calibration, hit rate, CAGR, Sharpe or Sortino was computed. No portfolio
backtest ran. `alpha-opportunity-model-v1/v2/v3` were not run, not modified,
and v3 stays sealed `BLOCKED_BY_DATA_INTEGRITY` exactly as merged (see
Validation below). This PR builds pipeline modules, an input-only inventory,
a probe, a collector, and one on-demand workflow — collection itself has not
run, because this development environment has no `DART_API_KEY`.

## Correction (execution-critical)

Two fixes to the design as first drafted, before any live run:

1. **Pagination.** The first draft's `list.json` calls carried no `page_no`
   and read only whatever a single `page_count=100` call returned — not
   sufficient for a 2013-2026 filing-history reconstruction, where a
   long-lived issuer can carry well over 100 disclosures of every kind, not
   only the ones this module matches. `fetch_all_pages` now walks every
   page the response's own `total_page` names, fails closed on inconsistent
   pagination metadata, and a ticker's collector state is marked `SUCCESS`
   only once every page has completed.
2. **Historical DART issuer identity.** The first draft resolved
   `stockCode -> corpCode` only by an EXACT CURRENT `corpCode.xml` stock
   code — too weak for a delisted security, since DART blanks a corp's
   `stock_code` field once it delists. `resolve_historical_dart_identity`
   now calls the repository's EXISTING historical resolver
   (`dart_ownership_universe._resolve_security`/`_unique_index`) directly:
   exact stock code, then a unique exact normalized historical company
   name, then unresolved — never fuzzy, never a name/ticker similarity
   guess, and the SAME resolver for both the probe and the collector.

Neither correction changes the foundation status: it stays
`BLOCKED_BY_SOURCE_ACCESS`, because this sandbox still has no
`DART_API_KEY` and neither fix could be exercised against the live API.

## Why this build exists

`alpha-opportunity-model-v3`'s sealed survivorship audit
(`docs/results/alpha-opportunity-model-v3-survivorship-audit.json`) found 22
KR securities that terminate inside the historical price sample with **zero**
dividend events on record, against 215 of 238 continuing names, and 300
missing 126-session endpoints. `docs/alpha-opportunity-v3-data-repair-plan.md`
named the cause: `pipeline/korea_prices.py` takes distributions from Yahoo
"if Yahoo happens to carry the name", and Yahoo does not carry delisted KR
tickers. So the names that leave the sample are price-return while survivors
and the `069500.KS` benchmark are total-return — a survivorship-correlated
basis gap, not a coverage gap. This build reconstructs, for those 22
securities, what a shareholder actually received: cash distributions, and
whatever a security became if it stopped trading.

## The 22-security inventory

Read from the sealed v3 audit's own `krTerminations` list — **never
hardcoded** — and verified in this PR to match the security codes named in
the originating task exactly (`tests/test_build_kr_termination_inventory.py
::test_committed_inventory_matches_the_sealed_survivorship_audits_22_names`).
`firstMembershipDate`/`lastMembershipDate` are newly computed here, from the
same sealed KRX top-120 monthly snapshots the v3 audit reads —
`lastTradingDate` is the v3 audit's own last-priced session, unchanged.

| Code | KRX name | First in top-120 | Last in top-120 | Last traded |
|---|---|---|---|---|
| 000030.KS | 우리은행 | 2014-12-01 | 2019-02-01 | 2019-02-12 |
| 000060.KS | 메리츠화재 | 2013-12-02 | 2023-02-01 | 2023-02-20 |
| 000830.KS | 삼성물산 | 2013-01-02 | 2015-09-01 | 2015-09-14 |
| 001300.KS | 제일모직 | 2013-01-02 | 2014-07-01 | 2014-07-14 |
| 002550.KS | KB손해보험 | 2013-08-01 | 2017-07-03 | 2017-07-20 |
| 003410.KS | 쌍용C&E | 2017-12-01 | 2024-07-01 | 2024-07-08 |
| 003450.KS | 현대증권 | 2013-01-02 | 2016-10-04 | 2016-10-31 |
| 003600.KS | SK | 2013-01-02 | 2015-08-03 | 2015-08-13 |
| 004940.KS | 외환은행 | 2013-01-02 | 2013-04-01 | 2013-04-25 |
| 008560.KS | 메리츠증권 | 2015-05-04 | 2023-04-03 | 2023-04-24 |
| 010520.KS | 현대하이스코 | 2013-01-02 | 2015-02-02 | 2015-07-14 |
| 010620.KS | HD현대미포 | 2013-01-02 | 2025-12-01 | 2025-12-12 |
| 011160.KS | 두산건설 | 2013-06-03 | 2013-07-01 | 2020-03-23 |
| 012510.KS | 더존비즈온 | 2018-07-02 | 2021-10-01 | 2026-07-14 |
| 037620.KS | 미래에셋증권 | 2013-02-01 | 2017-01-02 | 2017-01-19 |
| 042670.KS | HD현대인프라코어 | 2013-01-02 | 2023-08-01 | 2026-01-23 |
| 053000.KS | 우리금융 | 2013-01-02 | 2014-11-03 | 2014-11-18 |
| 057050.KS | 현대홈쇼핑 | 2013-02-01 | 2015-01-02 | 2026-07-16 |
| 067250.KS | STX조선해양 | 2014-04-01 | 2014-04-01 | 2014-04-14 |
| 079440.KS | 오렌지라이프 | 2017-06-01 | 2020-02-03 | 2020-02-13 |
| 115390.KS | 락앤락 | 2013-03-04 | 2013-03-04 | 2024-12-06 |
| 117930.KS | 한진해운 | 2015-03-02 | 2015-03-02 | 2017-03-06 |

**A measured, unexplained observation, published rather than smoothed over:**
several names' last top-120 membership date falls years before their last
traded session (e.g. 두산건설 last in the top-120 in 2013-07, last traded
2020-03-23; 락앤락 in the top-120 for one snapshot in 2013-03, last traded
2024-12-06). This is consistent with a security remaining listed and traded
for years after falling out of this study's top-120 research universe, but
this build never inspected price or return behaviour to say so — it is
reported as a date-arithmetic fact, nothing more.

## Sources actually verified in this environment

| Source | What was checked | Result |
|---|---|---|
| `opendart.fss.or.kr` (direct) | WebFetch of the developer guide | **Blocked by this sandbox's egress proxy** — the exact block `pipeline/dart_ownership_events.py`'s docstring already records for the same host |
| `list.json` (DS001, disclosure index) | Already used live in this repository (`probe_dart_ownership_events.official_filing_depth`) | **CONFIRMED** — `rcept_no`, `rcept_dt`, `report_nm`, `corp_code`, `corp_name`, `flr_nm` are real, working fields |
| `list.json` pagination fields | Field names (`page_no`, `page_count`, `total_count`, `total_page`) corroborated across independent third-party OpenDART client documentation (WebSearch); direct access to `opendart.fss.or.kr` blocked | **CORROBORATED, PENDING A LIVE PROBE** — `fetch_all_pages` fails closed if a live response does not carry them |
| `alotMatter.json` (dividend section) | Field names corroborated across independent third-party OpenDART client documentation (WebSearch) | **CANDIDATE, UNCONFIRMED** — `rcept_no`, `corp_code`, `corp_name`, `se`, `thstrm`, `frmtrm`, `lwfr`, `stock_knd`; promoted to confirmed only when `scripts/probe_kr_corporate_actions.py` runs against the real API |
| Merger / share-exchange / tender / delisting structured endpoints | Searched; no endpoint path or field map could be corroborated with confidence from this sandbox | **Not attempted.** No endpoint name is invented — see `pipeline/kr_corporate_action_events.py`'s module docstring. Discovery for these stays at the `list.json` report-name level only |
| `corpCode.xml` (DART issuer directory) | Same mechanism `dart_ownership_universe.py` already uses live | Requires `DART_API_KEY`, absent in this sandbox — **not resolved here** |
| KRX top-120 monthly snapshots | Already sealed on `signal-history` (`ledger/universe/kr/krx-universe-*.jsonl.gz`) | Read directly; used for the membership windows above |

Nothing above was fetched with a live key in this session. This PR's own
inventory artifact (`docs/results/kr-termination-inventory.json`) is
therefore honest that `dartIdentityStatus` is `DART_DIRECTORY_NOT_AVAILABLE`
for all 22 securities.

## Schemas

- **`pipeline/kr_corporate_action_events.py`** — raw disclosure discovery.
  `filing_index_rows`/`candidate_disclosures` read the confirmed `list.json`
  endpoint and classify a report by NAME keyword into one of `MERGER`,
  `SHARE_EXCHANGE_OR_TRANSFER`, `SPINOFF_OR_SPLIT_MERGER`,
  `BUSINESS_TRANSFER`, `TENDER_OFFER`, `DELISTING`, `DIVIDEND_DECISION` — a
  reading list for a human reviewer, **never** a termination-type verdict.
  `build_dividend_section_row` reads the candidate `alotMatter.json` fields,
  tagged `endpointConfidence: CANDIDATE_UNCONFIRMED` on every row.
  `amendment_chain` preserves every filing in a same-family, same-issuer
  chain, marking which are themselves amendments, without ever collapsing to
  "latest wins".
  - **Pagination.** `fetch_all_pages` walks a `list.json` result set to its
    own served `total_page`, deduplicating by receipt number and failing
    closed (`PaginationError`) on a missing or inconsistent pagination
    field, or the underlying result set changing mid-walk. Field names
    (`page_no`, `page_count`, `total_count`, `total_page`) are corroborated
    from independent third-party OpenDART client documentation — direct
    access to `opendart.fss.or.kr` is blocked from this sandbox's egress —
    at the same standard `ALOTMATTER_CANDIDATE_FIELDS` already uses; a live
    probe run is what confirms it.
  - **Historical DART issuer identity.** `resolve_historical_dart_identity`
    calls `dart_ownership_universe`'s existing `_resolve_security`/
    `_unique_index` directly (never a second, weaker resolver): exact stock
    code, then a UNIQUE exact normalized historical company name, then
    unresolved — never fuzzy, never a ticker/name similarity guess. Reusing
    the module-PRIVATE functions by name, rather than adding a public alias
    to `dart_ownership_universe.py`, is deliberate:
    `alpha-opportunity-model-v1` seals that file's exact bytes in its
    dependency closure, and even an additive edit to it would raise
    `SEALED_DEPENDENCY_CHANGED` on v1's next load.
- **`pipeline/kr_terminal_corporate_actions.py`** — the normalized terminal-
  consideration record, generalized from `data/replay-corporate-actions.json`
  's existing `REPLAY_CORPORATE_ACTIONS_V1` ESRX record. Ten action types:
  `MERGER_CASH`, `MERGER_STOCK`, `MERGER_CASH_AND_STOCK`, `SHARE_EXCHANGE`,
  `SHARE_TRANSFER`, `TENDER_CASH_OUT`, `HOLDING_COMPANY_REORGANIZATION`,
  `INSOLVENCY_DELISTING`, `VOLUNTARY_DELISTING`, `OTHER_TERMINATION`, plus
  `TERMINATION_TYPE_UNRESOLVED`. A record with a stated consideration term
  (a cash amount, a successor, an exchange ratio) but no citing DART receipt
  is **refused at construction** — it can never exist in an unvouched state.
  `chain_successors`/`successor_has_panel` build lineage for a future label
  engine (old security → successor → its own panel/further action) and
  compute no return.
- **`pipeline/kr_dividend_reconciliation.py`** — the repair plan's required
  cross-validation: matches DART and Yahoo dividend rows on continuing names
  and classifies every disagreement into `SOURCE_TIMING`, `AMENDMENT`,
  `GROSS_NET_REPRESENTATION`, `STOCK_VS_CASH_CLASSIFICATION`,
  `DATE_SEMANTICS`, `IDENTITY_MISMATCH`, or `UNRESOLVED`. Never reads a stock
  return.
- **`pipeline/kr_termination_inventory.py`** — the security × field
  completeness matrix and the overall foundation status, computed from
  evidence maps rather than a hardcoded assumption.
- **`data/kr-terminal-corporate-actions.json`** — the reviewed book, schema
  `KR_TERMINAL_CORPORATE_ACTIONS_V1`, currently **empty**: this PR resolves
  zero of the 22 securities' terminal consideration, because it collected no
  live data.

## PIT semantics

Every record kept by this build separates, and never conflates:

| Field | Meaning |
|---|---|
| `receiptDate` | public disclosure availability — the only PIT-usable date for a FEATURE |
| `decisionDate` | board/shareholder decision date, if DART states one |
| `recordDate` | entitlement record date (e.g. 배당기준일) |
| `exDate` | economic ex-date — see below |
| `effectiveDate` | merger/exchange/delisting/settlement economic date |
| `lastTradingDate` | |
| `paymentDate` | |

**`exDate` is never derived from `recordDate` by assumption.** No sealed,
dated Korean settlement-cycle rule exists anywhere in this repository, and
this sandbox could not reach an authoritative primary source to establish
one (`opendart.fss.or.kr` and the general web were searched; nothing citable
enough to seal as a dated rule was found). `kr_termination_inventory
.completeness_row` marks `exDateSemanticsResolved: BLOCKED` unless a
security's dividend evidence states `exDateSource: "DIRECT"` — an ex-date
DART's own disclosure stated outright, never one this codebase computed. If
a live probe finds DART states an ex-date directly for some disclosure
family, that becomes `DIRECT` evidence with no derivation involved; if not,
`DIVIDEND_EX_DATE_LINEAGE_BLOCKED` stays the status, per the originating
task's own instruction that this rule may never be guessed.

## Corporate-action semantics

Amendments are never collapsed: `kr_corporate_action_events.amendment_chain`
keeps every filing in a same-issuer, same-family chain and marks later ones
`isAmendment`. For realised reconstruction a later amendment may establish
the actual final terms; for PIT feature use, the later terms were not
knowable before their own receipt date — both facts are representable
because both dates are kept as separate fields on every filing.

Chained corporate actions are structurally supported:
`kr_terminal_corporate_actions.chain_successors` follows a security through
multiple hops (e.g. merger into a holding company, which itself later
undergoes a share exchange) and reports whether the final link has its own
price panel — never computing what any of it is worth.

## Completeness matrix

From the committed `docs/results/kr-termination-inventory.json`:

| Field | READY | BLOCKED / N/A |
|---|---|---|
| `terminationTypeResolved` | 0 / 22 | 22 |
| `dartIssuerResolved` | 0 / 22 | 22 |
| `dividendLineageResolved` | 0 / 22 | 22 |
| `exDateSemanticsResolved` | 0 / 22 | 22 |
| `terminalConsiderationResolved` | 0 / 22 | 22 (N/A while type is unresolved) |
| `successorResolvedWhereRequired` | 0 / 22 | 22 (N/A while type is unresolved) |
| `effectiveDateResolved` | 0 / 22 | 22 |
| `lastTradingDateResolved` | **22 / 22** | 0 |
| `rawEvidenceRetained` | 0 / 22 | 22 |
| `sourceProvenanceRetained` | 0 / 22 | 22 |

Only `lastTradingDateResolved` is ready everywhere, because that field came
from the v3 audit's own sealed price-panel measurement — nothing this PR
collected. Every field that depends on live DART access is `BLOCKED` on
every one of the 22 securities.

## Validation against continuing securities

`pipeline/kr_dividend_reconciliation.reconcile`/`reconcile_many` are built
and unit-tested against synthetic fixtures covering every disagreement
category (see `tests/test_kr_dividend_reconciliation.py`). Per the repair
plan's own rule, this reconciliation must be **run and pass** on continuing
names — where Yahoo already serves distributions — before any DART dividend
row is applied to one of the 22 names Yahoo cannot check. It has not been
run against real data in this PR, because no real DART dividend rows exist
yet to compare.

## Final data-foundation status

**`BLOCKED_BY_SOURCE_ACCESS`.** `DART_API_KEY` is not present in this
development environment, so `corpCode.xml`/`list.json`/`alotMatter.json`
could not be called live. Every one of the 22 securities has
`dartIdentityStatus: DART_DIRECTORY_NOT_AVAILABLE` and
`terminationType: TERMINATION_TYPE_UNRESOLVED` in the committed inventory —
an honest, input-only snapshot, not a partial result dressed up as more.

## Exact next step

1. Run `Collect KR terminated-security corporate actions`
   (`.github/workflows/kr-corporate-action-collection.yml`), `mode: auto`,
   with the real `DART` secret. It probes `list.json`/`alotMatter.json`
   first (`scripts/probe_kr_corporate_actions.py`) and only collects if that
   probe reports `SERVED`; a refusal fails the job closed, per
   `pipeline/collector_outcomes.py`.
2. A human reviews the collected disclosure-index rows
   (`ledger/kr-corporate-actions/` on `signal-history`) and, only from their
   actual content, adds entries to `data/kr-terminal-corporate-actions.json`
   — never inferred from a report-name keyword match alone.
3. Run `pipeline.kr_dividend_reconciliation.reconcile_many` on continuing
   names to validate the DART dividend derivation before applying it to any
   of the 22.
4. Re-run `scripts/build_kr_termination_inventory.py`, this time supplying
   the resolved `dart_identity`/`terminal_actions`/`dividend_lineage` maps,
   and check `foundation_status` again.
5. Only once every applicable completeness-matrix field reads `READY` may a
   `v4` preregistration be drafted over the repaired inputs — never before,
   and never by loosening this matrix's own rules.

## What this PR does not do

- Does not run `alpha-opportunity-model-v1/v2/v3`.
- Does not create a `v4`.
- Does not compute a forward return, Alpha, IC, Rank IC, calibration, hit
  rate, CAGR, Sharpe, Sortino, or portfolio backtest anywhere
  (`tests/test_kr_data_foundation_guardrails.py` checks every new module and
  script for exactly these tokens).
- Does not modify production Alpha scoring, the CHAMPION selector, or the
  live portfolio.
- Does not modify the sealed `alpha-opportunity-model-v1/v2/v3` specs —
  `tests/test_kr_data_foundation_guardrails.py::test_v3_seal_still_loads_
  unchanged` and `::test_v2_seal_still_loads_unchanged` reload both sealed
  specs by their own digest and pass.
