# kr-accounting-coverage-repair-v1 — why v4's KR accounting coverage gate fails, and what can repair it

Data-foundation and point-in-time accounting work only. **No Alpha model was
run. No forward-return label was built or read. No IC, return, CAGR, Sharpe,
calibration or hit rate was computed.** Every number below is feature
coverage or filing metadata.

- **Unchanged:** the sealed v1–v4 specs and the four sealed derivation
  modules. `dart_fundamentals.py`, `dart_derive.py`, `accounting_quality.py`
  and `alpha_opportunity_features.py` are hash-pinned by the v1 and v2 seals,
  so any in-place edit would break the v4 harness on load.
- **Unchanged:** the 20% accounting floor, every feature, horizon and
  threshold.

Machine-readable audit: `docs/results/kr-accounting-coverage-audit.json`
(summary) and `docs/results/kr-accounting-coverage-filings.jsonl.gz`
(13,520 ticker × fiscal-year × report-code rows).

## 1. What was audited, and how the audit is kept honest

`scripts/audit_kr_accounting_coverage.py` reads the same input snapshot that
the #160 execution froze:
- `signal-history` commit `4ea107ed`;
- input identity `674a8b97…`, verified by the harness's own
  `verify_input_identity`.

For every tradable KR name-date it:
- calls the sealed `alpha_opportunity_features.accounting_at` to decide
  whether each feature exists;
- then walks the same chain that `accounting_quality.derive_kr_fields` and
  `dart_derive.trailing_twelve_months` walk, to say why a feature is missing.

Two built-in checks stop it from drifting:
- It raises `AUDIT_DISAGREES_WITH_FEATURE_PATH` if its explanation ever
  contradicts the sealed function.
- It refuses to publish unless it reproduces #160's denominator (85,680
  member-dates, 85,132 tradable) and all four failing cells exactly. It
  does: 248/6,212, 0/6,212, 0/6,212 and 1,083/6,218.

Two runs produced byte-identical artifacts. The audit code commit is
`b204851e` and the tree was clean.

## 2. Root cause of each failure

### 2016 `assetGrowthPct` and `debtGrowthPct` — 0 of 6,212 each

Both fields are the same blocker. Growth compares a level with the same
report stage one year earlier. Primary blocker per name-date:

| Blocker | Name-dates | What it is |
|---|---|---|
| Prior is a fiscal-2015 quarterly, recorded absent | 2,039 | DART's statement endpoint served no 2015 Q1, H1 or Q3 report for any of 127 tickers. The absence log shows 381 of 381 answered "013" (§3). |
| Ticker never collected | 2,223 | The collector used today's universe, not the dated top-120 (§4). |
| No filing visible yet (Jan–Mar 2016) | 1,667 | No fiscal-2015 quarterlies exist in the store, and FY2015 annuals arrive at the end of March. |
| Prior is fiscal 2014 | 283 | This is the window between a FY2015 annual appearing and the 2016 Q1 report. DART serves statements only from 2015. |

Everything in 2016 growth depends on the prior year, and that prior year is
either 2015 quarterlies or pre-2015 data. Re-collecting the full universe
alone, even under the most generous accounting, would still give **0%** (the
collection-only upper bound).

### 2016 `ocfToNetIncomePct` — 248 of 6,212

A quarterly figure needs a trailing-twelve-month roll-forward from the prior
year's annual and same-stage reports. Blockers:

| Blocker | Name-dates |
|---|---|
| Prior same stage is a 2015 quarterly | 1,712 |
| Ticker never collected | 2,223 |
| No filing visible yet (Jan–Mar) | 1,667 |
| FY2015 annual not yet visible, because DART serves only its later amendment's receipt | 195 |
| Net income missing from the current filing | 132 |
| Operating cash flow missing from the current filing | 35 |

The collection-only upper bound is **9.43%**.

### 2025 `ocfToNetIncomePct` — 1,083 of 6,218

This failure is not about history. Missingness by category (primary
blocker, 5,135 missing name-dates):

