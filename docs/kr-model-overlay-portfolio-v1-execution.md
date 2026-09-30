# Preregistration, replay and authorization procedure

State: **MACHINE_FROZEN / DATA_READINESS_PENDING / EXECUTE_UNAUTHORIZED**. This PR builds the machine and does not turn it on. No authorization file exists. No live source collection or historical execute was dispatched. New joined KRX coverage is NOT_MEASURED.

The canonical scientific spec is `research_specs/kr-model-overlay-portfolio-v1.json`; its `.sha256` sidecar hashes compact sorted JSON through the repository's existing digest utility. The diagnostic spec is separately hashed. The spec pins all reachable repository imports, explicit docs/workflow/tests, the repaired accounting manifest, requirements, and prior v5 byte identities. Existing v5 spec/result/diagnostics are untouched. `verify` reads prior artifact bytes for hashes only, not their numeric content.

## Source preparation (later, outcome-free)

1. Materialize ONLY pinned monthly membership shards from source commit `4ea107ed0cde289f0a049a65ff13d2441a786710` under `<inputs>/ledger/universe/kr` and the pinned replay input manifest plus its price/benchmark content-addressed objects. The adapter reads `price/*` and `benchmark/*` only, filtering KR securities; it never reads historical outcome/signal shards, macro components or DART shares.
2. Materialize repaired `dart-*.jsonl.gz` accounting from `fb6e83743fd8cdba647d1522a4645b662a9d5647:ledger/fundamentals/kr-candidate-merged` into `<inputs>/accounting`. Full blob/content identity is checked against the accepted manifest. Do not reconstruct a different accounting snapshot under the same name.
3. Under authorized source access, `KRX_API_KEY=... python scripts/collect_kr_model_market_values.py <inputs>/market --start 2013-01-01 --end 2026-09-14 --max-calls 400`. Repeat bounded acquisition only until exact scheduled source dates are present; this is source collection, not model execution. Same-date response cannot overwrite cached source truth. Daily history is required for ADV; a weekly cap cache alone is insufficient. Refusals/empty expected exchange sessions do not become zeros or shifted dates.
4. Freeze/upload the resulting allowlisted raw input directory as a durable GitHub artifact, recording its run-id. Do NOT put outcome files in it. Exact file SHA256 mapping is computed by `input_identity`; later authorization pins its digest. This PR does not invent a nonexistent daily-cache digest.

## Modes

```bash
python scripts/run_kr_model_overlay_portfolio_v1.py --mode verify --output run
python scripts/run_kr_model_overlay_portfolio_v1.py --mode gates-only --inputs /path/to/inputs --output run
```

Without inputs, gates-only gives DATA_INSUFFICIENT with counters all zero. With inputs: accounting/universe/replay identity → PIT raw features → coverage by year/full member denominator → tradability/liquidity/downside history → overlay history → calendar-only maturity upper bound. First coverage date2017-01-01. Each VALUE/QUALITY feature20%; Catalyst relative/trend and Risk80% (OCF improvement uses20% accounting floor); quote/tradability80%, portfolio liquidity20%. PRIMARY stock rows must have at least one finite raw constituent in each VALUE/QUALITY/CATALYST family before imputation. Annual coreFamilyObserved conjunction coverage requires20% over all PIT member name-dates; all three family presence rates and the conjunction are reported. Failure blocks as DATA_INSUFFICIENT, never a post-outcome rule relaxation. Minimum matured-signal upper bound156, actual fitting requires104 matured training dates and10 names/date, minimum36months. No feature is removed when its gate fails. Sources can fail with explicit counters; never label quality masquerading as source coverage.

Counters are incremented at target, label, fit, prediction, model outcome, portfolio outcome call sites. Gates-only derives `stoppedBeforeOutcomes` from zero counters. Adversarial tests replace all outcome-facing functions with bombs. An OutcomePermit requires passed clean gates, pinned spec/input identity and matching later authorization. Target/evaluation wrappers refuse without it. Inputs are rehashed immediately before permit and after primary computation to detect same-run swaps.

