# c2-fixed-exposure-attribution-v1 — what still blocks execution (2026-11-04)

Contract: `research/alpha_evidence_sprint_v2/c2-fixed-exposure-attribution-v1.json` (sha256 `12f8f156…`). Nothing below
reads a C2 outcome.

| # | Blocker | Evidence | Smallest action that unblocks it |
|---|---|---|---|
| 1 | **Investable KRW cash return** (primary cash leg) | `config.json` `ecos.KR`: `KTB_3Y` = `817Y002` / item `010200000`, `LIVE_VALIDATED_SOURCE`; no CD91, KOFR, MMF or T-bill item is configured. `BaseRate` (`722Y001`) and `CorpBond_3Y` are `AMBIGUOUS_SOURCE`. `pipeline/ecos_macro.resolve_spec` refuses any series without a validated item code and cycle. `ECOS_API_KEY` exists only as a GitHub Actions secret (`ledger.yml`, `pages.yml`, `probes.yml` reference it); it is not set in this environment (0 matching env vars), so no live ECOS call was made. | Owner dispatches the existing `probes.yml` ECOS probe for table `817Y002`, daily cycle, to read the item list and validate the **CD(91일)** item code from ECOS's own response (not guessed here). Then add one `LIVE_VALIDATED_SOURCE` entry with its validation-evidence hash and pin the series by content hash. Until then the registered cash band {0, BOK proxy, BOK + 100bp} is the only cash input. |
| 2 | Owner execution authorization | Phase D closure §7 (`docs/kr-alpha-research-final-development-assessment.md`) | Owner commits `research/alpha_evidence_sprint_v2/AUTHORIZATION-c2.json` with the exact phrase, spec sha256 and the two code hashes. |
| 3 | Corrected ETF pre-anchor depth | 251 quotes before 2013-01-07 (verified, `evidence/c2-source-inventory.md` item 4) | None needed: the spec's 200-pair beta floor is met (≤ 250 ETF returns in the first windows); counted, not filled. |
| 4 | Industry (Brinson) split | no KODEX200 constituent or sector-weight history in the repository | Out of scope for this contract; stays `UNAVAILABLE`. A licensed or official KOSPI200 weight history would be a separate data acquisition. |
| 5 | Held names without dividend lineage | 5 names (000030, 000060, 002550, 047040, 207940) with zero dividend events | Carried as a known price-return-basis limitation (disclosed in the spec); not a blocker. |

Executing with blocker 1 unresolved is allowed by the contract (band verdict), but the result can only be
`SELECTION_SURVIVES_FIXED_EXPOSURE` if all three cash scenarios agree.
