# KR terminal-action reconstruction (v2)

**Status: `PARTIALLY_REPAIRED`.** This is a data-foundation build, not an
Alpha experiment. No historical outcome, return, IC, calibration, hit rate,
CAGR, Sharpe or Sortino was computed anywhere in this PR. No portfolio
backtest ran. `alpha-opportunity-model-v1/v2/v3` were not run and not
modified. `NOT READY_FOR_V4_PREREGISTRATION` — see "Final status" below.

This extends `kr-terminated-security-total-return-foundation-v1`
(merged, `jaehojung1879-netizen/investment#157`), never replaces it: every
module, schema field and test that PR shipped is unchanged and still passes.

## Section 0 — what was actually verified, not assumed

The task that produced this PR explicitly warned not to trust its own claims
about collection completeness without checking the real repository. Before
any code changed, the actual `signal-history` branch was read directly:

- `ledger/kr-corporate-actions/fetch-state.json`: **22/22** tickers
  `status: SUCCESS`, all `identityBasis: EXACT_STOCK_CODE`.
- `ledger/kr-corporate-actions/kr-corporate-actions-disclosures.jsonl.gz`:
  **451** rows, **145** amendments (32.2%).
- GitHub Actions run history for `kr-corporate-action-collection.yml`:
  two real runs (`36091590740`, `36094672107`), both `conclusion: success`,
  against `head_sha dd7ccb4` (PR #157's merge commit). The probe job's own
  log (read via `mcp__github__get_job_logs`, since this sandbox's egress
  cannot reach the Actions artifact's Azure blob storage — see "Known
  environment limitation" below) confirms `verdict: SERVED` and
  `alotMatter.json status=000 (정상) rows=15` for all 5 of the original
  probe's continuing-name sample.

**The prompt's claims were correct**: 22/22 collected, 451 matching
disclosure-index records, no pagination or identity failures. This is
recorded here as a VERIFIED fact, not an assumed one — the distinction the
task itself asked to be kept.

Disclosure-family breakdown across the 451 rows: `DIVIDEND_DECISION` 160,
`MERGER` 117, `SPINOFF_OR_SPLIT_MERGER` 50, `BUSINESS_TRANSFER` 56,
`SHARE_EXCHANGE_OR_TRANSFER` 39, `TENDER_OFFER` 28, `DELISTING` 13 (a
disclosure can match more than one family). Per-security receipt counts
range 1–50.

## Sections 1–5 — the research boundary and what this PR is not

Same non-negotiable boundary as v1, re-verified here: `tests/
test_kr_data_foundation_guardrails.py` greps every new module and script for
`select_portfolio_by_scores`, `replay_valuation`, `kelly_portfolio`,
`alpha_opportunity_v3_decision`, `compute_outcomes`, `sharpe`, `sortino`,
`cagr` and asserts none appear. `alpha-opportunity-model-v1/v2/v3`'s own
seal-reload tests (`test_v3_seal_still_loads_unchanged`, `test_v2_seal_
still_loads_unchanged`) pass unmodified.

This PR is a disclosure-METADATA-to-normalized-evidence pipeline, not a
content-extraction pipeline. Section 3's own rule — `list.json` rows are
disclosure metadata, not final economic terms, and a termination type,
consideration amount, ratio or successor identity may never be normalized
from a report NAME alone — is enforced structurally:
`build_kr_terminal_action_reconstruction_v2.build_terminal_actions` never
maps `disclosureFamilies` to an `actionType`; every one of the 22 securities
stays `TERMINATION_TYPE_UNRESOLVED` unless a human-reviewed entry exists in
`data/kr-terminal-corporate-actions.json` (still empty — no security has
been reviewed).

## Known environment limitation

This sandbox's egress cannot reach the GitHub Actions artifact's Azure Blob
Storage endpoint (`*.blob.core.windows.net`; confirmed via the agent proxy's
own status endpoint — `connect_rejected`, `gateway answered 403 to CONNECT
(policy denial)`), so the probe's own uploaded JSON artifact
(`kr-corporate-actions-probe.json`, containing the raw `alotMatter.json`
sample row and field-presence percentages) could not be downloaded directly.
Two things follow from this, both applied rather than worked around silently:

1. `scripts/probe_kr_corporate_actions.py` now also prints the
   `fieldsPresentPct` breakdown and one raw sample row directly to stdout
   (captured in the Actions job log, which — unlike the artifact — IS
   reachable via the GitHub API), so a future probe run's schema can be read
   without the artifact.
2. This sandbox also lacks `workflow_dispatch` permission on the GitHub App
   token available here (`403 Resource not accessible by integration`), so
   this PR could not trigger the new `collect-dividends` job itself. See
   "Exact next step" below.

## Sections 6–10 — termination-chain resolution and the schema extension

`pipeline/kr_terminal_corporate_actions.py`'s `KR_TERMINAL_CORPORATE_
ACTIONS_V1` contract is extended (never replaced — every v1 field, fixture
and test is unchanged):

- `considerationComponents` — a generalized list for a mixed cash-and-stock
  deal or more than one successor security (a split-merger into two
  entities). Each component cites its own DART receipt, the same
  construction-time rule the singular fields already enforced.
- `amendmentHistory` — the original filing plus every amendment, preserved
  as first-class data. `finalTermsReceiptNumber` names which entry's terms
  the record's own fields carry; an amended entry's `receiptDate` is its OWN
  PIT availability, never backdated to the original filing's.
- `oldIssuerCorpCode` / `successorIssuerCorpCode` — DART issuer identity,
  resolved only through `kr_corporate_action_events.resolve_historical_
  dart_identity` (the same resolver reused everywhere in this repair line).
- `sourceReceiptNumbers` — the UNION of every receipt a record cites
  (primary + every component + every amendment), for a caller that wants
  "every receipt this record's evidence rests on" without walking three
  separate lists.
- `unresolvedFields` — an explicit list, so a `TERMINATION_TYPE_UNRESOLVED`
  record never reads as silently complete.
- `chain_all_successors` — multi-successor reachability (cycle-safe, cycle
  detection reported rather than looping forever), generalizing
  `chain_successors`'s single-link-per-record walk.

None of this schema work was exercised against real DART filing content:
**no confirmed structured DART endpoint exists in this repository for
merger/tender/share-exchange economic terms**, and this sandbox could not
corroborate one (see "Source discovery" below). The schema is validated
entirely against synthetic fixtures (`tests/test_kr_terminal_corporate_
actions.py`'s new `v2 extension` sections: mixed cash-and-stock, two-
successor split-merger, amendment lineage, cycle rejection, unvouched-term
rejection at both construction and load time).

## Sections 3–4 — source discovery: what was probed, what was not guessed

`list.json` (DS001) remains the only CONFIRMED structured endpoint this
repair line has for the 22 securities' corporate-action history — metadata
only (receipt number, report name, filer, family match by keyword), never a
consideration term. `alotMatter.json` (dividend section) is now CONFIRMED
live-reachable (`status: 000`, real rows) but its exact `se` category
semantics remain undecoded — see "Dividend reconstruction" below.

A generic `document.xml` (DART's original-filing-document download
endpoint, corroborated with higher confidence than a disclosure-type-
specific endpoint because it takes no type-specific path — see `scripts/
probe_kr_corporate_actions.py`'s `probe_document_retrieval`) was added to
the probe, to be exercised on the NEXT live probe run (queued behind the
`workflow_dispatch` permission limitation above).

**No structured "주요사항보고서 주요정보" endpoint (merger/tender/share-
exchange/business-transfer decision, as distinct structured JSON) was
probed or guessed.** Corroborating a specific endpoint path or field map for
these from this sandbox was not possible (the same block `kr_corporate_
action_events.py`'s own module docstring already records for `opendart.
fss.or.kr` generally), and inventing one — the exact failure this
repository's vendor-refusal invariants (v2.9) and the workflow-hygiene
invariants' "a raw enum field is never translated on a guess" rule (v2.25)
both forbid — was not done. This is why termination type, terminal
consideration, successor identity and exchange ratio all stay `BLOCKED` for
every one of the 22 securities in this PR: the only structured source this
repository can currently confirm for them (`list.json`) is explicitly
insufficient for economic terms (Section 3), and no other structured source
was found without guessing.

## Sections 11–15 — dividend reconstruction

`alotMatter.json` is now confirmed live-reachable with real rows (`status:
000`, `rows: 15` per continuing name in the original 5-name probe sample).
Two things are built in this PR, and one is deliberately NOT:

- **Built:** `kr_continuing_dividend_sample.py` selects a real, 25-name
  continuing cross-validation pool deterministically from this repository's
  own `ledger/universe/kr` snapshot shards (rank-persistence in the top 120,
  excluding the 22 terminated securities and a name-pattern heuristic for
  preferred shares — published, not silently trusted) — never a second
  hand-picked list.
- **Built:** `scripts/collect_kr_dividend_sections.py`, a resumable,
  hard-call-budgeted collector for `alotMatter.json` across the 22
  terminated securities plus that 25-name pool, for every year 2013–2026
  (`reprt_code=11011`, annual), wired into `kr-corporate-action-
  collection.yml` as a third job (`collect-dividends`) rather than a
  parallel workflow file.
- **NOT built in this PR:** decoding `se` (DART's own dividend-row category
  label — DPS vs. yield% vs. payout ratio% vs. total amount, etc.) into a
  `DIVIDEND_AMOUNT_LINEAGE` reading. `kr_corporate_action_events.
  build_dividend_section_row` already keeps `se` fully RAW and refuses to
  interpret it (the same discipline `dart_ownership_events.py`'s
  `report_tp` handling uses, per the workflow-hygiene invariants v2.25) —
  and no live-observed `se` values exist yet for this study to build a
  confirmed decode table from. **This is the one concrete blocker on
  `DIVIDEND_AMOUNT_LINEAGE`**, resolved by running `collect-dividends` once
  (see "Exact next step").

`DIVIDEND_EVENT_DATE_LINEAGE` stays `DIVIDEND_EX_DATE_LINEAGE_BLOCKED`
regardless: no sealed, dated Korean settlement-cycle rule exists anywhere in
this repository, and this sandbox still could not reach an authoritative
source to establish one. `kr_termination_inventory.completeness_row`'s
`exDateSemanticsResolved` stays `READY` only for a directly-sourced ex-date
(`exDateSource: "DIRECT"`) — never derived from a record date — unchanged
from v1.

Dividend reconciliation (`pipeline/kr_dividend_reconciliation.py`, already
merged in v1) is unmodified: its `MISMATCH_REASONS` vocabulary (`SOURCE_
TIMING`, `AMENDMENT`, `GROSS_NET_REPRESENTATION`, `STOCK_VS_CASH_
CLASSIFICATION`, `DATE_SEMANTICS`, `IDENTITY_MISMATCH`, `UNRESOLVED`) is
what the next pass will reconcile the decoded `alotMatter` rows against
Yahoo's, once collection and decoding both land. No reconciliation was run
in this PR — there is nothing decoded yet to reconcile.

## Section 15 — price-adjustment semantics (input-only audit)

Not re-audited in this PR; v1's finding stands unchanged (no split/dividend-
adjustment semantics documentation was found or added in either PR). This
stays an open item for whichever pass first computes a return from KR price
data — flagged here rather than silently assumed resolved.

## Sections 19–21 — completeness matrix and foundation status

`kr_termination_inventory.py`'s matrix grows from 10 to the full 12 fields
Section 19 specifies (`terminalActionChainResolved`, `exchangeRatioResolved`
added, additive — every v1 field and fixture unchanged). Computed from the
REAL data above (`docs/results/kr-terminal-action-reconstruction-v2.json`,
built by `scripts/build_kr_terminal_action_reconstruction_v2.py`, verified
byte-identical across two runs):

| Field | READY / 22 |
|---|---|
| DART_IDENTITY | 22 |
| LAST_TRADING_DATE | 22 |
| RAW_EVIDENCE | 22 |
| (amendment/provenance retained) | 22 |
| TERMINAL_ACTION_CHAIN | 22 |
| TERMINATION_TYPE | 0 |
| TERMINAL_CONSIDERATION | 0 (NOT_APPLICABLE while type is unresolved) |
| SUCCESSOR_IDENTITY | 0 (NOT_APPLICABLE while type is unresolved) |
| EXCHANGE_RATIO | 0 (NOT_APPLICABLE while type is unresolved) |
| EFFECTIVE_DATE | 0 |
| DIVIDEND_AMOUNT_LINEAGE | 0 (NOT_COLLECTED — see above) |
| DIVIDEND_EVENT_DATE_LINEAGE | 0 (BLOCKED — no sealed ex-date rule) |

**Foundation status: `PARTIALLY_REPAIRED`.** Not `READY_FOR_V4_
PREREGISTRATION` (obviously — 8 of 12 fields are still blocked for every
security). Not `BLOCKED_BY_SOURCE_ACCESS` either: unlike v1, DART identity
IS resolved for all 22, and real disclosure evidence IS retained for all 22
— the remaining blockers are specific (no confirmed structured endpoint for
economic terms; dividend `se` semantics undecoded pending a collection run),
not "the source could not be reached at all." Per Section 21's materiality
rule, `terminalConsiderationResolved`/`successorResolvedWhereRequired`/
`exchangeRatioResolved` correctly read `NOT_APPLICABLE` rather than
`BLOCKED` while `terminationType` itself is unresolved (a type-dependent
field has nothing to be blocked ABOUT yet) — this is the existing v1 rule,
unchanged, applied to the two new fields too.

## Exact next step (operator action required)

This PR's own tooling cannot go further without one of two things:

1. **Preferred — run `collect-dividends` once.** Dispatch `Collect KR
   terminated-security corporate actions` (`kr-corporate-action-
   collection.yml`) with `mode: auto` (or `collect`) on this branch. The new
   third job collects real `alotMatter.json` rows for the 22 + the 25-name
   continuing pool. Re-running `scripts/build_kr_terminal_action_
   reconstruction_v2.py` against the resulting `signal-history` commit will
   then show real `se` values in the committed shard
   (`ledger/kr-corporate-actions/kr-dividend-sections.jsonl.gz`), letting a
   follow-up change build a `KNOWN_SE_RAW_VALUES` catalog from LIVE-OBSERVED
   values only (never guessed) and complete `DIVIDEND_AMOUNT_LINEAGE`.
2. **For terminal consideration / successor identity / termination type at
   all:** a human reviewer needs to actually read a sample of the 117
   MERGER-family / 39 SHARE_EXCHANGE-family / 28 TENDER_OFFER-family
   disclosures' real content (this repository's egress cannot reach
   `opendart.fss.or.kr` to fetch filing documents itself) and add entries to
   `data/kr-terminal-corporate-actions.json` via `TCA.build_record`. This
   PR's own probe extension (`probe_document_retrieval`) will report, on its
   next live run, whether `document.xml` raw-document retrieval is even
   reachable for automating part of that reading — that result is not yet
   known.

This PR could not trigger either action itself: the GitHub App token
available in this sandbox lacks `workflow_dispatch` permission (`403
Resource not accessible by integration`, confirmed), and no `DART_API_KEY`
or live-document access exists in this development environment for manual
filing review.

## Sections 24–25 — validation

Synthetic fixtures cover: mixed cash-and-stock consideration, a two-
successor split-merger, amendment history preservation and non-backdating,
unvouched-term rejection at both construction and load time (component and
amendment entries, not just the v1 singular fields), cycle-safe multi-
successor chain reachability, orphan successor links never silently
dropped, the continuing-name pool's determinism and preferred-share
exclusion, the dividend collector's hard call-budget ceiling (checked
before every ticker-year call), resumability (a budget-exhausted ticker
never marked complete, resumes from its first uncollected year), and — most
importantly — that no termination type is EVER assigned from a report name
alone (`test_no_termination_type_is_ever_guessed_from_a_report_name`), even
an unambiguous single-family match. Full list in `tests/test_kr_terminal_
corporate_actions.py`, `tests/test_kr_continuing_dividend_sample.py`,
`tests/test_collect_kr_dividend_sections.py`, `tests/test_kr_termination_
inventory.py` and `tests/test_build_kr_terminal_action_reconstruction_v2.py`.

`ruff check .`, `python -m compileall pipeline scripts`, and the full
`pytest -q` suite (2,237 passed, 1 skipped — pre-existing) all pass.

## Section 27 — data seal

`docs/results/kr-terminal-action-reconstruction-v2.json` (+ `.sha256`
sidecar) was built twice from the same real `signal-history` checkout
(commit `dfe78604db50a8010090824f2ead652ee74ba1af`) and diffed
byte-for-byte identical. This is the byte-stable, checked-in artifact
`tests/test_build_kr_terminal_action_reconstruction_v2.py`'s
committed-artifact tests read.

## Section 28 — answers

1. Did collection actually complete 22/22? **Yes**, verified against the
   real `signal-history` branch (not assumed from the prompt).
2. Real disclosure row count? **451**, `list.json`, all 22 tickers `SUCCESS`.
3. Termination-type breakdown? **0 resolved / 22 unresolved** — no
   confirmed structured source for economic terms exists yet.
4. Terminal-consideration breakdown? **0 resolved** (same reason).
5. Successor mappings? **0 resolved** (same reason).
6. Was fuzzy matching used anywhere? **No** — `resolve_historical_dart_
   identity` (exact stock code → unique exact normalized name → unresolved)
   is the only identity path used anywhere in this PR; `test_identity_
   resolution_never_uses_fuzzy_or_ticker_similarity` (v1, unchanged) still
   passes.
7. Effective dates resolved? **0/22** — depends on the same unresolved
   termination-type step.
8. Amendment chains found? **Yes** — 145 of 451 real disclosures (32.2%)
   are amendments; every terminated security's full chain (original +
   amendments) is captured in `amendmentHistory`, unflattened.
9. `alotMatter.json` verified fields? **Reachability and row COUNT
   confirmed live** (`status: 000`, 15 rows/name on the 5-name probe
   sample); the exact `se` CATEGORY values are not yet confirmed (Actions
   artifact unreachable from this sandbox — see "Known environment
   limitation"); the probe now also prints this to its job log for the
   next run.
10. Dividend amount lineage count? **0** — no `se` decode table exists yet.
11. Dividend event-date lineage count? **0** — no sealed ex-date rule
    exists (unchanged from v1).
12. Ex-date sourcing? Same rule as v1: `DIRECT` only, never derived.
13. Cross-validation method/mismatches? **Not run** — nothing is decoded
    yet to reconcile; the 5-name sample is expanded to a real,
    deterministic 25-name pool ready for the next pass.
14. Price-adjustment evidence? Not re-audited in this PR (v1's open item
    stands).
15. Double-counting risk? Unresolved — inherits v1's open item.
16. How many of 22 are fully ready? **0 of 22** end-to-end; **22 of 22**
    have resolved DART identity, retained raw evidence and a captured
    amendment chain (4 of the 12 fields).
17. Blockers? No confirmed structured DART endpoint for merger/tender/
    share-exchange economic terms (not guessed); `alotMatter.json`'s `se`
    category semantics undecoded pending one collection run;
    `workflow_dispatch` permission unavailable to this session.
18. Final status? **`PARTIALLY_REPAIRED`**.
19. `READY_FOR_V4_PREREGISTRATION`? **No.**
20–24. No forward return, no Alpha inspection, no model fit, no v1/v2/v3
    mutation, no production Alpha mutation — confirmed by `tests/
    test_kr_data_foundation_guardrails.py`'s token scan and the seal-reload
    tests, all passing.
25. Exact GitHub Action to run? `Collect KR terminated-security corporate
    actions` (`kr-corporate-action-collection.yml`), `mode: auto`, on this
    branch — see "Exact next step".
26. Exact `signal-history` commit(s) read? `dfe78604db50a8010090824f2ead
    652ee74ba1af` (disclosure index + fetch-state), same commit as its
    `ledger/universe/kr` shards used for the continuing-name pool.
27. Exact hashes/seals? `docs/results/kr-terminal-action-reconstruction-
    v2.json.sha256` — verified byte-identical across two independent runs.
28–30. See "Section 30 — final principle" below.

## Section 30 — final principle

This PR reconstructs **0 of 22** securities' economic terms — deliberately.
Every one of the alternatives considered (guessing a structured endpoint
name, inferring a termination type from a report name, decoding `se` from
unconfirmed third-party documentation) would have produced a plausible-
looking but fabricated 22/22. What is real: 22/22 DART identities resolved,
451 real disclosure receipts retained with full amendment lineage, a real
25-name continuing-sample dividend cross-validation pool, and one concrete,
named next step (run `collect-dividends` once) that unblocks dividend
amount lineage without guessing anything.
