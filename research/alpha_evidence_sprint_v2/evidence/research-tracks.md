# Research tracks — status catalogue (as of 2026-11-03)

Read-only. main = `37f8cbf6`. Lanes follow Issue #292 (Market B+C=#289, Industry=#290, Stock-KR=#286, Stock-US=#287, Portfolio=#283/#280).
Classes: **COMPLETE** (executed, verdict supports hypothesis) · **EMPIRICAL_FAIL** (executed, negative / no nomination / contains zero) · **PARTIAL** (design, prospective, or outcome-blind only) · **SOURCE_BLOCKED** (data / rights / power / authorization missing). No item is COMPLETE. Machine-readable: `tracks.json`.

| Lane | Overall | Item | Class | Evidence (path @ commit, quoted verdict) |
|---|---|---|---|---|
| A Market | **EMPIRICAL_FAIL** | C1-KR `kr-market-risk-model-v1` (C0–C3) | EMPIRICAL_FAIL | `docs/results/kr-market-risk-model-v1-result.json` @37f8cbf6: `"NO_CANDIDATE_NOMINATED_CONTROL_RETAINED"`; net 6.73%/7.14% (C0/C1) vs passive 9.73% |
| | | Market C2 `C2_PREEMPTIVE_HIERARCHICAL` (KR) | EMPIRICAL_FAIL | same file: `C2.dominatedBy=[C0,C1,C3]`, `survives=false` |
| | | C1-US replication (#288 archive) | EMPIRICAL_FAIL | `docs/research-program/results/rp1-c1-us-exposure-formal-20261024/README.md` @37f8cbf6: `NO_CANDIDATE_NOMINATED_CONTROL_RETAINED` / `REPLICATED_CONTROL_RETAINED`; passive 8.82% vs C0 7.77%, C1 7.98%, C2 7.41% |
| | | C1c asymmetric exit × re-entry (#289) | PARTIAL | @92d78cd5 proposal: `DESIGN_PROPOSAL_ONLY / OUTCOME_EXPOSED / NOT_APPROVED / NO_EXECUTION`; audit @37f8cbf6: `DESIGN_NOT_READY_FOR_OWNER_APPROVAL` |
| | | B-H1 prospective state receipts (+#301 outcome draft) | PARTIAL | `rp1-b-h1-prospective-state-v1-ko.md` @37f8cbf6: `BLOCKED_OUTCOME_CONTRACT_NOT_REGISTERED`; #301 @c9eaa036 `OWNER_REVIEW_DRAFT_NOT_REGISTERED` (first H63 maturity 2027-02-02) |
| | | EXP-C-RECOVERY-01/02 (#312/#313) | SOURCE_BLOCKED | @3b75bb02 `NEW OUTCOME EVALUATION BLOCKED`; @bd635edc `NOT_EXECUTED … execution unavailable on checked source-access paths; recommend historical closure` |
| B Industry | **PARTIAL** | industry-alpha-next-v1 (#290) | PARTIAL | @a72311c0 README: `DESIGN_DRAFT / EXECUTION_DISABLED`; approval packet `PREPARED_NOT_AUTHORIZED` |
| | | KR membership foundation v1–v4; US dated industry | SOURCE_BLOCKED | hierarchy doc 07 §2.2 @37f8cbf6: `DATA_FOUNDATION_INSUFFICIENT_V4` (terminated 22: 0%); US industry "없음" |
| | | kr-industry-opportunity-anatomy-v1 | PARTIAL (descriptive) | report @37f8cbf6: `EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY … Not confirmatory` |
| | | industry-ocfyield-conditional-v1 (#300) | SOURCE_BLOCKED (power) | @e580cde9: `검정력 게이트: NO_GO`, power 23.0% at ρ=0.10; 193/610 usable dates |
| | | M3 backlog→shipments (#302) | EMPIRICAL_FAIL | @06d55d7f REPORT: `REJECTED (exploratory)`, skill −0.741581% [−2.103096%, −0.048090%] |
| | | industry-information-transfer-v1 (#310) | PARTIAL | @50055560: `H1 = KEEP` (fundamental forecast, "수익 주장은 아니다"), `H2 = DATA_BLOCKED` |
| C Stock-KR | **EMPIRICAL_FAIL** | Atlas Phase C / Phase D | EMPIRICAL_FAIL | `docs/kr-alpha-research-final-development-assessment.md` @37f8cbf6: BY/Holm pass **0**, `prospectiveNominations []`, Level 4 `NOT_TRIGGERED` |
| | | intraday/overnight momentum (#286) | EMPIRICAL_FAIL | @97aa2cfe README: "안정적인 추가 알파를 발견하지 못했다"; +1.99%p [−8.41, +16.69] |
| | | CHAMPION-C2 aggregate (#286) | PARTIAL | @97aa2cfe `c2_aggregate_evidence_v1/result-v2.json`: `"verdict":"INCONCLUSIVE"`, `validatedAlpha:false` |
| | | entry-state ETF residual (#304) | EMPIRICAL_FAIL | @38926172 REPORT: KR +1.739pp/yr [−2.779, +6.659] `CONTAINS_ZERO` |
| | | preliminary earnings sprint (#308) | PARTIAL | @f48b6f29: `ELIGIBLE_FOR_PROSPECTIVE_REGISTRATION_ONLY`; closure recommended |
| | | tournament / overlay / opportunity-v5 | SOURCE_BLOCKED / EMPIRICAL_FAIL / EMPIRICAL_FAIL | @37f8cbf6: `BLOCKED_BY_DATA_INTEGRITY`; `DEVELOPMENT_REJECT`; `overallStatus INCONCLUSIVE` |
| | | Study A KR A0 | PARTIAL | `rp1-kr-a0-measurability-v1.json`: A1 `GOVERNANCE_CLOSED`, `PROSPECTIVE_ONLY`, `MDE_UNRESOLVED` |
| C Stock-US | **SOURCE_BLOCKED** | WID execution recovery (#287) | SOURCE_BLOCKED | @9a10baef blocker-review-v3: rights/identity/returnBasis `BLOCKED`; `NOT APPROVED FOR EXECUTION` |
| | | Study A US A0 (#260) | SOURCE_BLOCKED | `rp1-a0-measurability-v1.json` @37f8cbf6: A1 `NO_GO`, `MDE_UNRESOLVED` |
| | | regional-alpha-model-v1 (31 features) | EMPIRICAL_FAIL | AGENTS.md v2.24: `{"US":"NO_MODEL_EVIDENCE","KR":"NO_MODEL_EVIDENCE"}` |
| | | entry-state US leg (#304) | EMPIRICAL_FAIL | @38926172: −1.142pp/yr [−6.462, +3.178] `CONTAINS_ZERO` |
| D Portfolio | **PARTIAL** | D v1 contract / D v2 (#265/#280/#283, merged) | PARTIAL | README @37f8cbf6: `BLOCKED_NO_VALIDATED_SELECTION_INPUT`; D v2 `PREREGISTERED_DESIGN_INACTIVE_NO_ALLOCATION` |
| | | kr-integrated-alpha-portfolio-v1 | EMPIRICAL_FAIL | AGENTS v2.47: `NO_UNAMBIGUOUS_FINAL_ARCHITECTURE`; D +15.01%/yr vs passive +20.24%, MDD −57.86% vs −40.69% |
| | | economic path readout (#305) | PARTIAL | @e46024ca: `INSUFFICIENT_SOURCE_EVIDENCE_NO_PROMOTION` |
| | | edge forensics (#309) | PARTIAL | @84fe989f: `INCONCLUSIVE — … 종목선정 알파는 식별하지 못했다` |
| | | market/industry decomposition (#311) | SOURCE_BLOCKED | @e130c64f: `BLOCKED — 반도체 귀속`, `INCONCLUSIVE — 베타·복리` |

## Alpha-mechanism hypothesis families (#308 / #310)

| Family | Class | Evidence |
|---|---|---|
| A — earnings information (KR preliminary earnings) | PARTIAL | #308 @f48b6f29: `ELIGIBLE_FOR_PROSPECTIVE_REGISTRATION_ONLY`; content 97.5% equals formal filing; lead 12 KRX days; detecting 4%p at H126 needs 11.4–33.7 years. #310 H2 `DATA_BLOCKED` (no Phase D exception). Returns read: 0 |
| B — industry diffusion | PARTIAL | #308: price-based version excluded as "새 정보 아님" (ρ≈0.99 momentum variants) and US source blocked. #310 disclosure-based H1 `KEEP` on revenue-forecast MSE (p 0.0085), but financials 89%; ex-financials+energy −0.000075. No return test |
| C — investor flow | SOURCE_BLOCKED | #308: KRX `REFUSED: HTTP 400 LOGOUT`, 0 records; DART large-holdings starts 2024-09-24; Phase C X4 `SOURCE_BLOCKED` |
