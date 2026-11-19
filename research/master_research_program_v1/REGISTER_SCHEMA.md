# RESEARCH_OPPORTUNITY_REGISTER — entry schema (v1)

Each lane writes `register-entries.json` = `{"entries": [ ... ]}` in its own folder. `evidence_map/register.py`
loads every such file under `research/master_research_program_v1/`, validates and orders them.

| Field | Type / vocabulary |
|---|---|
| researchId | unique string; prefix `X-` existing/closed study, `M-` market, `I-` industry, `S1-`..`S5-` stock, `P-` portfolio, `D-` data foundation |
| region | `KR` / `US` / `COMMON` |
| track | `MARKET` / `INDUSTRY` / `STOCK` / `PORTFOLIO` / `DATA` |
| title | short name |
| economicMechanism | why it should earn 6–12M ETF-relative net return |
| overlapWithExisting | which existing features/studies it duplicates or is distinct from (with ids) |
| pitSourceAndRights | source, PIT semantics, license/access status |
| h126h252Feasibility | `FEASIBLE` / `PROSPECTIVE_ONLY` / `BLOCKED` + reason |
| effectiveSampleAndMde | text with numbers where measured, else `UNKNOWN` (never invented) |
| transactionCostMeasurable | `YES` / `PARTIAL` / `NO` + reason |
| expectedEconomicImportance | `HIGH` / `MEDIUM` / `LOW` + reason |
| prerequisitesAndBlockers | list of strings |
| evidenceClass | `VERIFIED_EVIDENCE` / `EXPLORATORY_EVIDENCE` / `EMPIRICAL_FAIL` / `SOURCE_BLOCKED` / `PREPARED_NOT_EXECUTED` / `PROSPECTIVE_PENDING` / `NOT_STARTED` |
| progressStatus | `ACTIVE` / `SOURCE_BACKLOG` / `CLOSED` / `PARKED` |
| highestGatePassed | `NONE` / `G0`..`G6` |
| failedGate | `null` or `G0`..`G6` |
| nextExecutionUnit | one concrete next step |
| ownerApprovalRequired | bool |
| priority | `{"tier": "P1"|"P2"|"P3", "netReturnRelevance": 0-3, "mechanism": 0-3, "independence": 0-3, "sourceObtainable": 0-3, "timeToDecision": 0-3, "krUsExtensible": 0-3}` |
| evidenceRefs | list of `path@commit` or `PR #n@sha` strings |
