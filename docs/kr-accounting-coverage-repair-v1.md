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

**E. Was the CANDIDATE_UNCONFIRMED parser actually correct on served
content? Measured, and a real defect found and repaired.** GitHub Actions
run [36304452901](https://github.com/jaehojung1879-netizen/Investment/actions/runs/36304452901)
(2026-09-27, this branch at `b3e02b8f`, `--dump-entries`, a real re-run
after a first attempt timed out on `corpCode.xml`) ran the expanded
all-stage probe against the live API and printed its own structured JSON to
the job log (artifact upload could not be downloaded from this sandbox —
blob storage stays blocked, per `AGENTS.md` v2.29 — so the job log was read
directly and parsed). Measured, not assumed: **18 of 24 sampled 2015 Q1/H1/Q3
packages served a real ZIP** (6 of 24 returned DART's confirmed 014
envelope), and of those 18, the first cut of the parser resolved only **3**
and read **15** as `AMBIGUOUS` — an all-or-nothing pattern per issuer (every
stage of a given ticker either all resolved or all ambiguous), pointing at a
filer-level XBRL-authoring style rather than a per-account or per-quarter
cause.

The mechanism, read from the real served content: the parser's context
window match (`instant`/`startDate`/`endDate` only) never inspected a
context's own `<scenario>`/`<segment>` dimensional qualifier, and DART's
general-corp filers from this era tag multiple contexts with the exact same
literal dates, distinguished only by such a qualifier. Three axis families
were actually observed (byte-exact XML quoted in
`tests/test_kr_accounting_coverage_repair.py`):
- `ifrs:ConsolidatedAndSeparateFinancialStatementsAxis`
  (`ConsolidatedMember`/`SeparateMember`) — the same Consolidated-vs-Separate
  distinction this repository's PIT-fundamentals invariants already resolve
  for the JSON endpoint (prefer Consolidated), reused rather than re-decided.
- `dart-gcd:PeriodAxis` (`PeriodCoveredbyLastFiscalYearMember` /
  `PeriodCoveredbyTheYearBeforeLastFiscalYearMember`) — every member actually
  observed names a PRIOR period; the axis reuses one literal boilerplate
  date range across a comparative table, so the member's own name is the
  only real signal.
- `ifrs:ComponentsOfEquityAxis` — an SCE component row (one real context
  carried BOTH this axis and the Consolidated one at once), exactly the
  shape `dart_canonical_accounts` already refuses for the JSON-row path.

`pipeline/dart_xbrl_statements.py` now admits a context as an eligible
candidate only if its dimensional content is empty, or is exactly one
Consolidated/Separate member — an allowlist of the two shapes this evidence
and this repository's own prior rules can account for, never a blocklist
that assumes every future axis has been seen. Anything else is excluded
under its own status, `AXIS_EXCLUDED_ONLY`, kept apart from `NOT_FOUND`
("stated only under a qualifier we do not admit" is a different fact from
"never stated at all"). This can only ever REMOVE a candidate from
ambiguity, never invent one.

**This fix has not yet been re-validated against live DART content from
this session** — a direct `workflow_dispatch` attempt returned `403
Resource not accessible by integration`, the same class of blocker
`AGENTS.md` v2.29 already recorded for a different workflow. But the
operator validated it directly: see §3F.

**F. The real collector ran, and validated the fix — then a real workflow
bug discarded the result.** GitHub Actions run
[36313209561](https://github.com/jaehojung1879-netizen/Investment/actions/runs/36313209561)
(2026-09-27, `target: raw-xbrl-2015`, this branch at `fee7cba1`, real
`DART_API_KEY`) ran the actual collector, not the probe, across the full
254-issuer PIT universe: 762 (ticker, stage) combinations checked, 1,369
calls, `datasetComplete: true`. Measured:

| Classification | Count |
|---|---|
| `XBRL_ZIP_SERVED` | 526 |
| `NO_ORIGINAL_FILING_INDEX` | 154 |
| `FILE_NOT_AVAILABLE_014` | 81 |
| `AMBIGUOUS_REPORT_MATCH` | 1 |

**525 of 526 served ZIPs (99.8%) produced a record with at least one
resolved account** — against 3 of 18 (16.7%) on the small pre-fix sample.
This is the strongest evidence yet that the dimensional-qualifier allowlist
(§3E) generalises across the real population, not just the 8-ticker sample
it was built from.

The run then failed at the commit-and-push step: `fatal: pathspec
'ledger/fundamentals/kr-canonical-v2' did not match any files` — a real
workflow defect, not a DART or parser problem. `raw-xbrl-2015` alone never
creates `kr-canonical-v2` (that is `raw-statements`' own rebuild step, never
run in this branch's history), and a bare `git add` on a path that does not
exist at all is a hard git error, not a no-op. **All 525 real, live-
collected records were discarded before reaching `signal-history`** — the
commit step aborted before the `git commit`/`git push` lines ever ran.
Fixed on this branch (commit `4c43ce36`): the step now adds only the
candidate paths that actually exist that run, proven by a regression test
that extracts the real shell loop from the workflow file and runs it
against a repo missing `kr-canonical-v2`. The coverage audit this same run
printed is consequently **not a real "after" reading**: with `kr-canonical-
v2` absent, the merged candidate store held only the 525 fiscal-2015 XBRL
records and nothing from any other year, so every 2016–2026 gate cell read
`0.0` by construction — there was no fiscal-2016+ filing in the store to
compute a TTM from, independent of whether the fiscal-2015 prior was
correct. §10 names re-running `raw-xbrl-2015` (now that the commit bug is
fixed) as the immediate next step.

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
- **A context's own `<scenario>`/`<segment>` dimensional qualifier is an
  allowlist, measured from real served content (§3E).** Eligible: empty, or
  exactly one `ConsolidatedAndSeparateFinancialStatementsAxis` member
  (Consolidated preferred over Separate, per this repository's own existing
  rule, basis recorded per account). Excluded under its own status
  (`AXIS_EXCLUDED_ONLY`, never folded into `NOT_FOUND`): everything else,
  including the two axis families real evidence showed being misread as
  candidates before this fix (`dart-gcd:PeriodAxis`'s comparative-period
  tags, `ifrs:ComponentsOfEquityAxis`'s SCE component rows). `describe_
  candidates` reports every window-matched candidate's contextRef/dims/
  eligibility for review, without deciding a value itself.
- Every record carries `endpointConfidence: CANDIDATE_UNCONFIRMED`, because
  this session has never read a real served ZIP's contents beyond what §3E's
  live probe already measured (§10 names the confirming re-run). A unit
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

**This session cannot dispatch the workflow itself.** A direct
`workflow_dispatch` call against `fundamentals.yml`, and a `rerun_workflow_
run` on an existing run, both returned `403 Resource not accessible by
integration` — a GitHub App token permission this environment's credentials
do not carry, not a DART-side refusal and not a code defect (the same class
of blocker `AGENTS.md` v2.29 already recorded for `kr-corporate-action-
collection.yml`). The operator has been dispatching runs directly, and §3F
already gives strong evidence the parser fix works on the real population
(525 of 526 served ZIPs resolved) — a separate confirming `raw-probe-2015`
run is no longer the blocking step; the commit-step bug §3F found is.

1. ~~`target: raw-probe-2015`~~ **Done twice**, both wrote nothing to
   `signal-history`: run
   [36300578100](https://github.com/jaehojung1879-netizen/Investment/actions/runs/36300578100)
   (single-stage sample, §3D) and run
   [36304452901](https://github.com/jaehojung1879-netizen/Investment/actions/runs/36304452901)
   (expanded all-stage probe with `--dump-entries`, §3E) — the second run's
   real evidence found and fixed the dimensional-qualifier parser defect.
2. ~~`target: raw-xbrl-2015`~~ **Run once, real collection succeeded,
   commit failed.** Run
   [36313209561](https://github.com/jaehojung1879-netizen/Investment/actions/runs/36313209561)
   (§3F) collected 525 real records (525 of 526 served ZIPs resolved) but
   then crashed at the commit step on a nonexistent `kr-canonical-v2` path,
   discarding all of it. Fixed on this branch (`4c43ce36`).
3. **`target: raw-xbrl-2015` again, on the current head (`4c43ce36`).**
   The immediate next step: re-run the exact same collection (it is
   idempotent — `fetch-state.json` already marks all 762 (ticker, stage)
   pairs checked, so this run should be fast and should reproduce the same
   525-record result) and confirm the commit step now succeeds and pushes
   to `signal-history`. This is the run that actually lands real data.
4. **`target: raw-statements`**, `raw_years`/`max_calls`/`max_minutes`
   empty. Not yet run at all. Re-run until the log reports
   `"datasetComplete": true` (2015 now asks only for the annual report
   there, so this is fewer calls than before — about 12,140 filings over
   7–9 runs). Once step 3 has actually landed the xbrl-original store on
   `signal-history`, this step's audit reads the merged candidate
   (canonical-v2 + xbrl-original) automatically — this is the run that
   produces the first REAL "after" coverage number for 2016, since §3F's
   own audit read every 2016+ cell as 0.0 only because no other year's
   filing existed in the store yet, not because the fiscal-2015 recovery
   failed.

`pipeline/dart_xbrl_statements.py`'s account extraction still carries
`CANDIDATE_UNCONFIRMED`: 525 of 526 served ZIPs producing at least one
resolved account is strong evidence the mechanism generalises, but nobody
has read a served ZIP's raw content by eye end to end in this session to
confirm the resolved VALUES themselves are correct, only that the
allowlist logic runs and produces a value most of the time. `--dump-dir`
on a real `raw-xbrl-2015` run remains the way to promote this to
`CONFIRMED_LIVE`.
