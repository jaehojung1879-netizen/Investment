# KR accounting coverage repair v1 — final live audit

Date: 2026-09-28

This document records the final outcome-free audit of PR #161 after the real DART collection completed. It supersedes the **current-status / what-to-run-next** statements in `docs/kr-accounting-coverage-repair-v1.md`; that earlier document remains the chronological investigation record.

## 1. Scope and invariants

This PR is a KR accounting data-foundation repair only.

- No Alpha model or historical outcome study was executed.
- No forward return, IC, Rank IC, CAGR, Sharpe, hit rate or portfolio result was computed.
- No v1-v4 sealed research file or threshold was changed.
- The preregistered accounting coverage floor remains 20%.
- The repaired accounting dataset remains a new, unsealed candidate input. It is not retroactively substituted into v4.

The repaired candidate was built by audit code at commit `8170a8941c49a3f8213cf743ecd3cc69515a0d53`. The final raw-collection bookkeeping was pushed to `signal-history` at commit `fb6e83743fd8cdba647d1522a4645b662a9d5647`.

## 2. Collection completion

### Statement endpoint (`fnlttSinglAcntAll`)

Final persisted state:

- PIT KR universe tickers: 260
- exactly resolved DART issuers: 254
- raw statement filings stored: 8,826
- source-confirmed absences recorded: 2,604
- unresolved filings: 0
- unresolved issuer tickers: 6
  - `005385.KS`
  - `005387.KS`
  - `005935.KS`
  - `051905.KS`
  - `051915.KS`
  - `090435.KS`

The six unresolved issuer identities remain explicit missingness. This PR does not invent a preferred-share-to-issuer mapping.

The manifest still reports `remaining=521` and `datasetComplete=false`, but these are **not 521 uncollected historical filings relevant to the frozen research cutoff**. The final run exhausted the actual work list it could query and returned `CFS=013` and `OFS=013` for all 521 items (`calls=1,042`, `written=0`, `stopReason=WORK_LIST_EXHAUSTED`, `outcome=EMPTY_BUT_VALID`). They are:

- fiscal-2026 annual report (`11011`): 254 issuer slots
- fiscal-2026 Q3 report (`11014`): 254 issuer slots
- fiscal-2026 half-year report (`11012`): 13 issuer slots

The v4 data cutoff is 2026-09-14. The fiscal-2026 annual and Q3 slots are therefore future/current-year slots outside that cutoff. The 13 half-year slots were explicitly queried and DART returned source absence. The collector intentionally does not permanently settle a source absence until the filing deadline plus grace has passed. Re-running `raw-statements` now would only repeat these current-year 013 responses and is not required to close this repair.

### Original fiscal-2015 XBRL

The original-XBRL store is complete for its fixed work list:

- resolved issuers: 254
- `(ticker, stage)` pairs checked: 762
- records stored: 525
- remaining: 0
- `datasetComplete=true`
- classifications:
  - `XBRL_ZIP_SERVED`: 526
  - `FILE_NOT_AVAILABLE_014`: 81
  - `NO_ORIGINAL_FILING_INDEX`: 154
  - `AMBIGUOUS_REPORT_MATCH`: 1

The last full collector run used 1,369 source calls and ended with `WORK_LIST_EXHAUSTED`.

## 3. Canonicalization and merged candidate integrity

Canonical statement store:

- canonical-v2 records: 8,826
- refused records: 0
- legacy comparison filings: 4,373
- exact-label matched amounts disagreeing with legacy: 0
- receipt numbers changed versus legacy: 2

Important account-resolution evidence:

- net income (`당기순이익`) is recovered primarily through exact IFRS element identity in IS/CIS plus the legacy exact-label path; SCE component rows are not admitted as net income.
- operating cash flow is admitted only from cash-flow statements.
- assets and liabilities are admitted only from balance sheets.
- canonicalization uses exact element identifiers / exact legacy labels, never fuzzy text matching.

Merged repaired candidate:

- canonical-v2: 8,826 records
- original-XBRL: 525 records
- total: 9,351 records
- duplicate record IDs in the audit: 0
- multi-receipt filings in the audit: 0

The candidate snapshot identity recorded by the final audit is:

