# DART ownership history + replay integrity v1

Status: **BLOCKED_HISTORICAL_DEPTH** (2026-09-24). This is a data-foundation
repair, not an alpha experiment. No future return, IC, portfolio, or outcome
metric was computed, and ownership data is not wired into production scoring.

## Verified starting state

The latest `signal-history` artifacts were inspected directly, not inferred
from workflow logs. `ledger/dart-ownership-events/manifest.json` records a
119-security current-KR work list, 119 completed, 116 DART calls, 1,285 events,
zero refused rows, and `WORK_LIST_EXHAUSTED`. The three raw shards are 2024,
2025, and 2026; their receipt-date coverage is **2024-09-24 through
2026-09-23**. They contain 114 distinct DART corp codes. This proves only what
the bounded response returned, not that those issuers had no older filings.

The authoritative PIT membership ledger contains **260 KR securities**:
119 are in the collected current work list and **141 are historical-only
relative to that list**. The ledger describes 121 securities with no delisting
date and 139 departed securities; those counts differ from the dynamic current
119 by design. Historical issuer count and final DART mapping coverage cannot
be known until `corpCode.xml` is resolved during the first v2 collection run.
They are therefore reported as pending, never guessed.

## Historical collection universe and identity

`KR_OWNERSHIP_COLLECTION_UNIVERSE_V1` unions every KR security in
`signal-history:ledger/universe-history.json`. Dated KRX snapshot shards supply
the exact historical company names. Mapping is:

1. exact DART stock code;
2. otherwise, one unique exact Unicode-normalized company name;
3. otherwise, an explicit unresolved row.

There is no fuzzy mapping. Collection state is keyed by DART `corp_code`
(issuer), not ticker text, so a ticker change cannot create a second fetch.
The output records current-universe issuers, historical-only issuers, every
security identity attached to an issuer, mapping method/source, and all
unresolved candidates. A completed issuer is skipped under the same raw
contract. A raw-contract change is the only automatic refresh rule; failed
calls stay pending.

## Raw contract and PIT rule

The live probe artifact from Actions run `35964461327` confirms all three
previously discarded source fields are present: `ctr_stkqy`, `ctr_stkrt`, and
`report_resn`. `DART_OWNERSHIP_EVENTS_RAW_V2` preserves them verbatim as
`majorTransactionSharesRaw`, `majorTransactionOwnershipPctRaw`, and
`reportReasonRaw`, with a source-field map. No classification is derived from
`report_resn`.

`amendmentFlag` was misleading: the implementation only tested whether the
same issuer/reporter pair had an earlier receipt. New output calls this
`priorFilingExists`. The compatibility reader maps the old name for readers;
it does not mutate old shards.

The usable time is always `availableFrom`, derived from the public DART receipt
number. `eventDate`, `reportDate`, and `availableFrom` are separate. A missing
event/reference date remains null. Nothing is backdated to a transaction or
reference date. Old v1 shards remain readable; absent v2 fields remain null.
A repeat receipt may enrich a formerly missing field only with a value actually
returned by DART. Conflicting non-null observations fail closed.

## Why the history starts in 2024

The current evidence supports two independent causes:

- the original collector selected only the dynamic current KR universe;
- `majorstock.json` accepts only `corp_code`, exposes no start/end date, and on
  2026-09-24 returned an earliest receipt exactly two years earlier.

The collector did not apply a start-date filter. Its parser did not discard
older valid receipt dates. The official `list.json` filing-search route does
accept `corp_code`, `bgn_de`, `end_de`, and disclosure type. The probe now
checks that official index for older large-holding filings and records
`BLOCKED_HISTORICAL_DEPTH` when it finds them. Filing-index rows are not the
economic event schema; a deterministic official filing-document parser with
clear amendment semantics is required before they can be backfilled. This PR
does not guess that parser or scrape a third party.

## Exact replay-v16 conflict diagnosis

The stored replay-v16 policy has raw canonical config hash
`3f4663c1434bea4fa2a747c0c5629dbe9baac991e72fecd4ef28d20432649e95`.
After PR #151 it became
`cddf9de1ac3c47b6d45201a933f910c9eeee799d8b511f939b75502c9ca1f1b5`.
PR #152 did not change replay/config. The complete raw config difference is:

| Path | Sealed representation | Current representation | Classification |
|---|---|---|---|
| `ecos.KR.KTB_3Y` | `"817Y002"` | `{"seriesId":"817Y002","itemCode":null}` | `REPRESENTATION_ONLY_CHANGE` and `UNUSED_FOR_REPLAY` |
| `ecos.KR.CorpBond_3Y` | `"817Y002"` | `{"seriesId":"817Y002","itemCode":null}` | `REPRESENTATION_ONLY_CHANGE` and `UNUSED_FOR_REPLAY` |

`load_config` normalizes both spellings to the same object. Replay-v16 calls
the FRED macro path; neither replay generation nor portfolio audit imports or
calls `ecos_macro.py`. Therefore replay-v16 semantics did **not** change.

The old guard hashed all of raw `config.json`, so this representation-only,
unused difference caused `frozen replay policy/config differs from snapshot`.
The fix fingerprints a stable, normalized projection of the configuration
actually consumed by replay: universe/core, universe size, benchmark sources,
FRED macro series, long-term/replay policy, and portfolio/cost policy. The
inspectable legacy baseline is
`data/replay-policies/replay-v16.json`. Compatibility requires all of:

- the stored legacy hash matches that baseline;
- the baseline is for replay-v16;
- current replay-semantic configuration matches the full baseline object;
- every non-config policy field is unchanged.

The sealed manifest is not rewritten: a compatible extension preserves its
original policy bytes. A replay-relevant change still raises an input-version
conflict. Conflict artifacts now include a machine-readable classification and
key diff where available. No hash was whitelisted and no replay generation was
bumped.

## Readiness and remaining work

Final readiness: **BLOCKED_HISTORICAL_DEPTH**.

The schema, PIT contract, historical work-list construction, identity failure
handling, and resumable collector are ready. The data is not ready for an
ownership preregistration until: (1) the v2 workflow resolves and reports the
260-security union's issuer mapping/unresolved counts; (2) bounded backfill
finishes; and (3) the official filing-index depth probe determines whether an
official document route can recover older economic events. `BLOCKED_IDENTITY`
supersedes this status if unresolved historical identities remain material
after the mapping run. No effectiveness assessment belongs in this decision.
