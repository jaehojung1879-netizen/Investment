# Original DART XBRL fixed-sample source-value validation

This is an accounting audit, not a repair or an investment study. The current
result is **BLOCKED** (live run completed: 60 AMBIGUOUS_SOURCE_FACT on the reader's DART entity-scheme rule; see the report). No confidence promotion is justified.

## Frozen design and chronology

- Actual starting main: `d8e3caddb8a007cfd9842eedd5e751e054d267e4`.
- Accounting source commit: `fb6e83743fd8cdba647d1522a4645b662a9d5647`.
- Local protocol/sample freeze: `658c6e6b519ef4e26978d36438622f985ca82615`.
- Published freeze: `e756f0aa4457aaa4840ea359df7eb9276ce77731`.
  These commits have the identical tree
  `178f5a762e9c23a373cc551478ac9fe3f4ef9798`. CLI push lacked credentials;
  the existing GitHub connector published that tree before source inspection.
  The independent reader and its synthetic fixtures come in a later commit.
- Protocol SHA-256:
  `0aec37a4daed0d0765a25846cbdcbc410d70098fbed9340926a5376dd791cb0a`.
- Sample file SHA-256:
  `590513ede1c8bd06d701f22f4b1aa01bcf8b004aa30b9410540865696e863e70`.

The authoritative design and sample are the two JSON files under
`research_specs/kr-original-xbrl-value-validation-v1*.json`. Never edit them
to replace difficult cases. The reader checks their bytes, their actual
pre-source git commit, original shard hash, candidate shard hashes, frame hash,
and exact deterministic reselection before joining stored amounts.

## Frame and selection

The frame is every stored original-XBRL account fact in the four requested
families: 2,037 observations from 525 records. Account existence defines a
stored-fact population; the absence of an account is not a value observation.
No value, magnitude, sign, downstream coverage or extraction-status threshold
is used to select observations. Missing provenance is retained.

| Family | Frame | Sample |
|---|---:|---:|
| Net income | 515 | 15 |
| Operating cash flow | 489 | 15 |
| Assets | 517 | 15 |
| Liabilities | 516 | 15 |

The fixed seed is `KR_ORIGINAL_XBRL_VALUE_VALIDATION_V1`. Fifteen rounds cycle
through the four families. Within each family select the least-used actual
report/basis/statement cell, tied by seeded SHA-256; within that cell minimize
global issuer reuse, then order immutable fact identity by seeded SHA-256.
No seeds were searched. The selection covers 50 issuers, at most two facts per
issuer, 57 receipts, all three stages (Q1 20, H1 19, Q3 21), and both CFS (29)
and OFS (31). All 24 observed family/report/basis/statement cells are represented.

Amounts are deliberately absent from the sample manifest. Frozen shard hashes
bind their exact stored representation. Only the post-freeze audit joins them.

## Independent reader

`pipeline/kr_xbrl_value_validation.py` uses standard-library XML parsing,
scoped namespace resolution, ZIP reading and Decimal arithmetic. It does not
import or call the production fact extractor. It follows the recorded
element/context pointer in original XML, checks duplicates across instances,
and independently validates issuer, filing index, context, dimensions,
presentation linkbase, basis, currency, accuracy and amount.

The original filing-index row is fetched independently from authenticated
DART `list.json`. Original ZIP bytes must reproduce the recorded hash. The
reader never selects a replacement filing, context or account because the
first case is hard. It never modifies candidate data.

Declared `decimals` controls accuracy, not scale. Decimal rounding at declared
accuracy is explicit; there is no floating-point epsilon. Source facts with
unsupported transformations, unresolved namespaces, missing presentation
evidence, an unmapped context-entity identifier, an unproven unqualified basis,
or changed archive bytes remain ambiguous. These are conservative capability
limits, not evidence that the production value is wrong. In particular the
synthetic tests do **not** establish that every real 2015 filing uses a source
layout the independent reader can fully resolve.

All 60 facts must be MATCH for PASS. One confirmed value, semantic or metadata
mismatch is FAIL, even with unresolved cases. Without a confirmed mismatch,
unavailable/ambiguous source is BLOCKED. Process failures are separately
reported as INFRASTRUCTURE_ERROR. A complete audit enumerates every fixed item.

The optional zero-mismatch binomial bound is emitted only on PASS. It uses the
upper endpoint of a two-sided exact 95% interval. Since the sample is balanced
and deterministically ordered, this is a descriptive calculation under a
binomial assumption, not a design-based population assurance.

## Exact operator step to finish

The DART host was reachable, but this session had no `DART_API_KEY`. The pinned
repository store contains extracted facts/hashes, not raw original ZIP bytes.
Use the existing authorized `DART_API_KEY` environment in an operator session
or runner; do not add a new secret mechanism or put a key in a command/file.

From this PR branch with repository dependencies installed:

```sh
git fetch --no-tags --depth=1 origin fb6e83743fd8cdba647d1522a4645b662a9d5647
python scripts/validate_kr_original_xbrl_values.py \
  --input-root /tmp/kr-xbrl-validation-input \
  --source-dir /tmp/kr-xbrl-validation-sources \
  --materialize-from-git --download \
  --output /tmp/kr-original-xbrl-value-validation-v1-live.json
```

This fetches only the frozen receipts, reusing the repository's existing
authenticated HTTP helper for transport. It does not call the production
extractor, rebuild the candidate, dispatch another workflow or push any data.
Materialization reads only the pinned original shard and merged accounting
shards from git. It never checks out the mixed `signal-history` tree.

Exit codes: 0 PASS, 2 FAIL, 3 BLOCKED, 4 INFRASTRUCTURE_ERROR. Each output path
must be new so prior evidence cannot be silently overwritten. Local source ZIPs
and `<receipt>-<reportCode>.filing.json` files may be reused by omitting
`--download`; retain those bytes securely outside git for reproduction. Publish
the new compact audit JSON and Markdown result without committing raw archives.
Never replace a sample item or silently correct candidate data after a failure.

If a source format is not supported, preserve its entry/context/unit evidence
and diagnose it explicitly. Do not loosen PASS criteria to obtain a pass.
If all 60 facts eventually MATCH, recommend a stronger fixed-sample source
confidence in the report, without inventing a production enum. The next task is
**KR repaired-input snapshot freeze + accounting semantic contract**. This PR
does not seal a final v5 input or authorize historical execution.

## Outcome-blindness disclosure

An initial keyword-based paragraph sanitizer accidentally emitted one unrelated
historical performance narrative from AGENTS.md. This is a real startup
deviation: zero exposure cannot be claimed. It was not used in any sample,
threshold, comparison, classification or repair decision. No historical result
artifact was intentionally opened and no historical investment workflow was
dispatched. The replacement sanitizer emits only recognized operating commands,
never surrounding text. Tests cover unlabelled narratives that defeated the
initial filter. The fixed procedure remains deterministic and outcome-independent.

Full-suite checking also needs a guard: some unrelated tests open mixed
documentation and result artifacts. Such reads were refused during the full
suite attempt, rather than relaxing the task's restriction to obtain green tests.
