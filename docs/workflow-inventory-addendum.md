# Workflow inventory — addendum for workflows added after a sealed study

`docs/workflow-inventory.md` is byte-pinned in the sealed `kr-model-overlay-portfolio-v1` specification
(`dependencyHashes`), so it can no longer be edited without breaking that sealed study's own identity check
(`HARNESS_OR_DEPENDENCY_CHANGED`). Workflows added from now on are therefore documented here, in the same
format, and `tests/test_workflow_inventory.py` reads both documents. Nothing in the main inventory is changed or
contradicted by this file.

## ACTIVE

| Workflow | Trigger | Scheduled | Purpose |
|---|---|---|---|
| `KR factor anatomy v1` (`kr-factor-anatomy-v1.yml`) | PR synthetic tests + outcome-free `verify`; manual `verify` / `execute` | **`verify` any time; `execute` only from merged `main`, by manual dispatch, after the protocol PR merges** | Exploratory / development / hypothesis-generating KR market map over the preserved v1 raw snapshot (`kr-model-raw-inputs-36844599518`). Pull requests never execute. `execute` checks main-only, the committed spec seal, the exact artifact name / run / id / digest and the input identity before any outcome is computed, never invokes the sealed KR v1 execute workflow and never contacts KRX. No PASS/FAIL or promotion semantics; see `docs/kr-factor-anatomy-v1-design.md`. State: PROTOCOL ONLY — no outcome has been computed. |
| `Seal KR factor anatomy v1 result` (`seal-kr-factor-anatomy-v1.yml`) | manual `workflow_dispatch` from merged `main` only | **No schedule; temporary** | Downloads the exact formal `kr-factor-anatomy-v1` result artifact inside Actions, verifies its archive SHA-256 before extracting, commits the exact bytes plus a provenance record to `research/kr-factor-anatomy-v1-result-seal` and opens one Draft PR. Recomputes no statistic and never merges; it is deleted by the result-seal change. |
