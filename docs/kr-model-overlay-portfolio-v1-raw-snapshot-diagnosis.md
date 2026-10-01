# kr-model-overlay-portfolio-v1 — raw snapshot gate diagnosis and sealed-machine correction plan

Outcome-blind. No label, target, price, KRX value, return, model or portfolio quantity was read; no KRX collection was
performed; no frozen file was changed. All six outcome counters stay 0; no authorization, lock or permit exists.
Method (reproducible, accounting + PIT universe only): `scripts/diagnose_kr_ocf_improvement_lineage.py`; it mirrors
`kr_value_quality_catalyst.accounting_values` step by step and reproduces the formal gate's observed count exactly.

## 1. State verified
PR #179 head `fd13262741a0461a940ebf7e27c5880f2d093dcf`. Snapshot SHA-256 `2b6840cc8fea90b869e00b85f3853e898264664e1d4411b2eb9eda339e68671b`,
input identity `233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7`, 10,501 components, KRX cache
`3419d9d2…80037` (3,364/3,364 dates, 733,458 rows, 260 securities). Frozen gates-only: `DATA_INSUFFICIENT`, one failed gate
`FEATURE_COVERAGE:2017:ocfImprovementToAssets` (frozen override floor 0.20).

## 2. 2017 `ocfImprovementToAssets`: denominator 6,120, observed 520 (8.50%)
Mutually exclusive buckets, each name-date assigned to the FIRST failing prerequisite in the feature's own order (sums to 6,120):

| bucket | name-dates | share |
| --- | ---: | ---: |
| `PRIOR_TTM_MIXED_STATEMENT_BASIS` | 2325 | 37.99% |
| `CURRENT_TTM_MIXED_STATEMENT_BASIS` | 1149 | 18.77% |
| `NO_VISIBLE_FILING` | 1064 | 17.39% |
| `OBSERVED` | 520 | 8.50% |
| `CURRENT_TTM_FILING_ABSENT:PRIOR_ANNUAL` | 499 | 8.15% |
| `NO_ACCOUNTING_RECORDS_FOR_TICKER` | 281 | 4.59% |
| `CURRENT_TTM_OCF_ACCOUNT_UNAVAILABLE` | 197 | 3.22% |
| `PRIOR_TTM_FILING_ABSENT:PRIOR_SAME_STAGE` | 43 | 0.70% |
| `CURRENT_TTM_FILING_ABSENT:PRIOR_SAME_STAGE` | 32 | 0.52% |
| `PRIOR_TTM_FILING_ABSENT:CURRENT_PERIOD` | 6 | 0.10% |
| `UNKNOWN_OR_MIXED_STATEMENT_BASIS` | 4 | 0.07% |

Adjacent years (same method): 2018 observed 2677/6240 (42.90%), 2019 3857/6240 (61.81%), 2020 4252/6360;
2016 observed 0/6240 and 2015 0/6360. 2017 observations exist only from 2017-03-31 (9), 298 in April, 153 in May,
then 6-10 per month; none before 2017-03-31.

