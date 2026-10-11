# Full-suite CI timeout and historical workflow provenance v1

Base: actual `main` `f81be25dceb1a29a665d02ab6d9dd5505378e876`.
This is an operational maintenance change. It authorizes no research execution,
new outcome access, model fitting, deployment, or trading-policy change.

## Operational change

The existing `Tests / pytest` job now has `timeout-minutes: 60`. Its triggers,
permissions, concurrency, complete `python -m pytest -q` invocation, lint/import
gates, Python version, single-thread settings, full Git checkout and pinned input
fetches are unchanged. The budget covers the entire job, including setup and
post-test import checks. No tests are removed, selected out, newly skipped, or
newly marked xfail. Existing xfails remain repository baseline behavior.

PR #221's run [38123415524](https://github.com/jaehojung1879-netizen/Investment/actions/runs/38123415524)
was cancelled: its lint/setup steps succeeded and the suite step was cancelled
before the import step. Cancellation is not a passing suite or an observed
assertion failure. The historical timing measurements in
`docs/weekly-decision-operations.md` explain the runner variance and expensive
synthetic Phase C checks; they are not measurements of this branch.

## Pin audit

All 73 JSON specifications/manifests in `research_specs/` and all tracked source,
script, test and documentation references were searched for the workflow path.

| Record or validator | Pin and treatment |
| --- | --- |
| `kr-alpha-atlas-phase-c-v1.json` | Direct `dependencyHashes` pin; 113 dependencies and 235 protected identities remain unchanged. |
| `kr-alpha-atlas-phase-c-v2-amendment.json` / `kr_alpha_atlas_phase_c_amendment.load` | Inherits the v1 dependency map via `contract.load`; additional pins still verify current bytes. |
| `kr-alpha-atlas-phase-c-v3-price-repair.json` / `kr_alpha_atlas_mirae_repair.load` | Inherits v2/v1; effective contract and dependency digest still verified. |
| `kr-alpha-atlas-phase-c-v4-numerical-reproducibility.json` / `kr_alpha_atlas_reproducibility.load` | Inherits v3/v2/v1; exact numerical/environment and effective-contract checks unchanged. |
| `alpha-research-design-review-v1-sources.json` | Historical review receipt, explicitly `isSeal: false`; hash `818b2cd9…` verified at its `baseMainCommit` `2c5b6849…`. It is also protected opaquely by Phase C. No current-workflow enforcement or receipt rewrite. |
| `kr_alpha_atlas_phase_c.contract.build/validate/load` | `build` used current bytes, including its own source. `validate` now resolves only the two explicitly registered compatibility identities before the original complete-registration comparison. |
| Phase C lifecycle and v2/v3/v4 formal paths | Still call the validators before input/lock/outcome boundaries. No authorization, lock, result namespace or formal workflow changes. |
| `tests/test_research_terminal.py` | PR-scope byte guard, not a historical research specification. It now permits exactly the authorized 30-to-60 timeout change and retains every other equality assertion. |

No other direct workflow pin was found. Indirect inherited validators and opaque
protection of the review receipt are included above. Original source hashes are
preserved inside the unchanged specifications, rather than regenerated.

## Versioned compatibility

`historical-workflow-provenance-v1.json` is a new operational compatibility record;
it is not a replacement research registration. It identifies the existing v1
registration at `8c3611116c5103a1e860173b180d0094e45b3074`, where the current sealed
specification was last registered, with exact specification SHA-256
`b57be30ce54abf1dd26388954053e99d4b1bf71fa06f3598787317e953988db0`.

When a current-vs-sealed comparison differs, the validator requires:

1. That full registration commit to be an ancestor of checkout `HEAD`.
2. Exact historical specification bytes, exact current specification bytes and
   the unchanged historical/current sidecar, all matching the known digest.
3. Historical workflow and original validator bytes from `git show`, each
   matching its original sealed dependency hash.
4. Current validator bytes matching the separately registered compatibility
   validator SHA-256. Any additional validator edit fails until explicitly
   reviewed and recorded as an operational compatibility change.
5. The original full structural comparison, after normalizing only the workflow
   and validator identities in the newly constructed comparison object.

The original validator is itself in the sealed import closure. Therefore its
historical identity must be verified alongside the historical workflow; merely
exempting the workflow would still invalidate the seal. The new adapter imports
only the standard library and introduces no new scientific import dependency.
Every other current dependency, formula, protected artifact, schema and lifecycle
field remains subject to the original exact checks. `file_hash` and `build`
continue to report actual current bytes; only the comparison object is normalized.
`load` still returns the unchanged sealed specification and original dependency
manifest. v2/v3/v4 consequently retain their exact existing effective digests.

The current operational workflow can evolve without rewriting historical research
hashes. Missing Git objects, shallow/unrelated history, unknown policy versions,
expanded exemption paths, modified specs/sidecars or unregistered validator edits
fail closed. There is no network fetch or fallback to a newer commit inside the
validator. CI already checks out full history. These checks verify historical
provenance and current scientific-code compatibility; they do not assert that the
current operational workflow is byte-identical to the historical one.

Future changes to scientific dependencies still require their own research
protocol decisions. This narrowly scoped mechanism does not make arbitrary
research changes compatible with an old seal and does not authorize executing
an old study. Do not run `freeze` to update a historical registration.

## Validation and execution-time assessment

Focused validation: 85 tests passed, including chronology/provenance, inherited
amendment integrity, and terminal guards. Ruff, pipeline compilation and the same
entry-point import/script compilation check used by CI passed. Seed validation
runs only on isolated synthetic output in `/tmp`, with production rejection
preserved.

The complete local suite uses the existing single-thread environment, adding
`--durations=40` and a temporary JUnit report for measurement only. Final measured
suite results and GitHub CI status are reported in the PR validation record.
Measurement files stay outside the repository and no research result is generated.

Fast/slow splitting is feasible by **whole test file**, using disjoint sets whose
union equals the full collected suite. Individual test splitting would duplicate
module-scoped setup, including the expensive synthetic `complete` fixture in
Phase C. Any later split should verify node-ID union/intersection and run each
file exactly once; running a fast subset plus a separate full suite duplicates
work. This change retains the existing single complete job, which is the smallest
fix and preserves all coverage and setup sharing. A split is not needed to remove
the current 30-minute budget, and does not by itself bound the expensive group.

An actual collection-only check found **4,372 unique node IDs**. A candidate split
placing `test_kr_alpha_atlas_phase_c.py` and `test_kr_alpha_atlas_mirae_repair.py` in
the expensive group yields 43 slow-group tests and 4,329 remaining tests, zero
intersection and a union of all 4,372 collected tests. These groups were assessed,
not installed as separate CI jobs. Names in the remaining group do not guarantee
that every individual test is fast; measured durations belong to the PR record.

The 60-minute limit eliminates the known 30-minute cancellation boundary; it
cannot guarantee arbitrary future suites or infrastructure delays finish within
60 minutes. A genuine assertion failure must still fail CI, and concurrency
cancellation on a newer push remains intentional.
