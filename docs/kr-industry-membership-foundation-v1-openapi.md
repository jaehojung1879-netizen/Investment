# Official authenticated KRX reference route — bounded extension to Draft #189

Accepted baseline: `f89bf8066e4c2ed54378d8e7bfbec17c2b4cc4bf`. The 413-receipt DART
collection and anonymous OTP/CSV probe are not repeated. No sealed study or outcome
payload is opened. The existing 610 signal dates, 73,200 name-date denominator,
260 ever-Top120 names, identity/terminal contracts and all frozen criteria remain unchanged.

## Current official contract, inspected before acquisition code

The official catalog, three basic-information developer specifications, daily
specification, usage instructions, terms and June 1, 2026 notice are retained under
`data/kr-industry-membership-foundation-v1/krx-openapi-docs`. Its manifest records
official URLs, BO_IDs, request parameters, acquisition timestamps, exact retained-byte
SHA-256 and extracted schema. DOCX specifications are public source documents;
their placeholder samples contain no real observations or repository credentials.
The three basic services also retain the exact decoded public contract XML.

| Official service | API ID / endpoint suffix after `https://data-dbg.krx.co.kr/svc/apis/` | Date argument | Industry fields |
|---|---|---|---|
| 유가증권 종목기본정보 | `sto/stk_isu_base_info` | `basDd`, YYYYMMDD | None |
| 코스닥 종목기본정보 | `sto/ksq_isu_base_info` | `basDd`, YYYYMMDD | None |
| 코넥스 종목기본정보 | `sto/knx_isu_base_info` | `basDd`, YYYYMMDD | None |
| 유가증권 일별매매정보 — authentication/date control, schema only | `sto/stk_bydd_trd` | `basDd`, YYYYMMDD | None |

All three basic schemas are exactly: `ISU_CD`, `ISU_SRT_CD`, `ISU_NM`, `ISU_ABBRV`,
`ISU_ENG_NM`, `LIST_DD`, `MKT_TP_NM`, `SECUGRP_NM`, `SECT_TP_NM`,
`KIND_STKCERT_TP_NM`, `PARVAL`, `LIST_SHRS`. Standard/short code are the identifiers;
`MKT_TP_NM` is market. `SECT_TP_NM` is **소속부**, not economic industry.
Security group and stock type likewise are not industry taxonomies. The official
public contract filters requested basDd against issue/security-group date intervals;
this supports dated reference queries, but supplies no industry assignment or
release/vintage proof. A start date of 2010-01-04 (KONEX 2013-07-01) is a service
coverage boundary, never by itself proof of PIT industry membership.

The daily control schema is pinned in the official manifest. Its `BAS_DD`, `ISU_CD`,
`ISU_NM`, `MKT_NM`, `SECT_TP_NM` are relevant to date/identity/schema checks. No price,
volume, return or other observation value is exported, summarized or used. The runner
only projects column names, row counts and date-match booleans; it never computes returns.

The official usage process separately approves a key and each requested API service.
The terms limit a key to 10,000 requests/day. The official June 1 notice says the
published service catalog defines Open API offerings; unlisted data require the
Marketplace screen/download or data purchase. This observation does not imply that
historical KRX industry data do not exist elsewhere.

## Frozen authenticated feasibility plan

`research_specs/kr-industry-membership-foundation-v1/krx-openapi-feasibility-plan.json`
and its sidecar are committed before the first authenticated request. Four fixed dates:
2015-01-02, 2020-01-02, 2023-01-02, 2026-09-01. Only date representation changes to
YYYYMMDD; there is no economic date substitution. Four documented services × four
dates, **16 requests maximum**, concurrency **1**, at least **1 second** between
requests, 30-second timeout, 8 MB response cap, no retries and no redirects.
No full-history acquisition is authorized by this plan. Any expansion requires actual
historical industry proof and a separate pre-existing committed acquisition plan/parser.

The existing `probes.yml` manual menu gains `krx-industry-openapi` and a separate
`workflow_dispatch`-only job. Generic jobs exclude it. Checkout uses
`persist-credentials: false`; contents permission is read-only. Only the exact probe
step receives `AUTH_KEY: ${{ secrets.KRX_API_KEY }}`. The script sends it only as
the HTTP `AUTH_KEY` header to the fixed official host/endpoints. It never puts the
key in a URL, CLI argument, artifact, hash, log, header metadata or exception output.
All authenticated response bytes are checked for credential material before hashing;
credential-bearing/sensitive-account responses abort without retained evidence.

Only fixed-name sanitized metadata JSON and its SHA-256 sidecar can be uploaded.
No raw authenticated response, rows, identifiers, request headers or logs are retained.
The metadata records service/date/nonsecret parameters/status/content-type category,
exact safe response SHA-256/byte length, schema/count, identifier/market/industry field
names and explicit semantics. Empty/error bodies and schema drift fail closed.
`Unauthorized API Call` means service not approved; other failures leave approval
unresolved. Neither is a claim that the source does not exist.

## Execution status and current decision

**NOT_EXECUTED.** No authenticated request has yet been made. The available GitHub
connector exposes GET and rerun operations but no workflow_dispatch operation.
This is an orchestration capability limitation, not KRX authentication failure,
unapproved-service evidence or source unavailability. Service approval status and
actual historical-date acceptance remain unobserved until a manual run is retained.
The official specifications already establish absence of economic industry fields
in these four documented schemas. Successful authentication or dated reference rows
would still not supply historical industry membership.

Current accepted foundation decision: **DATA_FOUNDATION_INSUFFICIENT**.
Admitted industry rows remain 0; all 73,200 research name-dates retain UNKNOWN,
coverage 0%, selected taxonomy/granularity null. This is not presented as the result
of a completed authenticated probe. The existing corrected adjacent-classification
availability gate remains unchanged; no stability threshold is added.

NO HISTORICAL INDUSTRY RETURN WAS COMPUTED
NO FACTOR OR ALPHA OUTCOME WAS INSPECTED
NO CURRENT INDUSTRY CLASSIFICATION WAS BACKFILLED INTO HISTORY
NO TAXONOMY OR GRANULARITY WAS CHOSEN FROM FUTURE RETURNS
NO KRX AUTHENTICATION SECRET WAS LOGGED OR PERSISTED
NO SEALED PRIOR STUDY WAS RERUN
