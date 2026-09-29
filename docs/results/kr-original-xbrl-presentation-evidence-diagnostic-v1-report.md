# Presentation-evidence diagnostic v1 — MIXED_SOURCE_STRUCTURE

Outcome-free diagnostic, not a validation. v1 and v2 of
`kr-original-xbrl-value-validation` are closed and untouched; neither was rerun.
No Alpha/outcome data was read.

## Run

Actions run `36562070867` (head `d153d9a9`, gated one-shot `pull_request` path,
no rerun), artifact `11030592265`, zip SHA-256
`af880c7e9ec1cb43c10cc1eb0dabed4ad863cb65a0a7c625e53ad77919597883`, diagnostic
JSON SHA-256 `5394f1aced08a56beef0206bc2923ce5e8295ca75fb43693536745d6594b7c88`.
**12 of 12** raw ZIPs retrieved; each ZIP SHA equals the frozen v1 `zipSha256`.
The artifact (raw ZIPs, full inventories) could not be downloaded from the
authoring environment, so the JSON report is reproduced from the job log.

Subset (frozen in the spec before any source access): 108670.KS Q1 net_income CFS;
008770.KS H1 net_income OFS; 068270.KS Q3 net_income CFS; 006740.KS Q1 OCF OFS;
115390.KS H1 OCF CFS; 042700.KS Q3 OCF OFS; 047810.KS Q1 assets CFS; 052690.KS H1
assets OFS; 003230.KS Q3 assets CFS; 057050.KS Q1 liabilities OFS; 012750.KS H1
liabilities CFS; 003520.KS Q3 liabilities OFS.

## What the ZIPs contain (uniform across all 12)

Eight files each: one XBRL instance, an entry-point XSD, a small role XSD, and
linkbases for **definition, calculation, presentation (dimensions only)** and
Korean/English labels. The instance's `linkbaseRef`s point at exactly these files,
so they are embedded (the diagnostic's own "not embedded" count of 60 is a
path-separator artifact: entry names use backslashes, hrefs use slashes).

## Why `presentation = []`

1. **No role definitions anywhere (12/12).** There are zero `roleType` elements.
   Presentation roles are `http://dart.fss.or.kr/role/ifrs/dart_2013-03-31_role-D<code>`
   and the instance's `roleRef`s point to external DART files
   (`rol_dart_2013-03-31.xsd`). `statement_kind()` never receives a definition, so
   no network maps to a statement. (84 of 84 networks: definition not found.)
2. **Standard concepts are external hrefs.** Locs use
   `http://dart.fss.or.kr/Resource/Taxonomy/ifrs/2013-03-31/ifrs-cor_2010-04-30.xsd#ifrs_<Element>`.
   Fragments do equal `ifrs_<Element>`, but the resource is not in the ZIP and the
   reader admits only xbrl.ifrs.org / xbrl.iasb.org hosts.
3. **Balance-sheet concepts are not in any presentation network (6/6).** Assets and
   Liabilities have no loc at all; the only presentation linkbase is the
   dimensions one. ProfitLoss has none in 1/3 and, in the others, locs in roles
   whose meaning the ZIP cannot establish, mostly unconnected by live arcs.
   Operating cash flow has connected locs in `D520005` for 3/3.

Chain per fact: the instance pointer is unique, entity equals the frozen
corpCode, unitRef and decimals match, and the raw text equals the candidate
amount (12/12, descriptive) — so **source-value identity is established**; only
statement-membership corroboration is missing.

## Ten hypotheses

Rejected: 1 (definition in another document), 4 (fragment form), 9 (linkbases
missing). Confirmed: 5 (concept only in an external taxonomy) and 10 for the
balance sheet. Partly observed: 3, 6, 8. Not testable/established: 2, 7. See the JSON.

## Verdict: MIXED_SOURCE_STRUCTURE

Not a reader bug: a perfect reader still could not prove balance-sheet membership
from source-contained presentation (finding 3), and role-to-statement mapping for
every family depends on an external DART taxonomy (finding 1). Cash flow differs
from balance sheet, hence "mixed". This is not a PASS/FAIL judgment on any value.

## Not measured (limits)

Calculation and definition linkbase membership of the target elements (present in
every ZIP), the external DART taxonomy contents (never fetched), and the raw
artifact files. A rerun is not allowed for these; a v3 design can decide.

## Proposed input to a separate v3 (not implemented here)

Presentation membership should not be a mandatory gate as specified: it is
unprovable from the source for balance-sheet facts and needs an external
taxonomy for the rest. A v3 would have to preregister, before any run, which
independent evidence supersedes it, for example the exact IFRS concept QName in
the instance namespace plus context/basis/period/unit identity, with presentation
reported as corroboration only, optionally with a pinned, hashed external DART
taxonomy or calculation-linkbase membership as an explicitly chosen alternative.
`CANDIDATE_UNCONFIRMED` is unchanged.
