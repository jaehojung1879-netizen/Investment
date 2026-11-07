# Pages state publication / operational audit

## A/B implementation consent and v2 candidate (2026-11-07 UTC)

The Owner explicitly approved A/B implementation and testing in this conversation ("승인할게") after reviewing the
[exact scope](https://github.com/jaehojung1879-netizen/Investment/issues/292#issuecomment-6699773509). This is not merge,
deployment, historical execution or prospective-writer activation consent. Existing #314/#315 branches remain untouched;
this candidate is isolated on parent #315 `23522002dcd2d9e0e16dfb9d325a235aef664f0c`.

- A: both ordinary Tests and production Pages pip installs use the same `constraints/ci-registered-numerics-v1.txt`:
  threadpoolctl3.7.0 and joblib1.6.0, as the original registration requires. Original requirements, formal requirements,
  Python3.11.16/CPU/thread guards and numerical error expectations are unchanged.
- B: the old PR/full-input preflight remains callable and still refuses consumed studies. The operational diagnostic now
  uses a separate standard-library-only `audit_closed_atlas_provenance.py`. It checks the original metadata, 158 registered
  dependencies and 235 protected files as opaque bytes, plus the exact existing consumed locks. It imports no numerical,
  label or model modules and has no GitHub write endpoint. No inputs are re-prepared and no external outcome archive is
  downloaded or evaluated. The formal result path is absent in the reference Git snapshots; absence is not a successful
  study and never makes the study unconsumed. Receipts say `CLOSED_STUDY_HISTORICAL_PROVENANCE_VERIFIED`, not execution
  preflight passed, and can only be created immutably in a private `/tmp` subdirectory.
- The original v1 record/sidecar stay byte-identical, SHA256436ce3361d1183fe11db0c931de0cf688dfdd021ac70c7173b8b35a939e25ddf.
  V2 is a new record/sidecar. Historical Pages/verifier/workflow assertion bytes are verified in Git; current bytes are
  checked separately. The only permitted workflow differences from parent #315 are the diagnostic route and one ordinary
  install line. The verifier's preparation, audit and formal functions remain byte-identical. The old workflow assertion
  is preserved in Git and only that function may change; every numerical test byte outside it is identical.

| Identity | v2 candidate SHA256 |
|---|---|
| Pages workflow | 112196a5a53123eae00d8f3ba5d6c15cd109263cbd43ecd1c26869c19bfd0371 |
| Tests workflow | 91e4f2dd587f6cc1a7a1cd0c41f04dcd03c97a4b2af0b6f904fdb1ad2b947124 |
| Atlas operational verifier | 799bb4a248547ef958eefd676748894413c00212811e56b55d57de021d8eb342 |
| Original research prefix, 5,992 bytes | 048356c7b43e499b32660ce40c0b1dde9db7e43b33a58fd36df8a4ea51e17b30 |
| Approved current prefix, 5970 bytes | 06ef04856344a6d076f1012f7bea697cff21e8da3705471b64d24b8802a88cb6 |

Changing a record and its sidecar together cannot authorize a broader workflow, skipped suite, changed formal runtime,
scientific preparation or altered numerical error expectation: bounded byte transformations and negative tests reject it.
The original registration/addenda, source IDs, authorization bytes, result bytes and consumed commit
`09ba076f9fcd7ca9957b12933dd51bd69e6506d0` are preserved. The diagnostic's result scope explicitly excludes external
outcome artifacts; it is not a new historical result evaluation.

The existing Git Data API publisher and its disk/concurrency controls are inherited without modification. Regular
ledger/replay checkout disk pressure remains outside this candidate. Exact final-HEAD test/CI and credential failures
are recorded in the Draft candidate/handoff; no deployment or operational-recording success is implied.

The dated v1 observations below remain historical evidence; their narrower scope and old prefix describe that version.

## Current implementation and consumed-study diagnostic (2026-11-04 KST)

Owner implementation approval is recorded on PR #315 (2026-11-03 KST). Maintenance record v1 and its sidecar now exist;
the earlier proposal text below is retained as design history, not a statement that approval is still missing.
The reviewed baseline is `0384ff464ad7e07d3c203b0c78e421fcda359123`.

Tests [41617427471](https://github.com/jaehojung1879-netizen/Investment/actions/runs/41617427471) succeeded. Pages
[41617427637](https://github.com/jaehojung1879-netizen/Investment/actions/runs/41617427637/job/125854271623) failed in
`Real full-input preflight behind the outcome firewall`, not registration validation or production publication.
The original job log (2026-11-03T10:15:32Z) traces CLI `preflight` through `V4.audit` to
`kr_alpha_atlas_mirae_repair.audit:329`, which raises `AUDIT_REQUIRES_UNAUTHORIZED_UNCONSUMED_STUDY`.
Its original uploaded `reproducibility-preflight-receipt.json` has `FAIL_GATE_PRESERVED_NOT_CONSUMED` and all seven
outcome/model/backtest/dispatch/lock counters equal to zero. Neither production deploy nor formal execution ran.

This is the frozen lifecycle rejecting a consumed/authorized study, not a disk failure and not another failed maintenance
hash check. `tests/test_pages_consumed_preflight.py` reproduces the refusal with an offline GitHub adapter and proves input
preparation is never reached. The guard is intentionally preserved. Suppressing this error, changing a lock, returning a fake
matrix-preflight success or excluding the check would not repair the lifecycle.

The unconditional PR real-input preflight is inside the sealed 5,992-byte prefix. Turning it into a closed-study historical
verification route changes diagnostic behavior and needs a separate explicit scope decision; the current approval permits
only production state publication and exact maintenance validation. This patch therefore does not claim the Pages check is
green or that the PR is merge-ready. No workflow prefix, execution authorization, result, numerical code or lock is changed.

Within the existing production scope, the publisher now distinguishes a missing file from existing JSON `null`. Any existing
non-object/invalid state is rejected before POST/PATCH. The five seal-verifier paths and the exact v1 Pages/verifier hashes
remain unchanged; no maintenance version/hash update is needed for this unsealed publisher correction. The historical Git
objects are additionally checked without temporarily replacing current files. Concurrent ledger writes, duplicate no-op,
bounded conflicts, failure isolation and bounded ENOSPC fixtures remain covered.

Snapshot: 2026-11-02 UTC. Code base: `main@37f8cbf6b1c066f6b3c65235953648d17ebf2f69`.
Source: [Issue #292 capacity handoff](https://github.com/jaehojung1879-netizen/Investment/issues/292#issuecomment-6574150500).
This is an engineering inventory, not investment admission, permission to execute research, or a merge approval.

## P0: state-only publication

Run 41378213161 deployed Pages successfully; subsequent state persistence failed while checking out the entire signal-history tree. Replace only that publisher with Git Data API operations. `update_state.py` still performs production validation after successful deployment. The new script reads branch HEAD, commit and the one state file pinned to that HEAD; creates a tree based on the inspected tree with one explicit path; creates a single-parent commit; PATCHes the branch with `force: false`. An intervening ledger append makes this a non-fast-forward update. Only 409/422 ref conflicts retry, at most five attempts, each with a fresh HEAD/state read. No rebase, ledger content download, worktree or branch creation occurs. A missing branch/token, unreadable or malformed state, invalid timestamp, permission failure or exhausted retries fails closed. Objects from rejected attempts can be unreachable, but no existing ref/tree/data is deleted.

Decoded JSON equality is a no-op, including differently formatted copies of the same snapshot. Both `marketAsOf` and timezone-aware `generatedAt` must never decrease. Different content at an equal generation instant is refused. A concurrent newer state is rechecked rather than overwritten. A missing latest.json may be added only after tree metadata confirms absence. Existing sealed state files and every unrelated subtree inherit their object identity.

The earlier Pages `git fetch signal-history` and `git archive ... ledger/historical` remain unchanged: their input/readout parity is outside this patch. This fix removes the final 3.359-GiB materialization, not all repository disk pressure. Gauges (`df -h`, aggregate `du -sh` for workspace, .git, .state and _site) precede checkout/build/deploy/publication; they print sizes and paths only.

### Reproduction and validation

`python -m pytest -q -s tests/test_publish_state.py` uses a tiny bare Git repository and an offline Git Data API adapter. It covers state-only diff, ledger and protected-state blob/tree identity, duplicate no-op, concurrent ledger append, concurrent newer state, bounded conflicts, 401/403/500 isolation, stale/malformed candidates, missing token and a missing latest file. The adapter implements actual commit ancestry with `git merge-base --is-ancestor`, not an always-success mock.

The kernel `/dev/full` fixture produces ENOSPC when writing a 17,407-byte synthetic ledger blob. This reproduces the failing materialization operation, not the entire production runner. The API update then succeeds with ledger tree identity unchanged. A separate real synthetic worktree measures 17,714 bytes versus a 214-byte new state payload and **zero ledger checkout bytes** for publication. No multi-GiB fixture, full disk fill or real historical replay was used. Metadata for `signal-history@7c0bcf01cf77bdfe456881febaba43f7461b8c77` (recursive tree, `truncated=false`) totals **3,606,903,033 blob bytes**, all of which the old worktree would materialize; the new publisher downloads only state JSON and small metadata. Filesystem overhead, Git object storage and build outputs are additional, so this is not a measured full-run 14-GB peak.

Local: 17 new synthetic tests + 28 existing integrity tests PASS (45 total); Ruff, pipeline compile, seed generation and `validate --allow-seed` PASS. Seed is local verification only and cannot enter publication. Full trusted repository suite is delegated to automatic PR CI because local checkout is shallow and historical source identities are not materialized. Exact final-head CI status is recorded on the Draft PR; never inherit a previous head's green. Production deploy+publication confirmation awaits an authorized normal post-merge run. No dispatch, rerun, merge or production state write was performed in this task. Independent non-author review remains a merge gate.

## P0 seal conflict: Phase C v4 pins the whole pages.yml (analysis, no seal change)

**Scope of the seal.** `pipeline/kr_alpha_atlas_reproducibility.py` hard-codes `ADDITIONAL_FILES` (the module itself, its
tests, the diagnostic modules, `root-cause.json` and `.github/workflows/pages.yml`). Their hashes live in
`research_specs/kr-alpha-atlas-phase-c-v4-reproducibility.json`, which its `.sha256` sidecar pins and whose
`effectiveContractSha256`/`dependencyManifestSha256` digest the closure. `load()` raises
`REPRODUCIBILITY_DEPENDENCY_CHANGED: .github/workflows/pages.yml` on any byte change. The pin is whole-file because the research
jobs `matrix-diagnostic` (PR / `matrix-validate` / `matrix-preflight`, contents: read) and `matrix-formal-owner-only`
(`workflow_dispatch` `matrix-execute`, main only, owner only, contents: write), their triggers, concurrency group and the
numerical environment (thread pins, `OPENBLAS_CORETYPE`, CPU-feature masks, Python 3.11.16) are declared in the same file as
production `build-and-deploy`. The v4 addendum states `formalExecutionAuthorized: false` and `freshExactHashOwnerApprovalRequired:
true`; the global one-shot lock `refs/tags/kr-alpha-atlas-phase-c-v1-execution-lock` already exists at `09ba076f`, so no formal
run can occur again. The seal now protects reproducibility evidence, not a pending execution.

**Where it is enforced: five independent pins, measured on head `df80c485`: Tests run 41432985079 (8 failed / 6,436 passed) and Pages run 41432985080 (`matrix-diagnostic` failed).**

| # | Contract | Pin | Failing check on this head |
|---|---|---|---|
| 1 | KR Alpha Atlas Phase C v4 reproducibility addendum | whole-file sha256 `d13e2a45…` (`ADDITIONAL_FILES`, addendum, sidecar) | `matrix-diagnostic`; `test_kr_alpha_atlas_reproducibility.py` ×4 (3 × `REPRODUCIBILITY_DEPENDENCY_CHANGED`, 1 regex reached through the same load) |
| 2 | Research terminal publication seal (Python) | exact bytes of commit `8f45870c`; only `weekly-session-integrity-v1-pins.json` files and a hard-coded tests.yml timeout are exempt | `test_research_terminal.py::test_sealed_build_publication_and_results_are_unchanged` |
| 3 | Research terminal v3.1 seal (Node) | same file list with the same pins registry | `test_research_terminal_v3.py` (node `research_terminal_v31.test.cjs` #25) |
| 4 | RP1 C1 US WP4d scope guard | no `.github/workflows/*` change other than its host workflow in a branch diff | `test_rp1_c1_us_wp4d.py::test_no_new_workflow_file_and_the_census_and_its_pinned_layers_are_untouched` |
| 5 | RP1 US universe registration | `protectedTreeSha256[".github/workflows"] = fa92a9ad…` in its registered spec | `test_rp1_us_universe.py::test_sealed_directories_c1_files_and_workflow_census_unchanged` |

All eight failures are these five pins; no other test fails. Each is a registered contract or its validator, so none may be
edited to make CI green without approval. A precedent for a narrow, owner-approved exact-hash replacement already exists
(`docs/weekly-session-integrity-v1-pins.json`, scope `OWNER_REQUESTED_WEEKLY_SESSION_SAFETY_FIX_ONLY`), used by pins 2 and 3.

**Path A rejected: publish state outside pages.yml without changing it.** Technically possible (a `workflow_run`
workflow could rebuild state from the deployed artifact's `data/site-data.json` and call `publish_state.py`), but unsafe:
1. The sealed `Publish last successful state` step is unconditional (no input, variable or secret disables it). Every
   production run would keep materialising 3.36 GiB and fail after deployment, so a real deploy failure becomes
   indistinguishable from a known one.
2. If the legacy step ever succeeds (more disk), two publishers write the same path. `publish_state.py` refuses regressions,
   but the legacy step has no regression guard. Correctness would depend on ordering between two workflows.
3. The `workflow_run` workflow would write `signal-history` from a job outside the `github-pages` environment that gates
   `build-and-deploy`. That moves state writes outside whatever protection rules and branch policy that environment
   enforces (they could not be read from this session).
4. `workflow_run` also fires on the `pull_request`-triggered Pages runs that execute `matrix-diagnostic`. Rejecting them needs
   parsing of the triggering run's event, branch and individual step outcomes, because the run's own conclusion would be
   `failure`. That is a second deploy-state protocol to keep correct.

**Path B chosen: a versioned maintenance exception, pending owner approval.** This branch now keeps **every byte before
`build-and-deploy:`** identical to the sealed file. The prefix is 5,992 bytes with sha256
`048356c7b43e499b32660ce40c0b1dde9db7e43b33a58fd36df8a4ea51e17b30` in both the sealed blob `d13e2a45…` and this head.
`tests/test_pages_sealed_research_prefix.py` asserts that prefix, that `build-and-deploy` is the last job (so the prefix covers
both research jobs, triggers, permissions and concurrency), and that the addendum, sidecar and `ADDITIONAL_FILES` are untouched.
The two header comment lines an earlier commit had edited are restored. The explanation moved inside the publish step.

Nothing below is implemented. The exception has to be approved first, because it edits sealed bytes:

| Item | Proposed |
|---|---|
| Registration | one record, `docs/operations/pages-yml-maintenance-1.json` + `.sha256`: old whole-file sha256 `d13e2a45…`, new whole-file sha256 of the approved head (currently `03f38c82d771b0663194985f6dada35453ab9554a0ef289a80c95bfa53f27e79`), sealed prefix sha256 `048356c7…` / 5,992 bytes, the five pins it covers, scope `PRODUCTION_STATE_PUBLICATION_ONLY` |
| What it permits | exactly one changed file, `.github/workflows/pages.yml`, to exactly that new hash, **only while** the bytes before `build-and-deploy:` still hash to `048356c7…` |
| Pin 1 | `kr_alpha_atlas_reproducibility.load()` accepts the closure with that single substitution when the record verifies. The module is in its own sealed closure, so its new hash is listed in the record and the v4 addendum, sidecar and `root-cause.json` stay byte-identical |
| Pins 2–3 | the two terminal seals read the record (like `weekly-session-integrity-v1-pins.json`) instead of comparing pages.yml to `8f45870c` |
| Pin 4 | the WP4d guard allows pages.yml only when the record verifies |
| Pin 5 | the universe check recomputes `.github/workflows` with the sealed pages.yml blob substituted, so its registered `fa92a9ad…` is untouched |
| Does not permit | execution (`formalExecutionAuthorized` stays false and the lock already exists), any change to inputs, matrix digest, numerical environment, research jobs, triggers, permissions or concurrency, or re-running anything |
| Approval | owner comment on #315 naming the exact head SHA, the record's sha256 and the new pages.yml hash; independent non-author review of that head |

Until then #315 stays red on `matrix-diagnostic` and on the eight pytest checks above. No hash, validator, test or registration
was changed to make it pass.

## P1: next operational changes (read-only diagnosis)

Sizes below are blob bytes from the same fixed tree, rounded MiB. A full current signal-history worktree adds **3,439.81 MiB** per materialization plus filesystem overhead; fetch pack/history/cache/build outputs are extra, not included. Historical sealed trees have their own sizes, not necessarily today's size. Partial-write conversions must use a base tree and non-force ref update; never rebuild a root tree from a sparse set alone. Append-only writers must recompute/merge their own path changes on conflicts rather than overwrite a concurrent append.

| Priority / workflow | Required signal-history paths | Full tree needed? / current extra disk | Partial approach / change risk |
|---|---|---|---|
| 1 ledger.yml | state/latest; ledger signals/outcomes/summary, historical read shards, weekly-decisions | No; 3,439.81 MiB + .state historical copy | Pin reads; sparse historical inputs + only mutable paper/weekly paths, API tree commit. High: append identities and weekly failure isolation must remain. |
| 1 fundamentals.yml KR/US | ledger/fundamentals/kr (0.95 MiB), us (43.24 MiB) | No; 3,439.81 MiB per runner | Narrow stores, base-tree writes. Medium: vendor cursor/provenance and derived period semantics. Existing US probe already uses sparse checkout. |
| 1 fundamentals.yml raw | raw/canonical/XBRL/candidate stores; pinned sealed universe and legacy KR fundamentals | No; 3,439.81 MiB current + an entire sealed worktree of unmeasured size | Sparse two immutable refs; raw alone 62.73 MiB, all fundamentals 140.92 MiB. High: preserve sealed SHA and exact coverage-audit inputs. |
| 2 universe.yml snapshot/prices | ledger/universe/kr; prices/kr plus universe/kr | No; 3,439.81 MiB per runner | Narrow reads/writes (all universe 1.64 MiB, all prices 49.15 MiB). Medium: carry-forward, outage refusal, as-traded identities. |
| 2 dart-ownership-events.yml | ledger/dart-ownership-events (0.44 MiB), universe-history.json and universe/kr | No; 3,439.81 MiB | Sparse store and membership reads. Medium: incremental receipt dates, duplicate handling, missingness. Probe job does not create the extra tree. |
| 2 kr-corporate-action-collection.yml collect/dividend/terminal | ledger/kr-corporate-actions (1.73 MiB); dividend job also universe/kr | No; 3,439.81 MiB per job (separate runners) | Narrow read/write sets per job. High: terminal economics, source documents, cursor and three-way conflict semantics. Probe/owner-gated US job have no extra worktree here. |
| 2 fundamental-acceleration-seal.yml | fundamentals/kr,us reads; fundamental-acceleration-seal writes | No; 3,439.81 MiB + .fundamentals extracted store | Sparse inputs + atomic append. High: preserve seal hashes and write-once records. |
| 3 replay.yml | historical shards/versions, replay-inputs, universe, prices, fundamentals, models and benchmark snapshots | Broad ledger input is needed, unrelated state and prior replay versions need not be expanded | 3,439.81 MiB + generated new outputs; historical 2,257.35 MiB, inputs 920.10 MiB. Highest: frozen-input/output identity and archived versions. Design bounded sparse reads/content-addressed writes only after exact parity proof; do not rerun studies to test this. |
| 3 pages.yml prior reads | latest state, summary, outcomes, historical, diagnostics/validation and opportunity/warning models | Existing full fetch and historical archive remain | Pinned narrow reads can reduce object transfer and archive selection, but require exact input/readout parity; independent follow-up only. |

Prevention: run size-only gauges before checkout/build/publish on later workflow changes; review a pinned tree-size census as an operations gate. Separate immutable old replay versions from each job's necessary working set through sparse reads, not deletion. Put one independent workflow conversion in each reviewed change. Keep research intake behind this P0; closing PRs by itself will not reclaim Git history. No new service, paid storage or dependency is required.

### Whole workflow checkout census

All `.github/workflows` files were searched for `actions/checkout`, `git worktree add`, `git clone` and `git archive`. Full signal-history worktrees occur only in the seven workflow families listed above (Pages removed by P0). No executable git clone was found in workflow YAML. Additional ordinary source checkouts generally materialize main (~0.347 GiB per checkout); `fetch-depth: 0` adds unbounded history/objects beyond that estimate. Existing sparse source checkouts reduce working files but do not alone prove blobless transfer. Research lifecycle workflows and their pins are unchanged.

The following is the complete per-file source-checkout inventory at this audit HEAD; counts denote action occurrences, not simultaneous trees on one runner:

- `alpha-inference-calibration-v1.yml`: 1 source checkout(s).
- `alpha-inference-calibration-v2.yml`: 1 source checkout(s).
- `alpha-inference-calibration-v3.yml`: 1 source checkout(s).
- `alpha-inference-calibration-v4.yml`: 1 source checkout(s).
- `alpha-inference-calibration-v5.yml`: 1 source checkout(s).
- `alpha-opportunity-model-v1.yml`: 2 source checkout(s); includes full-history fetch; includes sparse checkout.
- `alpha-opportunity-model-v2.yml`: 2 source checkout(s); includes full-history fetch; includes sparse checkout.
- `alpha-opportunity-model-v4-execution.yml`: 4 source checkout(s); includes full-history fetch; includes sparse checkout.
- `alpha-opportunity-model-v5-execution.yml`: 2 source checkout(s); includes full-history fetch; includes sparse checkout.
- `dart-ownership-events.yml`: 2 source checkout(s).
- `fundamental-acceleration-seal.yml`: 1 source checkout(s).
- `fundamentals.yml`: 6 source checkout(s); includes sparse checkout.
- `kr-alpha-atlas-phase-c-amended.yml`: 1 source checkout(s); includes full-history fetch.
- `kr-alpha-atlas-phase-c-price-repair.yaml`: 1 source checkout(s); includes full-history fetch.
- `kr-alpha-atlas-phase-c.yml`: 1 source checkout(s); includes full-history fetch.
- `kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit.yml`: 1 source checkout(s); includes full-history fetch.
- `kr-alpha-discovery-tournament-v1.yml`: 3 source checkout(s); includes full-history fetch.
- `kr-corporate-action-collection.yml`: 5 source checkout(s); includes full-history fetch.
- `kr-factor-anatomy-v1.yml`: 2 source checkout(s); includes full-history fetch.
- `kr-industry-membership-foundation-v1.yml`: 1 source checkout(s).
- `kr-industry-membership-foundation-v2.yml`: 3 source checkout(s).
- `kr-industry-membership-foundation-v3.yml`: 4 source checkout(s).
- `kr-industry-membership-foundation-v4.yml`: 1 source checkout(s).
- `kr-industry-opportunity-anatomy-v1.yml`: 2 source checkout(s); includes full-history fetch.
- `kr-integrated-alpha-portfolio-v1-postoutcome-audit.yml`: 1 source checkout(s); includes full-history fetch.
- `kr-integrated-alpha-portfolio-v1.yml`: 3 source checkout(s); includes full-history fetch.
- `kr-market-risk-anatomy-v1-sources.yml`: 1 source checkout(s).
- `kr-market-risk-anatomy-v1.yml`: 2 source checkout(s); includes full-history fetch.
- `kr-market-risk-anatomy-v2.yml`: 2 source checkout(s); includes full-history fetch.
- `kr-market-risk-model-v1.yml`: 3 source checkout(s); includes full-history fetch.
- `kr-model-overlay-portfolio-v1.yml`: 1 source checkout(s); includes full-history fetch.
- `kr-original-xbrl-presentation-evidence-diagnostic.yml`: 1 source checkout(s); includes full-history fetch.
- `kr-original-xbrl-value-validation-v2.yml`: 1 source checkout(s); includes full-history fetch.
- `kr-original-xbrl-value-validation-v3.yml`: 1 source checkout(s); includes full-history fetch.
- `kr-original-xbrl-value-validation.yml`: 1 source checkout(s); includes full-history fetch.
- `kr-stock-within-industry-anatomy-v1.yml`: 2 source checkout(s); includes full-history fetch.
- `kr-top120-regime-review-v1.yml`: 2 source checkout(s); includes full-history fetch.
- `ledger.yml`: 1 source checkout(s).
- `market-industry-stock-foundation-v1.yml`: 1 source checkout(s).
- `pages.yml`: 3 source checkout(s); includes full-history fetch.
- `probes.yml`: 6 source checkout(s); includes full-history fetch.
- `replay.yml`: 1 source checkout(s).
- `seal-kr-factor-anatomy-v1.yml`: 5 source checkout(s); includes full-history fetch.
- `tests.yml`: 1 source checkout(s); includes full-history fetch.
- `universe.yml`: 2 source checkout(s).

## P2: twenty pre-existing open PRs (read-only)

Snapshot excludes this new P0 PR. Classification is a proposed disposition, not permission to merge/close. `MERGE_CANDIDATE` still requires exact-head checks, independent review and owner ordering; `ARCHIVE_KEEP_EVIDENCE` means preserve a completed or blocked study's evidence before considering closure, not delete its branch. PR bodies may describe older heads; CI here was fetched directly by the current full head SHA. All have successful pytest except #313 (failure). No review approval is inferred from CI.

| PR | Disposition / reason | Base ref @ SHA | Head (immutable evidence anchor) | Evidence path at head |
|---|---|---|---|---|
| [#314](https://github.com/jaehojung1879-netizen/Investment/pull/314) | **BLOCKED** — production ledger hook inherited from #306; independent review missing | `claude/compassionate-galileo-yunri9@98028fe4c8` | [`e366d7aa0b`](https://github.com/jaehojung1879-netizen/Investment/commit/e366d7aa0bcd4e5d77b357b83109f71f6dd75e33) | [`docs/daily-decision-report.md`](https://github.com/jaehojung1879-netizen/Investment/blob/e366d7aa0bcd4e5d77b357b83109f71f6dd75e33/docs/daily-decision-report.md) |
| [#313](https://github.com/jaehojung1879-netizen/Investment/pull/313) | **BLOCKED** — exact-head pytest failure plus source/authorization blockers | `main@37f8cbf6b1` | [`bd635edcdf`](https://github.com/jaehojung1879-netizen/Investment/commit/bd635edcdfa6a03e8e20ba81899f6f11c84296dc) | [`research/exp_c_recovery_validation_v1/README.md`](https://github.com/jaehojung1879-netizen/Investment/blob/bd635edcdfa6a03e8e20ba81899f6f11c84296dc/research/exp_c_recovery_validation_v1/README.md) |
| [#312](https://github.com/jaehojung1879-netizen/Investment/pull/312) | **ARCHIVE_KEEP_EVIDENCE** — sealed recovery evidence/design; execution remains gated | `main@37f8cbf6b1` | [`3b75bb0280`](https://github.com/jaehojung1879-netizen/Investment/commit/3b75bb0280e96e0c9e3024290b06921fa38188c5) | [`research/exp_c_recovery_oracle_v1/README.md`](https://github.com/jaehojung1879-netizen/Investment/blob/3b75bb0280e96e0c9e3024290b06921fa38188c5/research/exp_c_recovery_oracle_v1/README.md) |
| [#311](https://github.com/jaehojung1879-netizen/Investment/pull/311) | **ARCHIVE_KEEP_EVIDENCE** — completed descriptive decomposition, no alpha admission | `main@37f8cbf6b1` | [`e130c64fa0`](https://github.com/jaehojung1879-netizen/Investment/commit/e130c64fa0d998d9a8a34475838e6b9780fd9c9f) | [`research/market_industry_alpha_decomposition_v1/REPORT.md`](https://github.com/jaehojung1879-netizen/Investment/blob/e130c64fa0d998d9a8a34475838e6b9780fd9c9f/research/market_industry_alpha_decomposition_v1/REPORT.md) |
| [#310](https://github.com/jaehojung1879-netizen/Investment/pull/310) | **ARCHIVE_KEEP_EVIDENCE** — saved H1 result; H2 remains DATA_BLOCKED | `claude/alpha-mechanism-sprint-v1-shxr6w@f48b6f2999` | [`50055560de`](https://github.com/jaehojung1879-netizen/Investment/commit/50055560dee54d746949d53e05cc18b5f00813f6) | [`research/industry_information_transfer_v1/REPORT.md`](https://github.com/jaehojung1879-netizen/Investment/blob/50055560dee54d746949d53e05cc18b5f00813f6/research/industry_information_transfer_v1/REPORT.md) |
| [#308](https://github.com/jaehojung1879-netizen/Investment/pull/308) | **MERGE_CANDIDATE** — source/protocol parent of #310; review source rights and snapshots | `main@37f8cbf6b1` | [`f48b6f2999`](https://github.com/jaehojung1879-netizen/Investment/commit/f48b6f29993cf572d191f9724d19d2543f375f6c) | [`research/alpha_mechanism_sprint_v1/REPORT.md`](https://github.com/jaehojung1879-netizen/Investment/blob/f48b6f29993cf572d191f9724d19d2543f375f6c/research/alpha_mechanism_sprint_v1/REPORT.md) |
| [#309](https://github.com/jaehojung1879-netizen/Investment/pull/309) | **ARCHIVE_KEEP_EVIDENCE** — saved concentration/compounding evidence | `main@37f8cbf6b1` | [`84fe989f92`](https://github.com/jaehojung1879-netizen/Investment/commit/84fe989f92d348e88243090bcad5d7a1fe891a02) | [`research/portfolio_edge_forensics_v1/REPORT.md`](https://github.com/jaehojung1879-netizen/Investment/blob/84fe989f92d348e88243090bcad5d7a1fe891a02/research/portfolio_edge_forensics_v1/REPORT.md) |
| [#307](https://github.com/jaehojung1879-netizen/Investment/pull/307) | **MERGE_CANDIDATE** — report delta; after #299 or reviewed aggregate route | `codex/four-track-research-results@4d7fbbd83a` | [`03a72544c5`](https://github.com/jaehojung1879-netizen/Investment/commit/03a72544c513bed7d094d2ffb37239ce459ee133) | [`app.js`](https://github.com/jaehojung1879-netizen/Investment/blob/03a72544c513bed7d094d2ffb37239ce459ee133/app.js) |
| [#306](https://github.com/jaehojung1879-netizen/Investment/pull/306) | **SUPERSEDED** — all commits inherited by #314, which fixes an ETF baseline defect | `main@37f8cbf6b1` | [`98028fe4c8`](https://github.com/jaehojung1879-netizen/Investment/commit/98028fe4c8e5ea0c4829d1b1c381dbf730eccf13) | [`research/economic_path_readout_v1/README.md`](https://github.com/jaehojung1879-netizen/Investment/blob/98028fe4c8e5ea0c4829d1b1c381dbf730eccf13/research/economic_path_readout_v1/README.md) |
| [#305](https://github.com/jaehojung1879-netizen/Investment/pull/305) | **SUPERSEDED** — current head already contained in #306/#314 | `main@37f8cbf6b1` | [`e46024ca92`](https://github.com/jaehojung1879-netizen/Investment/commit/e46024ca92be16b5ded9c459797a7027c1d81d23) | [`research/economic_path_readout_v1/README.md`](https://github.com/jaehojung1879-netizen/Investment/blob/e46024ca92be16b5ded9c459797a7027c1d81d23/research/economic_path_readout_v1/README.md) |
| [#304](https://github.com/jaehojung1879-netizen/Investment/pull/304) | **SUPERSEDED** — current head already contained in #306/#314 | `main@37f8cbf6b1` | [`38926172b7`](https://github.com/jaehojung1879-netizen/Investment/commit/38926172b705ab998812709c91a7d805436cb617) | [`research/entry_state_role_etf_residual_v1/REPORT.md`](https://github.com/jaehojung1879-netizen/Investment/blob/38926172b705ab998812709c91a7d805436cb617/research/entry_state_role_etf_residual_v1/REPORT.md) |
| [#302](https://github.com/jaehojung1879-netizen/Investment/pull/302) | **ARCHIVE_KEEP_EVIDENCE** — M3 negative result and one-shot evidence | `main@37f8cbf6b1` | [`06d55d7fd6`](https://github.com/jaehojung1879-netizen/Investment/commit/06d55d7fd61284ce1c4d278b22f7a08249ee296d) | [`research/m3_backlog_v1/REPORT.md`](https://github.com/jaehojung1879-netizen/Investment/blob/06d55d7fd61284ce1c4d278b22f7a08249ee296d/research/m3_backlog_v1/REPORT.md) |
| [#301](https://github.com/jaehojung1879-netizen/Investment/pull/301) | **BLOCKED** — D1–D8 owner decisions null; no outcome registration | `main@37f8cbf6b1` | [`c9eaa036ea`](https://github.com/jaehojung1879-netizen/Investment/commit/c9eaa036eabd94da4bfa662fcf373604b8c73b1d) | [`docs/research-program/rp1-b-h1-outcome-v1-owner-review.md`](https://github.com/jaehojung1879-netizen/Investment/blob/c9eaa036eabd94da4bfa662fcf373604b8c73b1d/docs/research-program/rp1-b-h1-outcome-v1-owner-review.md) |
| [#300](https://github.com/jaehojung1879-netizen/Investment/pull/300) | **ARCHIVE_KEEP_EVIDENCE** — NO_GO power gate and C2 audit evidence | `main@37f8cbf6b1` | [`e580cde917`](https://github.com/jaehojung1879-netizen/Investment/commit/e580cde917673a0bd2d6a1ca21b010916721fa22) | [`research/independent_audit_c2_marketc_v1/README.md`](https://github.com/jaehojung1879-netizen/Investment/blob/e580cde917673a0bd2d6a1ca21b010916721fa22/research/independent_audit_c2_marketc_v1/README.md) |
| [#299](https://github.com/jaehojung1879-netizen/Investment/pull/299) | **MERGE_CANDIDATE** — reviewed read-only report parent of #307; currently non-Draft | `main@37f8cbf6b1` | [`4d7fbbd83a`](https://github.com/jaehojung1879-netizen/Investment/commit/4d7fbbd83afb82d3b83ebca81fc312e962bf41c9) | [`app.js`](https://github.com/jaehojung1879-netizen/Investment/blob/4d7fbbd83afb82d3b83ebca81fc312e962bf41c9/app.js) |
| [#297](https://github.com/jaehojung1879-netizen/Investment/pull/297) | **BLOCKED** — description promises AGENTS archive but actual delta is only CLAUDE.md + evidence boundary; reconcile scope | `main@35c0c0177f` | [`d124a3be46`](https://github.com/jaehojung1879-netizen/Investment/commit/d124a3be46539d2aacf8ad95319c5e398e87ac65) | [`CLAUDE.md`](https://github.com/jaehojung1879-netizen/Investment/blob/d124a3be46539d2aacf8ad95319c5e398e87ac65/CLAUDE.md) |
| [#290](https://github.com/jaehojung1879-netizen/Investment/pull/290) | **BLOCKED** — execution-disabled design; source and owner gates | `main@b589d658ee` | [`a72311c0d8`](https://github.com/jaehojung1879-netizen/Investment/commit/a72311c0d8873d33bd85577293fc1b00e179466c) | [`research/industry_alpha_next_v1/README.md`](https://github.com/jaehojung1879-netizen/Investment/blob/a72311c0d8873d33bd85577293fc1b00e179466c/research/industry_alpha_next_v1/README.md) |
| [#289](https://github.com/jaehojung1879-netizen/Investment/pull/289) | **BLOCKED** — cash/source rights/economic readiness unresolved | `main@b589d658ee` | [`92d78cd5ca`](https://github.com/jaehojung1879-netizen/Investment/commit/92d78cd5ca4f74225a2c9456d4f296c082280098) | [`docs/research-program/README.md`](https://github.com/jaehojung1879-netizen/Investment/blob/92d78cd5ca4f74225a2c9456d4f296c082280098/docs/research-program/README.md) |
| [#287](https://github.com/jaehojung1879-netizen/Investment/pull/287) | **BLOCKED** — rights, identity and return basis unresolved | `main@591f182955` | [`9a10baef60`](https://github.com/jaehojung1879-netizen/Investment/commit/9a10baef600078c132b6942e83f72b587cf0c581) | [`docs/winner-inflection-discovery/blocker-review-v3/pit-boundary-evidence.json`](https://github.com/jaehojung1879-netizen/Investment/blob/9a10baef600078c132b6942e83f72b587cf0c581/docs/winner-inflection-discovery/blocker-review-v3/pit-boundary-evidence.json) |
| [#286](https://github.com/jaehojung1879-netizen/Investment/pull/286) | **ARCHIVE_KEEP_EVIDENCE** — historical result/audit with unresolved corporate-action paths | `main@591f182955` | [`97aa2cfe2c`](https://github.com/jaehojung1879-netizen/Investment/commit/97aa2cfe2cabace05796f9179f2711cf83698d42) | [`research/historical_alpha_discovery_v1/README.md`](https://github.com/jaehojung1879-netizen/Investment/blob/97aa2cfe2cabace05796f9179f2711cf83698d42/research/historical_alpha_discovery_v1/README.md) |

### Verified ancestry and acceptable ordering

GitHub compare at the exact listed heads returned `behind_by=0` for each comparison: #304→#306 ahead 4; #305→#306 ahead 23; #306→#314 ahead 1; #299→#307 ahead 1; #308→#310 ahead 3. Thus these are actual inherited commits, not merely overlapping filenames. Ancestry preserves versions at those commits; it is not a separate off-repository backup or proof every later edit kept every output byte unchanged.

- Preferred review unit for the first stack is the complete #314 aggregate (including #306, #304 and #305). Review the production ledger hook and ETF baseline fix together. Do not merge #304/#305 again afterward. Alternatively #306→#314 follows today's explicit base relation, but exposes the known #306 baseline defect until the second merge; do not adopt that sequence without resolving this risk. If choosing the aggregate, owner-reviewed retarget to main and refreshed exact-head CI are prerequisites, not actions performed here. Avoid squash-merging components and then merging the unchanged aggregate, which loses ancestry recognition.
- #299→#307 and #308→#310 are valid base-first stacks with ancestry-preserving merges. Before merging any child (#307, #310 or #314), verify its base is main: after its parent lands, retarget the child from the feature branch to main, inspect the effective diff and refresh exact-head/base CI. Merging into the original feature-branch base does not integrate the child into main. After squash, child bases/diffs need independent reconciliation and new checks. Aggregate alternatives require owner retarget/review; do not merge the parents again afterward. #314 and #299 are different report entry points, not ancestry duplicates; reported clean composition in a PR body is not a current conflict test.
- Before any closure/deletion, preserve full head commit, relevant path/blob IDs, SHA256SUMS/source manifests and one-shot locks/results in durable approved storage and verify retrieval. Immutable Git links above are inspection anchors only. No preservation-driven branch deletion is authorized by this inventory. Closing stale design PRs needs owner review; source history size remains unchanged.