## Separate operator authorization (NOT in this PR)

After review/merge and the complete outcome-free source freeze, commit:

```json
{"studyId":"kr-model-overlay-portfolio-v1",
 "specSha256":"<sealed canonical digest>",
 "inputSnapshotSha256":"<exact allowlisted file-map digest>",
 "inputArtifact":"<exact raw artifact name>",
 "inputRunId":"<exact producing run-id>",
 "harnessHashes":{"<every sealed dependency path>":"<file sha256>"},
 "diagnosticSpecSha256":"<sealed diagnostic digest>",
 "authorizedExecutions":1,
 "authorizedBy":"<operator>",
 "mergeCommit":"<final specification merge SHA>"}
```

File path: `research_specs/kr-model-overlay-portfolio-v1-execution-authorization.json`. Its exact bytes must be committed at HEAD. Execution requires Actions on `refs/heads/main`, matching authorization, no committed primary result and no prior repository primary artifact. A local `execution.started.json` is exclusively written before first outcome access; existing started/primary records refuse. Workflow concurrency is non-cancelling. A pre-lock failure or DATA_INSUFFICIENT gate stop is non-substantive and does not consume the one-shot. Failure after atomic repository lock creation may consume it, even if no outcome was reached. The workflow is manual, no schedule. No automatic dispatch in this PR.

The raw artifact's name AND producing run-id must be committed in authorization and match workflow download inputs. Authorization hashes prove its identity before outcomes. Later execute command is `python scripts/run_kr_model_overlay_portfolio_v1.py --mode execute --inputs inputs --output run`. It refuses today.

## Durability

Primary JSON is canonical, fsynced and atomically exclusively published; hash sidecar is written before any supplementary invocation. Supplementary work is separate and cannot rewrite primary. Workflow `always()` classifies/uploads primary even if diagnostics or the process later fail. Immediately archive primary+sidecar to `docs/results/kr-model-overlay-portfolio-v1-result.json` in main: the committed result is the permanent guard beyond artifact retention. Operator must never rerun an executed study because an artifact expired or diagnostics failed. A permanent repository tag keyed by spec SHA is atomically created ONLY after successful raw download, exact authorized identity and READY pre-label gates with ALL six outcome counters zero; never updated or deleted. This guard survives artifact expiry and runner loss. A post-lock infrastructure failure may consume that attempt; preserve its evidence and require a new study version rather than retrying this version. No post-outcome scientific edit under this version.

## Verification scope

New tests use synthetic filing/price/cache/label fixtures only. Routine legacy repository regression tests can verify existing closed-study artifact identities; they are not new-study outcome access, new fitting or a design input. No v5 numeric table was opened to choose v1 rules. The zero-counter proof applies to this new study's verify/gates paths, not a fictional claim that required README/AGENTS contained no historical narratives.

## Formal lock and permit sequence (v1 correctness revision)

1. Verify current main HEAD, committed authorization and its spec/closure/diagnostic/artifact/run pins; refuse prior result/artifact/lock (read-only).
2. Download that exact authorized raw artifact. A typo/network failure cannot create a lock.
3. Verify its exact authorized snapshot identity.
4. Prepare raw PIT features and run pre-label gates.
5. Require READY and exactly the full six-counter map with every value zero; recheck spec/input/authorization pins and no existing local started/primary files.
6. Atomically POST/create the permanent repository tag. Duplicate/ambiguous responses refuse. No outcome-reading function is called between gate verification and this create.
7. Immediately exchange the same clean gates and successful lock receipt for the outcome permit, then write the local started record.
8. Only then call labels/fitting/evaluation. The primary stays durable before supplementary work.

All pre-step6 failures preserve the one-shot, including identity/gate/counter failures. All post-step6 failures may consume it. This repair creates neither an authorization nor an execution lock.