| Category | Name-dates | Evidence |
|---|---|---|
| Net income not in the stored current filing | 3,706 | Collection kept only rows whose label exactly matched `당기순이익`, `당기순이익(손실)` and similar. Net income is missing from 1,586 of 3,260 stored quarterly filings, against 87 of 1,113 annual ones. The rate rises from 5% in 2016 to over 70% in 2024–2025. In 2025, 259 of the 274 quarterly filings without net income still carry revenue or operating income from the same income statement. So the income statement was served and the net-income row was dropped. |
| Ticker never collected | 751 | 595 common shares and 156 preferred shares. |
| Operating cash flow not in the stored current filing | 343 | Same mechanism, for the cash-flow line. |
| Prior same-stage net income missing (roll-forward dependency) | 270 | Same mechanism, one year earlier. |
| Prior annual not visible at the signal date | 62 | An amendment was served in place of the original filing (§5). |
| Prior filing absent (DART "013") | 3 | Primary source. |
| CFS/OFS selection | 0 | 4,306 CFS and 67 OFS filings; no blocker traces to the choice. |
| Amount-column semantics | 0 | Verified (§6). |
| Mixed receipt / receipt-date rejection | 0 | 0 mixed-receipt filings; 0 receipt/`availableFrom` mismatches. |

A per-ticker × current-filing breakdown is in
`blockedNameDatesByTickerAndFiling`. The collection upper bound is
**95.75%**. That is an upper bound, not a projection: a re-collected filing
may still lack the account.

**Whether the dropped rows really are net income cannot be proven from the
sealed store**, because the store did not keep them. The raw-row
re-collection in §7 is what settles it.

## 3. Fiscal 2015 quarterlies

**A. Were they ever requested?** Yes.
- `absent.json` holds 127 entries each for 2015 `11013`, `11012` and
  `11014`. Every one is recorded as "013".
- 81 fiscal-2015 annual reports were served; 46 were recorded absent.

**B. (Only asked if they were not requested.)** They were requested, so no
scheduling, resume or year-boundary cause applies.

**C. What did DART return?** It is not fully known.
- `collect_dart_fundamentals.fetch_one` returns the literal "013" whenever
  both CFS and OFS fail, whatever DART actually said. The recorded status is
  therefore a collector-synthesised value, not proof of DART's answer.
- The 127 × 3 all-absent pattern is uniform across tickers, while the same
  tickers' annual reports were served. That points strongly to the endpoint
  not serving 2015 quarterlies, not to a parser discarding them. No row was
  discarded: an empty response never reaches the parser.

