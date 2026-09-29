# KR repaired accounting snapshot v1 and semantic contract

A data-foundation freeze. **No Alpha model, forward label, return, IC or outcome
artifact was read or run**, and no accounting record was repaired, refetched,
reselected or tuned. The machine-readable freeze is
`research_specs/kr-repaired-accounting-snapshot-v1.json`.

## The frozen input

The `kr-candidate-merged` directory at `signal-history` commit
`fb6e83743fd8cdba647d1522a4645b662a9d5647`: `kr-canonical-v2` (raw DART statement
rows, canonicalised) united with `kr-xbrl-original` (fiscal-2015 Q1/H1/Q3 original
XBRL) by `scripts/merge_kr_candidate_snapshot.py`.

| Item | Value |
|---|---|
| Records | 9,351 (8,826 canonical-v2 + 525 original XBRL) |
| Tickers with a record | 250 of the 260 PIT-universe tickers |
| Fiscal years | 2015-2026 (2026 partial) |
| availableFrom range | 2015-04-29 to 2026-09-16 |
| **Frozen content SHA-256** | `e0199d98679357f405de9a95a4091045db814d65af61e2c698af1a70d54fda58` |
| Candidate identity SHA-256 | `af642e7e79e9ba59ac6ee14faf033f4d63887188bab6506845c082e21dc3d1cc` (the candidate validated by v1-v3) |

The content hash covers the decoded records sorted by id, so it does not depend on
gzip bytes or input order. The candidate identity is the v1-v3 convention (hash of
shard-file -> git blob SHA-1) and ties this snapshot to the validated candidate.
Regenerating the merge from its two sources reproduces every shard byte for byte.
The manifest also pins the blob SHA-1 of the merger, canonicalisation, derivation
and reader code; editing any of them requires a new snapshot version.

Recreate: `git fetch --no-tags --depth=1 origin fb6e83743fd8cdba647d1522a4645b662a9d5647`
then `python scripts/build_kr_repaired_accounting_snapshot_manifest.py --from-git --verify`.

## Semantic contract (KR_ACCOUNTING_SEMANTIC_CONTRACT_V1)

- **Point in time.** `availableFrom` is the date in the head of the DART receipt
  number. A filing is usable for as-of date D only if `availableFrom < D` and every
  receipt's date prefix equals `availableFrom`. Two records fail the second test and
  are never visible.
- **Filings and amendments.** One record per ticker x fiscal year x report code. The
  JSON endpoint serves the latest amendment's receipt, so 2,639 records carry a later
  date than their statutory deadline: point-in-time honest, but the original earlier
  values are not in the snapshot. The 525 XBRL records come from the original filing
  (amendments excluded). Restatements are not modelled.
- **CFS vs OFS.** Consolidated first; separate only if consolidated was not served
  (fsDiv CFS 8,479 / OFS 347). XBRL records choose per account (unqualified, then
  consolidated over separate) and record `statementBasis`. Bases are recorded, not
  harmonised, and downstream code does not condition on them.
- **Periods.** 11013 Q1 (3 months), 11012 half (6), 11014 Q3 (9), 11011 annual (12).
  Balance-sheet accounts are period-end levels. Flows are cumulative year-to-date:
  annual `thstrm_amount`; quarterly IS/CIS `thstrm_add_amount`; cash flow's single
  column. TTM = FY(Y-1) - cumulative(Y-1, stage) + cumulative(Y, stage), or None. Never
  annualised.
- **Duplicates.** Record ids are unique (9,351 of 9,351). An id in both sources makes
  the merger raise; ambiguous candidate rows omit the account; component rows are
  never totals. No record has more than one receipt.
- **Source precedence.** The sources are disjoint, so none is applied: XBRL covers
  only FY2015 Q1/H1/Q3, canonical-v2 everything else. A collision is an error.
- **Missing values.** An absent account is absent (None), never 0 and never imputed.
  400 records lack at least one of the four families.
- **No look-ahead.** Only visible filings; priors only from the same visible set;
  share counts carry forward from earlier filings only; no forward fill; no
  whole-history derivation followed by filtering.
- **The four families.** Assets: IFRS `Assets`, BS, period-end total. Liabilities:
  IFRS `Liabilities`, BS, period-end total. Net income: IFRS `ProfitLoss` (IS/CIS),
  including non-controlling interests, year-to-date, never the parent-attributable
  element. Operating cash flow: IFRS `CashFlowsFromUsedInOperatingActivities` (CF),
  year-to-date, never the cash-generated-from-operations subtotal. Full KRW, no scaling.

The tests enforce these through the real code (visibility, column choice, rollforward,
carry-forward, element rules, collision, first-write-wins) rather than only prose.

## Known limitations

- Source validation (v3 PASS) covers the 60-fact fiscal-2015 original-XBRL sample by
  concept identity, not statement membership. The 8,826 canonical-v2 records were not
  source-validated by it.
- 6 preferred-share tickers are unresolved identities and 4 more resolved issuers have
  no record; the raw collection reported `datasetComplete=false`, 521 unsettled items
  and 2,604 recorded source absences.
- DART serves statements from 2015, so fiscal-2015 quarterlies exist only through XBRL
  and 2016 growth features stay structurally unavailable.
- Amendments overwrite in place; no restatement history. 400 records miss a family.
- This freezes an input, not a study. No Alpha-v5 design is implied.
