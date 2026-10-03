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
| `KR Top120 regime review v1` (`kr-top120-regime-review-v1.yml`) | PR synthetic tests + outcome-free `verify`; manual `verify` / `execute` | **`verify` any time; `execute` only from merged `main`, by manual dispatch, after the protocol PR merges** | Exploratory post-outcome regime diagnostic over the sealed `kr-factor-anatomy-v1` result and its preserved raw snapshot. Pull requests never execute. `execute` checks main-only, the committed spec, the sealed predecessor identities, the exact artifact name / run / id / digest, the input identity, no committed result or marker and no earlier results artifact; the marker is written only after identities and readiness gates pass. No PASS/FAIL or promotion semantics; see `docs/kr-top120-regime-review-v1-design.md`. State: PROTOCOL ONLY — no outcome has been computed. |
| `Market industry stock foundation v1 metadata audit` (`market-industry-stock-foundation-v1.yml`) | PR when foundation paths change; manual metadata audit | **No schedule; no execution mode** | Standard-library identity/source-readiness audit only. Does not read prices, historical outcomes or result payloads; cannot fit, select industries or construct a portfolio. Return math is unit-tested on synthetic fixtures separately by Tests. No secrets or write permissions. |

| `KR industry membership foundation v1 source acquisition` (`kr-industry-membership-foundation-v1.yml`) | PR opened on the exact foundation branch only | **No schedule; no outcome execution mode** | Bounded public DART receipt acquisition from the frozen 413-target plan, 21 immutable artifact slices, at most four workers and three requests per receipt. Standard library only; contents read permission; no secrets, ECOS, current-profile backfill, prices, models, portfolios or sealed study execution. Completed source run 37096833360 is retained in the foundation provenance. Synchronize events do not recollect sources. |

## Foundation observation on existing lifecycle (2026-10-03 KST)

The older PROTOCOL ONLY descriptions above record their authors' then-current state;
they are not today's execution authority. KR anatomy now has a committed result seal.
Top120 regime-review dispatch 37018055459 completed and its durable lock exists at
main 9504f970a2895781eedcc3a6a1c94126fd4682f8; result artifact 11232463461 exists
(archive digest recorded in the new foundation design). Only provenance metadata was
checked here, not result contents. Neither closed study can be rerun by this foundation.

## ECOS manual source-validation extension (PR #188)

`probes.yml` adds `ecos-market-context` to the existing manual dispatch menu.
Its separate job requires workflow_dispatch and maps only the ECOS secret to
ECOS_API_KEY. Other probe jobs exclude this option. PR jobs receive no ECOS
credential. It reads BOK metadata and at most latest-period smoke observations,
saves only sanitized source identities/coverage/status, and computes no Alpha
outcomes. No schedule, production wiring or sealed study rerun is introduced.
The foundation metadata workflow remains credential-free on PR events.
