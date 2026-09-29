# Original XBRL source-value audit — BLOCKED

## Result

**Overall verdict: BLOCKED. Operational blocker: BLOCKED_ON_SOURCE_ACCESS.**
The fixed sample and independent reader are complete; original source validation
has not been demonstrated. No candidate data or production confidence label changed.

| Classification | Count |
|---|---:|
| MATCH | 0 |
| VALUE_MISMATCH | 0 |
| SEMANTIC_MISMATCH | 0 |
| METADATA_MISMATCH | 0 |
| AMBIGUOUS_SOURCE_FACT | 0 |
| SOURCE_UNAVAILABLE | 60 |
| INFRASTRUCTURE_ERROR | 0 |

Zero confirmed mismatches with no source-resolved facts is not a successful
validation. No error-rate confidence bound is reported. There are no confirmed
mismatch examples to diagnose and no repair is proposed.

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

The adjacent JSON report records every frozen fact, its stored normalized value,
issuer/receipt/period, claimed statement and element, recorded context/unit/
precision, original ZIP hash and exact reason it could not be compared.
No original source amount was fabricated or inferred from the production value.

Raw source bytes are not persisted in the pinned repository store; its collector
explicitly stores hashes and extracted values only. DART's host responded, but
the authorized `DART_API_KEY` environment variable was absent. No authenticated
source request was made. Source absence here means unavailable to this audit,
not proof that DART lacks the filing.

The independent implementation reads the original XML/context/unit/presentation
directly and uses Decimal. Synthetic tests exercise matching, incorrect signs,
wrong values, wrong periods/bases/currencies, metadata mismatches, duplicate
ambiguity, unavailable sources and process verdict priority. Those tests are
implementation checks, not substitutes for live source evidence.

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

## Confidence and next action

`CANDIDATE_UNCONFIRMED` **cannot be promoted** on this evidence. Execute the
exact operator command in `docs/kr-original-xbrl-value-validation-v1.md` in the
existing authorized DART environment, keep the sample unchanged, and publish
the completed evidence. A confirmed mismatch must remain FAIL and any actual
repair belongs in a separately authorized task/PR.

Only after strict PASS is the next task **KR repaired-input snapshot freeze +
accounting semantic contract**. No final v5 seal or historical Alpha execution
is part of this PR.
