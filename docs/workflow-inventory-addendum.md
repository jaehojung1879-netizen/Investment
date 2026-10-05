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

| `KR industry annual originals v2` (`kr-industry-membership-foundation-v2.yml`) | PR opened/updated on the exact foundation branch only; jobs `collect`, `chapters`, `retain` | **No schedule; no outcome execution mode** | Outcome-free v2 PIT industry-membership source acquisition. `collect`: frozen 254-issuer annual-original discovery plus collection in 26 immutable artifact slices (skipped per slice when its frozen inventory artifact exists; completed in run 37119776441). `chapters`: only the 68 classification-chapter requests frozen in `classification-chapters.json` before acquisition (skipped when its artifact exists). `retain`: downloads those exact artifacts, verifies every frozen-plan and archive SHA-256, and commits the bytes unchanged to the foundation branch (`contents: write`, same-repository branch only, skipped when already committed). Standard library collectors; DART key only in the discovery step; no prices, returns, models, portfolios or sealed-study execution. |

| `KR industry v3 source feasibility` (`kr-industry-membership-foundation-v3.yml`) | PR on the exact v3 foundation branch only | **No schedule; no outcome execution mode** | Runs only the four requests frozen in `research_specs/kr-industry-membership-foundation-v3/protocol.json` (KIND listed-company table, KRX 업종분류 현황 page and OTP, KIND 업종변경 search), standard library, no secrets, no retries or redirects, read-only contents. Retains raw bytes and hashes; admits nothing historical. |

| `KR industry v4 delisted-register probe` (`kr-industry-membership-foundation-v4.yml`) | PR on the exact v4 foundation branch only | **No schedule; no outcome execution mode** | Issues the single request frozen in `research_specs/kr-industry-membership-foundation-v4/protocol.json` (the official KIND delisted-company register page), standard library, no secrets, no retry or redirect; commits the raw bytes unchanged to the branch (`contents: write`, same-repository branch only). Admits nothing historical. |

| `KR industry opportunity anatomy v1` (`kr-industry-opportunity-anatomy-v1.yml`) | PR synthetic tests + outcome-free `verify` / `readiness`; manual `verify` / `execute` | **`verify` any time; `execute` only from merged `main`, by manual dispatch, after the protocol PR merges** | Exploratory industry-state anatomy over the frozen v4 membership and the preserved raw snapshot. Pull requests never execute. `execute` checks main-only, the committed spec, pinned membership, the exact artifact name / run / id / digest, the input identity, no committed result or marker and no execution lock; a durable exclusive git-tag lock is created after identities and readiness gates and before any outcome. Never reruns a sealed study; never contacts KRX, DART or KIND. State: PROTOCOL AND HARNESS ONLY — no outcome has been computed. |
| `KR stock within-industry anatomy v1` (`kr-stock-within-industry-anatomy-v1.yml`) | PR synthetic tests + outcome-free `verify` / `readiness`; manual `verify` / `execute` | **`verify` any time; `execute` only from merged `main`, by manual dispatch, after the protocol PR merges** | Exploratory read of the eleven registered stock features against stock minus LEAVE-ONE-OUT industry return, over the frozen v4 membership and the preserved raw snapshot. Pull requests never execute. `execute` checks main-only, the committed spec, pinned membership, the exact artifact name / run / id / digest, the input identity, no committed result or marker and no execution lock; a durable exclusive git-tag lock is created after identities and readiness gates and before any outcome. Never reruns a sealed study; never contacts KRX, DART or KIND. State: SPENT — the formal run (37196246044) is sealed in `docs/kr-stock-within-industry-anatomy-v1-result-seal.md`; `execute` now refuses (committed result and marker, and the git-tag lock). |
| `KR market risk anatomy v1 source snapshot` (`kr-market-risk-anatomy-v1-sources.yml`) | PR opened / reopened / synchronized on the exact study branch only | **No schedule; no dispatch; no execution mode** | Post-pre-source-freeze acquisition of the frozen source registry (FRED, Yahoo chart, FinanceDataReader): retains the raw vendor bytes, hashes, identity and a dates-and-counts metadata audit, and commits them unchanged to the branch (write permission on contents, same-repository branch only, `FRED_API_KEY` only). An ACQUIRED source is never refetched; a failed one is retried at most three times. Computes no return, drawdown, episode or result table and cannot change the frozen design. |
| `KR market risk anatomy v1` (`kr-market-risk-anatomy-v1.yml`) | PR synthetic tests + outcome-free `verify` / `readiness`; manual `verify` / `execute` | **`verify` any time; `execute` only from merged `main`, by manual dispatch, after the protocol PR merges** | MARKET-layer exploratory anatomy over the committed immutable source snapshot (and, for the extended tier, the preserved raw artifact). Pull requests never execute. `execute` checks main-only, the committed spec, the frozen design and snapshot pins, the exact raw artifact identity and no committed result, marker or lock; label-free readiness gates run first, then the durable exclusive git-tag lock, then the first value read. Never reruns a sealed study; never contacts a data vendor. State: PROTOCOL AND HARNESS ONLY — no outcome computed; the committed readiness decision is `DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY`, so a dispatch would stop at the gates without spending the study. |
| `KR market risk anatomy v2` (`kr-market-risk-anatomy-v2.yml`) | PR synthetic tests + outcome-free `verify` / `readiness`; manual `verify` / `execute` | **`verify` any time; `execute` only from merged `main`, by manual dispatch, after the protocol PR merges and a separate explicit authorization** | Corrected SOURCE-ADMISSIBILITY preregistration for the market-risk anatomy (historical admissibility separated from live freshness; session-based quality over expected XKRX sessions). Reads the exact immutable bytes retained by `kr-market-risk-anatomy-v1` and acquires nothing; v1 stays `DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY` and unchanged. Pull requests never execute. `execute` checks main-only, the committed spec, every pin, the exact raw artifact identity and no committed result, marker or lock; label-free gates run first, then the durable exclusive git-tag lock, then the first value read. State: SEALED — the formal one-shot run (`37244866236`) succeeded and its exact result is committed under `docs/results/kr-market-risk-anatomy-v2-*`; both execution-lock tags exist, so `execute` can never run again. |

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

## KRX authenticated reference-source extension (Draft PR #189)

`probes.yml` adds `krx-industry-openapi` to the existing manual menu. Its isolated
workflow_dispatch-only job receives KRX_API_KEY as AUTH_KEY only in the exact probe
step, uses read-only contents and persist-credentials:false, and excludes generic
probe jobs. Sixteen fixed requests at concurrency one inspect official reference
schemas and date acceptance; no price/return values, raw authenticated responses,
headers or logs are uploaded. No schedule, full-history acquisition, outcome execution
or automatic membership promotion. Plan and public official documentation hashes
are verified before authentication. Execution remains pending manual dispatch.

## Recommended pattern for future one-shot research studies

formal execution succeeds -> verify the immutable run / artifact / spec / lock identities -> automatically prepare a deterministic **Draft** result-seal PR -> a human reviews and merges the seal.

The automatic step must never rerun outcomes, alter or reformat results (the committed result and marker are the artifact's exact bytes), optimise or tune anything, or merge. It only verifies identities and copies verified bytes plus provenance. This is a convention for later studies, not a framework built here; `kr-market-risk-anatomy-v2` was sealed by hand to this pattern.