`sha256 = af642e7e79e9ba59ac6ee14faf033f4d63887188bab6506845c082e21dc3d1cc`

This hash identifies the repaired **candidate**, not a v5 sealed input.

## 4. Point-in-time integrity

The final audit remains outcome-free and uses filing metadata, account presence, receipt dates, PIT universe membership and backward-looking tradability only.

PIT protections verified by the repaired pipeline include:

- `availableFrom` derives from the filing receipt number/date, never collection date.
- future amendments are not treated as if they were visible at the original statutory deadline.
- current filings can be held back when only a later receipt is stored; the final audit records 289 held-back 2016 name-dates and 279 held-back 2025 name-dates for this reason.
- missing filings/accounts remain missing with explicit reason codes; they are not zero-filled or inferred from future filings.
- a DART absence is accepted only when both CFS and OFS were actually asked and both returned the source-absence status (`013`).
- non-absence errors remain unresolved/retryable rather than being relabeled as 013.

## 5. Final accounting coverage

The fixed accounting floor is 20%. Final repaired coverage is:

| Gate year | Feature | Before | Final repaired candidate |
|---|---:|---:|---:|
| 2016 | `ocfToNetIncomePct` | 3.99% | **47.52%** |
| 2016 | `assetGrowthPct` | 0.00% | **49.07%** |
| 2016 | `debtGrowthPct` | 0.00% | **49.07%** |
| 2025 | `ocfToNetIncomePct` | 17.42% | **88.44%** |
| 2025 | `assetGrowthPct` | — | **94.15%** |
| 2025 | `debtGrowthPct` | — | **94.15%** |

Final gate result:

- `accountingFloor = 0.20`
- `firstEvaluationYear = 2016`
- `failures = []`

The repair therefore clears the preregistered KR accounting coverage gate without lowering or retrospectively changing the threshold.

## 6. Remaining structural missingness

The audit does not claim 100% accounting coverage. Remaining gaps are disclosed and include:

- six unresolved preferred-share issuer identities;
- pre-service-history requirements around fiscal-2015 / earlier priors;
- filings genuinely absent according to DART;
- filings/accounts not visible by the relevant PIT date;
- account-level missingness in otherwise served filings;
- amendment timing where the statement endpoint exposes a later receipt rather than the original filing date.

These remain missing / blocked observations. They are not repaired with future information.

## 7. Original-XBRL confidence limitation

`pipeline/dart_xbrl_statements.py` intentionally keeps original-XBRL account extraction at `endpointConfidence=CANDIDATE_UNCONFIRMED`.

The real population evidence is strong: the repaired parser recovered at least one target account from 525 of 526 served ZIPs, and the final candidate passes the coverage gates. However, the values extracted from a fixed live sample have not yet been independently read end-to-end against the original source filing and promoted to a stronger source-confidence status.

This does **not** block merging PR #161 as a data-foundation repair and collection/canonicalization implementation. It **does** mean the repaired candidate should not be called a fully sealed v5 input yet. Before v5 execution, an outcome-independent source-value validation should be completed (or the v5 preregistration must explicitly define the treatment), and the exact repaired snapshot must then be frozen and hashed as a v5 input.

## 8. Final verdict

| Question | Verdict |
|---|---|
| Data-foundation repair code | **PASS** |
| Historically mature DART collection needed for the frozen research window | **PASS** |
| Original fiscal-2015 XBRL fixed work list | **PASS / complete** |
| PIT / missingness discipline | **PASS** |
| Canonical account mapping integrity | **PASS** |
| Fixed 20% KR accounting coverage gate | **PASS** |
| Outcome blindness of this repair | **PASS** |
| Full 2026 current-year manifest permanently settled | **NOT REQUIRED / still naturally open** |
| Repaired candidate already sealed for v5 | **NO** |

**Overall: `KR_ACCOUNTING_DATA_FOUNDATION_REPAIR_PASS`.**

No more `raw-statements` collection is required for this repair at the current research cutoff. The next research steps are separate from PR #161: finish the preregistered synthetic inference calibration from the design review, perform the fixed outcome-independent original-XBRL value check, freeze the repaired input snapshot, then create/seal v5 before any historical Alpha outcome execution.