## 3. First causal constraint
The feature is `ocfTTM(year, stage) − ocfTTM(year−1, stage)` over total assets, where a quarter-stage TTM needs the
prior-year annual AND prior-year same-stage filing, and every filing in a chain must carry one explicit `fsDiv` of CFS or OFS
(`_compatible`). The pinned snapshot's fiscal-2015 Q1/H1/Q3 records (525, source `DART:fnlttXbrl.xml:ORIGINAL`) have
`fsDiv = None`: DART's JSON endpoint does not serve fiscal-2015 quarterlies, and the original-XBRL repair records carry no single
record-level basis. The frozen data audit states this is by design ("original-XBRL without a single explicit record-level CFS/OFS
basis is withheld in this version"). So, for every 2017 signal whose latest visible filing is a quarter report, the PRIOR
TTM chain `(2015 annual, 2015 same-stage)` contains an unlabelled record and abstains (`PRIOR_TTM_MIXED_STATEMENT_BASIS`
2,325, 38.0%; the same rule applied to the current chain in Jan-Mar, 1,149, 18.8%). Only the annual stage (FY2016 annual vs FY2015 annual,
both JSON CFS/OFS) can be observed, and it is the latest visible filing only from late March to mid May: that is the 520.
Independently of basis, 1,064 (17.4%) have no visible filing and 281 (4.6%) have no accounting record for the ticker.

**Classification: A (structural warm-up), through a frozen basis rule (G, defined above) — not C, D, E or F.**
There is no ingestion, availability, implementation or join defect: the code does what the audit documents. It is also not B
alone: filings exist; the fiscal-2015 quarterlies exist but are withheld by the frozen rule.

## 4. Was 2017 expected to be measurable? Could this be known outcome-blind?
- Earliest accounting source: fiscal 2015 (earliest `availableFrom` 2015-04-29, a Q1 XBRL record). Earliest PIT-usable under the frozen rule:
  FY2015 annual (JSON CFS/OFS; median `availableFrom` 2016-03-30) and everything from fiscal 2016.
- Earliest date `ocfImprovementToAssets` can legitimately exist: **2017-03-31** (annual stage: FY2016 annual vs FY2015 annual). For quarter stages:
  **2018-05-04** (Q1 2018 vs Q1 2017 vs prior annuals), because the prior TTM then needs only fiscal-2016 JSON records.
- Under the frozen chronology the 2017 20% floor (1,224 name-dates) was **structurally infeasible**: 520 is the maximum the frozen
  rule can produce (the observed count equals the bound). The design disclosed "warmup 2015–2016; gates start 2017" but
  fiscal-2015 quarterlies are unusable, so the true warm-up for this one feature extends to Q1 2018.
- It was knowable before any outcome, and even before the KRX collection: the count depends only on the pinned accounting shards, the
  PIT universe and the frozen feature code, none of which involves KRX values or returns.
- Informational bound only, NOT a proposal and not permitted by the frozen design: if unlabelled-basis records were treated as compatible, 2017 would
  read 2798/6120 (45.7%); the remaining shortfall is no-visible-filing and no-record names.

Nothing is changed on the strength of this. The 0.20 floor, 2017, the universe, the feature, the source, the imputation and the study period are untouched.
Any change to those is a study-design decision for the owner, not a repair.

## 5. Implementation defect?
For the coverage gate: **no**. For the sealed machine: **yes, one** (section 6).

## 6. Sealed-loader defect (`price/source`, `benchmark/source`)
- The pinned replay-v16 manifest has 585 components. `price/source` (vendor/routes/distributions/…) and `benchmark/source`
  (policy/region/source/symbol/ticker) are one-row lineage records with no `date`.
- Sealed `kr_model_portfolio_execution.load_sources` (line 159) selects components by prefix `("price/", "benchmark/")`, keeps rows
  whose `ticker` ends `.KS` (the benchmark lineage row does), and de-duplicates with `row["date"]` → `KeyError('date')` (run 36844599518).
- `replay_inputs.is_price_panel` (line 43) is the repository's canonical predicate (added after the replay-v10 run died on the same
  `KeyError: 'date'`) and separates dated panels from `STATIC_SOURCES`.
- The current PR's `dated_panels_only()` runtime shim in the UNSEALED `kr_model_raw_snapshot.py` made the readiness measurement
  possible but does not make the sealed execution path work: execution runs the sealed loader and would crash identically.

### Repair plan (NOT performed here)
- File requiring change: `pipeline/kr_model_portfolio_execution.py` only.
- Logic: line 159 `if not component.startswith(("price/", "benchmark/")): continue` → `if not RI.is_price_panel(component): continue`
  (`RI` is already imported there; no new import, so the import closure is unchanged).
- Leave line 112 (`source_files`, input identity) as is: it hashes the static lineage objects by prefix; changing it would move the input identity.
- Economic effect: none. The two static components never yielded a priced row (they crash today); every dated panel, row, value and date is identical.
  No feature, model, universe, gate or threshold changes; the diagnostic spec (`0fd3baf7…5f03`, no reference to the primary seal) is unchanged.
- Hashes that necessarily change: `dependencyHashes["pipeline/kr_model_portfolio_execution.py"]` (`c07dce18…41f9` → new) in the primary spec,
  therefore the primary spec bytes/digest and its `.sha256` sidecar (`bda5ade6…ad0c` → new), the `SPEC_SHA` constant in
  `kr_model_raw_snapshot.py` and the tests that pin it, and the snapshot manifest (it embeds `specSha256`; the manifest SHA `2b6840cc…671b` changes).
  Unchanged: all raw component bytes, the input identity `233df37e…66a7` (file hashes only), the KRX cache hash, the diagnostic spec.
  `docs/kr-model-overlay-portfolio-v1-handoff.md` quotes the file hash and is itself pinned: do not edit it; record the change in a new document.
- Reseal scope (precedent: the alpha-opportunity-model-v4 pre-execution correction, recorded in the sealed spec's `correctionHistory`): update the one
  `dependencyHashes` entry, add a `correctionHistory` entry, regenerate the sidecar, re-verify `load_spec`, re-run the replay (no KRX) to re-freeze the manifest,
  and remove the runtime shim. The study has no authorization, no result and no lock, and `preLockFailureConsumes` is false.
- Verification before any authorization: spec/closure verify; the sealed loader, unshimmed, returns the same priced panels as the shim on the real snapshot (compare panel
  digests; outcome-free); frozen specs otherwise byte-identical; input identity and KRX cache hash unchanged; six counters 0; gates-only on the re-frozen
  snapshot; and a decision on the 2017 gate (below) BEFORE resealing, so the study is resealed once.
- Do not reseal until the owner has decided what to do about section 4, because any change there (a different gate, start year, feature or basis rule) is also a change to the sealed spec.

## 7. Next permitted action
An owner decision on (a) the 2017 `ocfImprovementToAssets` gate and (b) the sealed-loader correction, ideally as one reseal. Until then: no authorization, no lock, no permit, no execution, no collection.
