# Original XBRL source-value audit — BLOCKED

## Result

**Overall verdict: BLOCKED (live execution completed).** The frozen 60-item
audit ran against real DART originals. All 57 receipts downloaded
(`sourceAccess: COMPLETED`, zero failures) and no candidate data changed.

| Classification | Count |
|---|---:|
| MATCH | 0 |
| VALUE_MISMATCH | 0 |
| SEMANTIC_MISMATCH | 0 |
| METADATA_MISMATCH | 0 |
| AMBIGUOUS_SOURCE_FACT | 60 |
| SOURCE_UNAVAILABLE | 0 |
| INFRASTRUCTURE_ERROR | 0 |

Live evidence: Actions run `36519798469` (head `02124c9c`), artifact
`11012284532` (zip SHA-256 `3b3de806d6d0539aa0d314aa599d6193c0ce2b502ba3b2881322550f246be240`),
report SHA-256 `a04725f6e7df4aa57ef0b27d6ec0c708f80848f269b33adb4cd69826e0f8660a`.
An earlier run on head `eb5a3190` (`36518798900`, artifact `11012490293`) produced
a byte-identical report hash. The per-item fields in the JSON are reproduced
from the job log; the artifact zip could not be downloaded from the authoring
environment.

**Why every item is ambiguous.** All 60 stop at the reader's frozen identity
rule with the same reason: `context entity scheme not independently
established as DART identity`. The served contexts use entity scheme
`http://dart.fss.or.kr/ifrs/CIK`; the frozen rule admits only a bare
`dart|opendart.fss.or.kr` scheme. This is a conservative reader-capability
limit, not evidence that any candidate value is wrong.

**Descriptive only, not a classification.** In all 60 items the context entity
equals the sample's `corpCode` and the source raw text equals the stored
candidate amount. These observations were made after the run, changed no
rule, and do not produce a MATCH: under the frozen semantics the identity
scheme is unproven, so PASS is not established. Relaxing the rule after seeing
this would be the loosening the protocol forbids; any such amendment needs its
own pre-registered follow-up, and this sample must stay fixed.

No confirmed mismatch exists, so nothing is diagnosed or repaired here.

## Verified identity and sample

| Item | Value |
|---|---|
| Starting main | `d8e3caddb8a007cfd9842eedd5e751e054d267e4` |
| Accounting source commit | `fb6e83743fd8cdba647d1522a4645b662a9d5647` |
| Candidate SHA-256 | `af642e7e79e9ba59ac6ee14faf033f4d63887188bab6506845c082e21dc3d1cc` |
| PIT KR universe | 260 tickers, recomputed from membership/rank metadata |
| Resolved DART issuers | 254, verified in persisted manifests |
| Canonical-v2 / original-XBRL / merged | 8,826 / 525 / 9,351 records |
| Original-XBRL work list | 762 checked, 0 remaining, datasetComplete=true |
| Frame | 2,037 fact-level observations |
| Fixed sample | 60: 15 per family, 50 issuers, 57 receipts |
| Sample SHA-256 | `590513ede1c8bd06d701f22f4b1aa01bcf8b004aa30b9410540865696e863e70` |
| Published pre-source freeze | `e756f0aa4457aaa4840ea359df7eb9276ce77731` |
| Local pre-source freeze, identical tree | `658c6e6b519ef4e26978d36438622f985ca82615` |

The candidate identity is recomputed with the existing audit convention: SHA-256
of compact sorted JSON mapping each merged shard filename to its git blob SHA-1.
This independently reproduces the reported candidate hash; it is not a hash of
an arbitrarily reserialized set of accounting values.

The current `signal-history` head was also checked by tree metadata only:
`90b32e062382739ee6c8290ba027422aeb1ee5ed`. Its original-XBRL shard/manifest and
all 12 merged accounting shards have identical blob IDs to the pinned source
commit (14 allowlisted objects checked). No unrelated branch artifact was opened.

All 525 original records still say `CANDIDATE_UNCONFIRMED`. The original-XBRL
work list is complete. Separately, the raw-statement manifest's datasetComplete
is false because its broader collection work list is not fully settled; this
does not change the verified 8,826 stored canonical records or original-XBRL
completion. No broader collection-completion claim is made here.

## Evidence and limitations

The adjacent JSON report records every frozen fact with its stored value,
recorded context/unit/decimals/raw text, entry and ZIP hashes, filing-index
hash and the exact reason it stayed ambiguous. No source amount was inferred
from the production value. The independent reader (not the production
extractor) produced these results; the synthetic tests remain implementation
checks and the live run shows real 2015 packages resolve to a concrete fact
but not past the identity-scheme rule.

## Verification

- `ruff check .`: passed.
- `python -m compileall -q pipeline scripts`: passed.
- Every pipeline module imported; every script compiled: passed.
- New validation tests plus existing accounting-repair and accounting-quality
  tests: 156 passed, 1 skipped (old merge-base absent in shallow checkout).
- Full `pytest -q` attempt with outcome-file/live-network refusal guard:
  2,603 passed, 68 failed, 2 skipped. The guard logged 68 refused file reads;
  mixed AGENTS.md and unrelated result/dependency artifacts were blocked.
  This is **not** an unqualified full-suite pass. The task's source restrictions
  take precedence over reading those files to make unrelated tests pass.
- Synthetic site seed generation was not run: it emits investment-score/site
  artifacts outside this source-value audit. No existing site artifact was read
  or regenerated for validation.
- `git diff --check`: passed.
- No workflow file changed and no workflow dispatch/rerun was requested.
- No historical investment outcome was used in selection, thresholds or verdict.

The startup sanitizer did leak one unrelated performance narrative. The incident
and subsequent fail-closed replacement are disclosed in the protocol/runbook.
Do not describe this session as having had zero historical-outcome exposure.

## CI

`tests.yml` now checks out full history (`fetch-depth: 0`); the two failures
were the shallow checkout lacking freeze commit `e756f0aa`, and are fixed
without skipping or weakening the ancestry check. Tests run `36519798466` on
head `02124c9c`: success.

## Confidence and next action

`CANDIDATE_UNCONFIRMED` **cannot be promoted**: no item is MATCH. The sample
stays fixed. The blocker is the reader's entity-scheme rule, which needs a
separately pre-registered, human-approved amendment (and a new result file)
before any PASS is possible. Nothing else — no repair, v5 seal or Alpha
execution — is part of this PR.