**D. Do the original 2015 quarterly filings exist, with their receipt
numbers? Confirmed live.** GitHub Actions run
[36300578100](https://github.com/jaehojung1879-netizen/Investment/actions/runs/36300578100)
(2026-09-27, `data/kr-accounting-coverage-repair-v1` at `4965599c`, job
`kr-raw`, `target: raw-probe-2015`) ran the `raw-probe-2015` mode with a real
`DART_API_KEY` against the live API and pushed nothing to `signal-history`
(the `Collect a slice`/`Rebuild canonical`/`Commit & push` steps all show
`conclusion: skipped`, confirmed from the job's own step list). Artifact
`dart-fiscal-2015-probe`, sha256 `af7e3b58086b1004af59bdbf978d4e19e9a150fd212d51a639f3512a9a885c2e`,
64 calls, 8 tickers (`000030.KS`, `000060.KS`, `000080.KS`, `000100.KS`,
`000120.KS`, `000150.KS`, `000210.KS`, `000240.KS`). Measured, not assumed:

| | Result |
|---|---|
| `fnlttSinglAcntAll`, fiscal-2015 Q1/H1/Q3, both CFS and OFS | 013 on 24 of 24 real attempts (8 tickers × 3 stages), reconfirming §3C's mechanism with a live call rather than only the sealed store's history |
| `list.json`, same tickers/period | listed the original Q1/H1/Q3 filings with real receipt numbers for every one of the 8, e.g. `000030.KS`'s `분기보고서 (2015.09)`, receipt `20151116001418`; `000030.KS`'s Q1 also shows a real amendment, `[기재정정]분기보고서 (2015.03)`, receipt `20150529001078`, alongside its original, receipt `20150515002248` — confirming an original and its amendment are genuinely two different receipts on record |
| `fnlttXbrl.xml`, one 2015 Q3 package per ticker | **6 of 8 served a real ZIP** (153–170 KB: `000080`, `000100`, `000120`, `000150`, `000210`, `000240`; one at 85 KB: `000240`). **2 of 8 returned DART's own error envelope**, `<result><status>014</status><message>파일이 존재하지 않습니다.</message></result>` (147 bytes, confirmed non-ZIP): `000030.KS`, `000060.KS` |

**The consequence, stated precisely.** `fnlttSinglAcntAll` and the original
filing archive (`list.json` + `fnlttXbrl.xml`) are different endpoints with
different historical depth. Fiscal-2015 quarterlies are
`PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY` for the STATEMENT endpoint
specifically — never a blanket claim about DART. The original archive
serves most, not all, of the sample.

**What is still unconfirmed, stated just as precisely.** This session has
**not** read the contents of any served ZIP — `DART_API_KEY` is absent from
this development environment and `opendart.fss.or.kr` is blocked from this
sandbox's egress (unchanged from `AGENTS.md` v2.28). The live probe recorded
only the outer envelope (first two bytes `PK`, total size). Whether the four
gate accounts can actually be extracted from a served ZIP's real internal
XBRL structure is answered by `pipeline/dart_xbrl_statements.py`, built from
general XBRL/K-IFRS conventions and this repository's own already-confirmed
element identifiers — carrying `endpointConfidence: CANDIDATE_UNCONFIRMED`
throughout, the same tier `alotMatter.json` carried before its own live
probe. §7 names the exact next run that would promote it.

**Recoverable 2015 filings today: 0 confirmed, 6 of 8 sampled candidates.**
- A 2015 quarterly is never synthesised from a later report's comparative
  column. `frmtrm_*` is a restated comparative, and on a quarterly balance
  sheet it is the prior year-end, not the same quarter.
- An original filing is never read from its later amendment. §7's original-
  XBRL collector selects the earliest non-`[기재정정]` receipt matching a
  stage's own stated report name and period; a stage listed only as an
  amendment is its own recorded state
  (`ORIGINAL_NOT_LISTED_ONLY_AMENDMENT`), never silently upgraded.

With 2015 quarterlies, the 2016 upper bound rises to **55.1% for growth and
60.87% for `ocfToNetIncomePct`**. Jan–Mar 2016 and the pre-2015 priors stay
dark whatever is collected. That bound assumes every account is recoverable
from a served package; the CANDIDATE_UNCONFIRMED tier means the real number
could be lower.

## 4. Collection-universe gap

- `collect_dart_fundamentals.py` builds its work list from
  `universe.resolve(cfg)`, which is today's names.
- Only **126 of the 260** tickers ever in a KR top-120 snapshot have any
  DART filing. Tradable name-dates without any filing: 2,223 in 2016 and
  751 in 2025.
- **Preferred shares.** Their accounts are filed under the common-share
  issuer, and `corpCode.xml` lists no preferred codes. They account for 216
  name-dates in 2016 and 156 in 2025. They stay unresolved by the new
  collector, because mapping a preferred share to its issuer is an identity
  rule that needs its own preregistered decision.

## 5. Amendments are served in place of originals

- **1,208 of 4,373** stored filings (27.6%) carry a receipt date after
  their statutory deadline. `fnlttSinglAcntAll` serves the latest
  amendment's receipt number.
- The record ID is ticker:year:code with no receipt number, so the original
  filing's visibility date and content are not in the store.
- Example: 010130.KS (Korea Zinc). All 14 filings from FY2022 through 2025
  Q3 are dated 2026-08-13. None is visible anywhere in 2023–2025, so its
  features freeze on the 2022 Q3 report.
- Counts: 239 collected 2025 name-dates, and 51 in 2016, run on a current
  filing held back this way.

This is **PIT-honest**: the amended numbers were not public before the
amendment. But it costs coverage, and re-collecting from the same endpoint
cannot recover the originals. Only the original XBRL could, as in §3.

The module docstring's claim that "restatements arrive as their own filing"
is false for this implementation. That is recorded here; the sealed module
is not edited.

## 6. Derivation audit (measured on the stored filings)

| Check | Result |
|---|---|
| `trailing_twelve_months` roll-forward | Correct as `FY(Y-1) - cum(Y-1, s) + cum(Y, s)`. |
| Income-statement column | Every quarterly IS/CIS net-income row carries `thstrm_add_amount`. |
| Cash-flow column | Cash flow has one cumulative column. Q3/FY operating-cash-flow median is 0.662 over 778 pairs, and net income 0.833 over 432 pairs. Standalone quarters would sit near 0.25. |
| `level_amount` | Reads balance-sheet `thstrm_amount`, the period-end level. Correct. |
| Same-report-code growth | Correct semantics. |
| Indexing | 0 duplicate IDs. Restatements are not stored separately (§5). |
| `visible_filings` / strict `availableFrom < as_of` | Correct. The KR receipt-consistency check rejects 0 filings. |
| **Row-selection defect** | `build_record` keeps the first label match in any statement. In 56 filings net income came from the statement of changes in equity (SCE), where a row is one equity component. The canonical rule refuses SCE. On pseudo-raw rows rebuilt from the legacy store, this lowers 2016 `ocfToNetIncomePct` from 3.99% to 3.88% (7 name-dates). It changes nothing in 2025 and no other amount. |

No derivation was changed: all four modules are sealed.

## 7. The repair built here (new modules only)

**`pipeline/dart_raw_statements.py` and
`scripts/collect_dart_raw_statements.py`**
- Re-collect DART statement responses whole: every row, and every CFS/OFS
  attempt with DART's own status and message.
- Cover all 260 point-in-time tickers. Delisted issuers are resolved by the
  repository's historical identity resolver.
- `availableFrom` comes only from the served `rcept_no`. The run is
  append-only, budget-checked before every call, and fails closed on a
  refusal.
- **Only DART's own "no data" counts as absence.** A filing is recorded in
  `absent.json` only when both CFS and OFS answered 013. It is skipped
  permanently only once, in addition, its deadline plus grace has passed;
  `settled()` re-derives both conditions from the stored attempts.
  - 013 is the only status this repository has evidence means "no such data"
    for statement requests.
  - 014 appears only as a label in the status table, with no evidence of what
    it means for `fnlttSinglAcntAll`, so it is not treated as absence.
  - 100, 900, 014, a 000 with no rows, a transport failure and any unknown
    code go to `unresolved.json` with every status and message, and are
    retried next run.
  - 800 (maintenance) and 021 (company-count limit) stop the run as a
    refusal. Nothing is settled either way.
  - A first draft of this collector let 100/800/900/021 fall through to a
    settled absence, and one test asserted it. That was corrected before any
    collection ran.

**`pipeline/dart_canonical_accounts.py` and
`scripts/build_kr_canonical_filings.py`** rebuild records the sealed feature
path reads unchanged.

- **Element-ID rule.** Only for the four gate accounts, a row is also
  admitted when its IFRS element ID is the one those accounts carry under an
  exact label match. Examples: `ProfitLoss` in IS/CIS, and
  `CashFlowsFromUsedInOperatingActivities`.
- **Evidence for the rule.** In the sealed store, 2,700 label-matched
  net-income rows use only `ProfitLoss` in IS/CIS. The exceptions are 16
  non-standard-code rows, CF rows under DART's own
  `dart_ProfitLossForStatementOfCashFlows`, and SCE rows. Full table:
  `accountIdsUnderExactLabelMatch`.
- **Never mapped:** attributable-to-parent profit, cash generated from
  operations, current assets or liabilities, SCE rows, component rows.
  Disagreeing candidates are left out as AMBIGUOUS.
- **Other accounts:** the legacy rule, called unchanged.
- **Review report.** The rebuild publishes every (statement, label, ID)
  combination the element rule admitted, and compares the result with the
  legacy store.

**`pipeline/dart_xbrl_originals.py`** — discovery and classification, network-free.
- `select_original_filing` picks the earliest non-`[기재정정]` `list.json` row
  matching a stage's own stated report name and period; a stage listed only
  as an amendment, only ambiguously, or not at all is its own recorded state
  (`ORIGINAL_NOT_LISTED_ONLY_AMENDMENT` / `AMBIGUOUS_REPORT_MATCH` /
  `NO_ORIGINAL_FILING_INDEX`) — never a guess.
- `classify_xbrl_response` reads only the served bytes' own shape: a ZIP
  signature, or DART's own `<result><status>014</status>…</result>` error
  envelope (pinned to the exact 147-byte body the live probe captured).

**`pipeline/dart_xbrl_statements.py`** — parsing, `CANDIDATE_UNCONFIRMED`.
- Matches XBRL facts by exact QName local name, namespace-agnostic, derived
  from the same `ELEMENT_RULES` the canonical rebuild already uses — never a
  fuzzy label, never `ProfitLossAttributableToOwnersOfParent` for net income
  or `CurrentAssets` for total assets.
- A flow account (net income, operating cash flow) is read only from a
  DURATION context running from the fiscal year's own start to the filing's
  period end — the cumulative reading, stored under exactly the amount field
  `dart_derive.cumulative_amount` already reads for that statement — never a
  same-named concept's standalone-quarter context.
- Two same-named facts surviving that window with disagreeing values is
  `AMBIGUOUS`; no parseable XML entry is `NO_PARSEABLE_XML_ENTRY`. Neither is
  ever resolved by picking one.
- Every record carries `endpointConfidence: CANDIDATE_UNCONFIRMED`, because
  this session has never read a real served ZIP's contents (§3D). A unit
  test proves the resulting record actually supplies `dart_derive`'s missing
  2015-same-stage prior for a 2016 TTM roll-forward, end to end, unmodified.

**`scripts/collect_dart_xbrl_originals.py`** — the real collector, not yet run.
- For every stage of every resolved PIT ticker: `list.json` discovery (fully
  paginated), original-filing selection, `fnlttXbrl.xml` fetch, classify,
  extract. Append-only, keyed ticker × stage, budget-checked before every
  call (list.json pages and the XBRL fetch alike).
- Stores the four candidate accounts plus the served ZIP's SHA-256 and every
  entry's name — never the raw ZIP bytes themselves in git. `--dump-dir`
  writes the raw ZIPs locally for direct human inspection (never committed).
- Every classification is kept in `fetch-state.json`, including the ones
  that store nothing (`ORIGINAL_NOT_LISTED_ONLY_AMENDMENT`, `FILE_NOT_
  AVAILABLE_014`, …), so a re-run never silently re-asks a settled case and
  a reviewer can see exactly why any given stage has no record.

**`scripts/merge_kr_candidate_snapshot.py`** — combines `kr-canonical-v2`
(other years) with `kr-xbrl-original` (fiscal-2015 quarterlies) into one
candidate directory the sealed feature path reads unchanged; raises rather
than silently picking a side if the two sources ever describe the same
filing (they should never overlap by construction).

**`fundamentals.yml` job `kr-raw`**
- Manual dispatch only; the schedule can never take it.
- Reads the sealed commit. Writes only `ledger/fundamentals/kr-raw`,
  `kr-canonical-v2`, `kr-xbrl-original` and `kr-candidate-merged`, never
  `ledger/fundamentals/kr`.
- `target: raw-probe-2015` now tests all three stages against BOTH
  endpoints (not one Q3 sample) and, for a served ZIP, best-effort reports
  which of the four accounts the `CANDIDATE_UNCONFIRMED` parser recovers —
  still writes nothing to the store.
- `target: raw-xbrl-2015` runs the real collector, merges with any existing
  `kr-canonical-v2`, and audits the merged candidate.
- `target: raw-statements` now also merges in `kr-xbrl-original` before
  auditing, if that store exists.

**Coverage after repair: not yet measured.** Neither `raw-statements` nor
`raw-xbrl-2015` has been run — only `raw-probe-2015` has (§3D), and it
writes nothing. Before and upper bounds, by gate year:

| Year | Feature | Before (measured) | Upper bound, collection | Upper bound, collection + 2015 quarterlies | After |
|---|---|---|---|---|---|
| 2016 | ocfToNetIncomePct | 3.99% | 9.43% | 60.87% | pending run |
| 2016 | assetGrowthPct | 0.00% | 0.00% | 55.10% | pending run |
| 2016 | debtGrowthPct | 0.00% | 0.00% | 55.10% | pending run |
| 2025 | ocfToNetIncomePct | 17.42% | 95.75% | 95.75% | pending run |

**Will the 20% gate pass after repair?**
- **2025:** likely, if the dropped rows are net income. This is decided by
  the "after" audit, not by this table.
- **2016:** **cannot pass by collection alone**, since growth's bound is 0%.
  Passing needs both `raw-xbrl-2015` to recover 2015 quarterlies AND their
  extracted accounts to leave `CANDIDATE_UNCONFIRMED` and clear the 20%
  floor — neither is measured yet.

## 8. Decision classification

| Blocker | Class |
|---|---|
| Ticker never collected (common shares) | `DATA_COLLECTION_GAP_REPAIRABLE` |
| Net income / operating cash flow dropped at collection (label outside the alias list) | `PARSER_OR_DERIVATION_DEFECT_REPAIRABLE` (pending raw-row evidence) |
| Net income taken from SCE component rows | `PARSER_OR_DERIVATION_DEFECT_REPAIRABLE` (fixed in the canonical rule) |
| Fiscal-2015 quarterlies from the statement endpoint | `PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY` for `fnlttSinglAcntAll` specifically — confirmed live (§3D) |
| Fiscal-2015 quarterlies from the original filing archive | `DATA_COLLECTION_GAP_REPAIRABLE` for 6 of 8 sampled (`fnlttXbrl.xml` serves a ZIP); `PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY` for 2 of 8 (014); whether the four accounts actually extract from a served ZIP is `UNRESOLVED` (`CANDIDATE_UNCONFIRMED`, §7) |
| Pre-2015 priors (Jan–Mar and Apr–May 2016) | `PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY` |
| Amendments served in place of originals | `PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY` via the statement endpoint; `DATA_COLLECTION_GAP_REPAIRABLE` via the original-XBRL path where a served ZIP exists |
| Preferred shares without an issuer mapping | `UNRESOLVED` (needs a preregistered identity rule) |
| DART "013" on a due filing (3 name-dates in 2025) | `PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY` |

**Overall:**
- **2016:** `UNRESOLVED`, pending `raw-xbrl-2015`'s real recovery rate and
  whether the recovered accounts clear the 20% floor. Not
  `PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY` outright any more: the
  live probe found a genuine second route for most of the sample.
- **2025:** `PARSER_OR_DERIVATION_DEFECT_REPAIRABLE` plus
  `DATA_COLLECTION_GAP_REPAIRABLE`, subject to the `raw-statements` run.

## 9. Versioning consequence

- **What v4 was run against.** v4 executed on signal-history `4ea107ed` with
  28 sealed raw blobs.
- **What this PR changed.** None of those blobs. The repaired data lands in
  new directories, so the v4 input identity still verifies. Running v4 on the
  repaired store would require changing what the harness reads, and that is
  refused.
- **A repaired dataset is a new input snapshot.** It must not be run under
  v4.
- **A new preregistration is required.** The expected next step is to freeze
  the repaired snapshot, then create `alpha-opportunity-model-v5` with the
  same economic and model design. Only one thing moves: the KR fundamentals
  input snapshot and its canonicalisation contract. v5 would then execute
  only after its own seal.
- **What v5 must also decide, unless a separate preregistered reason
  applies:** whether the preferred-share issuer mapping and the SCE exclusion
  count as input definitions.
- **Not implemented here:** v5 itself.

## 10. What to run next

The job is in `fundamentals.yml` on this branch. It can be dispatched from
the branch before merge.

1. ~~`target: raw-probe-2015`~~ **Done.** Run
   [36300578100](https://github.com/jaehojung1879-netizen/Investment/actions/runs/36300578100),
   64 calls, wrote nothing, artifact `dart-fiscal-2015-probe` uploaded.
   Evidence is in §3D. The probe now also tests all three stages (not one
   Q3 sample) and, for a served ZIP, best-effort reports which of the four
   accounts the `CANDIDATE_UNCONFIRMED` parser recovers — re-running it is
   optional, useful only for a wider sample than 8 tickers or to review
   more real ZIP structure via `--dump-entries`.
2. **`target: raw-xbrl-2015`**, other inputs empty (`max_calls` 1,800,
   `max_minutes` 290). Not yet run. This is the collector that would
   actually recover fiscal-2015 quarterlies where `fnlttXbrl.xml` serves
   them. Its job summary publishes real classification counts (how many
   stages got `XBRL_ZIP_SERVED` vs `FILE_NOT_AVAILABLE_014` vs the
   selection-side codes) and the merged candidate's real "after" coverage
   for 2016 — the first real measurement of whether original-XBRL recovery
   actually clears the 20% floor, since every number before this is an
   upper bound.
3. **`target: raw-statements`**, `raw_years`/`max_calls`/`max_minutes`
   empty. Re-run until the log reports `"datasetComplete": true` (2015 now
   asks only for the annual report there, so this is fewer calls than
   before — about 12,140 filings over 7–9 runs). If step 2 already ran,
   this step's audit reads the merged candidate (canonical-v2 + xbrl-
   original) automatically; if not, it audits canonical-v2 alone, exactly
   as before.

Review before running step 2: `pipeline/dart_xbrl_statements.py`'s account
extraction has never been exercised against a real served ZIP in this
session (§3D, §7). Its logic is built from confirmed element identifiers and
general XBRL convention, marked `CANDIDATE_UNCONFIRMED`, and tested only
against synthetic fixtures. Running step 2 with `--dump-dir` locally, or
reading `--dump-entries`'s output from an expanded probe run, is how to
inspect real structure before trusting its output.
