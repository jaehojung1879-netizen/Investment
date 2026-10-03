# KR industry membership foundation v1

**Decision: `DATA_FOUNDATION_INSUFFICIENT`.** No taxonomy or granularity is selected. This is a source-acquisition and PIT-membership foundation, with no authorization to run an industry-return study or promote production readiness.

## Acquired evidence

The fixed plan acquired all **413 exact DART annual-report receipts**: 175 from the earliest retained fiscal-2015 inventory and 238 from fiscal-2023. Source-only GitHub Actions [run 37096833360](https://github.com/jaehojung1879-netizen/Investment/actions/runs/37096833360) completed successfully at producer commit `de2da7cf66a858f7edf78dd80facd05a2a11280b`. Its 21 artifacts were downloaded by exact artifact ID; ZIP size and SHA-256 were verified against GitHub's artifact digests before extracting the two expected batch files. Artifact IDs, digests, verified ZIP hashes and producer are retained in `artifact-provenance.json`. This is a completed collection, not a proposed memo.

The run made **1,199 public requests**, within the frozen 1,239-call ceiling and four-worker ceiling. It retained 393 successful receipt pages and parsed 786 successful overview sections; HTTP failures and raw response bytes are retained as evidence too. Raw bytes are content-addressed SHA-256/base64 objects inside 21 deterministic gzip archives. The offline verifier reproduces hashes, target order, source markers and receipt identity. No ECOS or authenticated OpenDART company-profile API was contacted. Existing 92 terminal-action filing documents are reused byte-for-byte and verified against their original member hashes; terminal economics are untouched.

The reading list has 112 sections containing classification markers or code-shaped tokens; these sets overlap. All 22 classification-marker sections were reviewed. Twelve reported issuer/business observations are recorded separately, including SK Hynix's reported `321`, Hyundai Steel's `241`, Douzone's `J58222`, NCSoft's `58211`, HD Hyundai Infracore's `29111`, and Kakao Pay's `K6619`. These are **as-reported observations**, without an inferred KSIC edition or division/group prefix. Aircraft/product identifiers in other lexical candidates are not classifications. Hankook-related reports contain multiple segment/entity codes (`C29292`, `C29294`, and later `G47711`); these cannot be transferred to a parent security. Five retained terminal-document mentions concern merger appraisal/another merger party, not an independently established assignment to `053000.KS`.

No observation establishes all required dated security subject, taxonomy edition/codebook, economic validity interval and publication visibility. A sparse filing assertion does not prove classification throughout a fiscal year or until the next filing. **Zero membership rows are admitted.** This says what this retained evidence can prove, not that historical classifications do not exist.

## Other authoritative source attempts

The official KRX industry page was retrieved successfully. Dated KRX POST attempts for `20130102` and `20260901` returned HTTP **403**; exact request parameters and response bodies are retained. Official KSIC 10/11 codebook and transition download attempts returned HTTP **502**, so no failed response is treated as a codebook. The OpenDART company API guide was retained, but its company-profile classification has no historical as-of contract and was not backfilled. `reference-sources/manifest.json` records URLs, acquisition times, status, bytes and hashes. These are bounded feasibility checks, not claims that every official historical route is exhausted.

Fiscal inventory labels do not establish release dates: for example fiscal-2023 inventory receipt `20260630000500` is a late correction. It is retained as the exact planned source and never silently substituted for an original 2024 report. Receipt identifiers alone cannot prove an economic interval or original publication visibility.

## Immutable mapping and reused contracts

The admitted mapping contract is `security_id, ticker, taxonomy_id, taxonomy_version, industry_id, valid_from, valid_to, release_date, known_to, source, source_sha256, identity_provenance`, with existing foundation fields `region, source_date, evidence_kind`. Existing `industry_foundation.Membership` validates intervals, source hashes and identity provenance. Existing visibility semantics require release strictly before the signal, evidenced economic validity, and any knowledge expiry. Current-snapshot classifications cannot be admitted. Exact retained proof references and unique locators are required for identity, version, codebook, validity and release; lexical matches alone do not establish semantic truth.

The universe is the existing frozen KR PIT Top120 at source commit `4ea107ed0cde289f0a049a65ff13d2441a786710`: 14 pinned shards, 164 monthly snapshots, 260 ever-members. Each signal uses exactly 120 securities from the strictly previous rank snapshot. There is no current-member union or price/eligibility filtering. Existing `KRX:<ticker>` security identifiers, issuer mapping provenance and all 22 terminal-action security identities are retained. Existing issuer mappings cover 254 of 260 securities; this retrospective bridge does not itself establish a dated identity/classification link. No successor, preferred-share, company-name or current-industry inference is applied.

`membership.json` contains the empty admitted mapping, its canonical SHA-256, and explicit UNKNOWN records for all 260 securities, with unknown classification fields null and available identity provenance retained. UNKNOWN stays in every signal-date and annual denominator. Missing industry is not a group.

## Frozen outcome-blind criteria and audits

Criteria and exact source inventory were frozen locally before acquisition; original commit-object bytes and independently verified Git SHA-1s are retained in `freeze-provenance.json`. These local objects are not claimed as remote publication timestamps. The original interrupted collection checkpoint is archived separately and excluded from formal acquisition counts. The completed GitHub run uses the unchanged criteria and exact plan.

Candidate order is KRX native as published, KSIC 2-digit division, then KSIC 3-digit group. The first candidate passing every gate is selected; otherwise taxonomy/granularity stay null. No future returns or performance select granularity.

| Gate | Frozen requirement | Verified result, all three candidates |
|---|---:|---:|
| Each signal-date full-universe coverage | >=90% | 0/120, 0% |
| Each annual name-date coverage | >=90% | 0% |
| Adjacent repeated-name classification availability | >=90% | 0% |
| Constituents in a sufficient group | >=5 | No admissible groups |
| Sufficient groups per signal | >=3 | 0 |
| Classified fraction in sufficient groups | >=90% | null: no classified denominator |
| Dated version, codebook, identity, validity | Required | Not established |

The research audit covers **610 completed weekly KR signal dates**, 2015-01-02 through 2026-09-11, **73,200 full-universe name-dates**. Machine-readable per-date audits include all missing security IDs and reasons, group counts and strictly previous snapshot dates. Annual audits also include supplementary 2013 onward history; this extended audit does not enlarge the preregistered research eligibility window. Terminal-security audits preserve missing terminated names rather than selecting survivors.

| Year | Signal dates | Full name-date denominator | Classified |
|---|---:|---:|---:|
| 2015 | 53 | 6,360 | 0 |
| 2016 | 52 | 6,240 | 0 |
| 2017 | 51 | 6,120 | 0 |
| 2018 | 52 | 6,240 | 0 |
| 2019 | 52 | 6,240 | 0 |
| 2020 | 53 | 6,360 | 0 |
| 2021 | 52 | 6,240 | 0 |
| 2022 | 52 | 6,240 | 0 |
| 2023 | 52 | 6,240 | 0 |
| 2024 | 52 | 6,240 | 0 |
| 2025 | 52 | 6,240 | 0 |
| 2026 through Sep 11 | 37 | 4,440 | 0 |

## Reproduction and next evidence need

Run `python scripts/build_kr_industry_membership_foundation.py --verify` for an offline hash-closed reproduction. The standalone spec and SHA-256 sidecar pin the new inputs, raw archives, review decisions, code, tests and outputs. Fresh output directories are required for regeneration; retained inputs are immutable. Unit tests use explicitly synthetic classifications solely for admission/calendar/coverage boundaries. Repository seed validation is a synthetic fixture check, not a historical study.

The bounded two-era collection does not supply continuous annual history. The next useful acquisition is an authoritative dated KRX classification export or a versioned historical KSIC assignment source with explicit subject identity, validity and original release evidence. Access to that source must precede a later preregistered study. Current classifications, filing-year edition guesses and sparse-observation carry-forward cannot repair this gap. No historical industry return, factor performance, Alpha outcome, fit or portfolio result was computed; no sealed prior study or ECOS probe was rerun. Existing research logic, production sector code, terminal-action economics and frozen study files are unchanged. The PR remains Draft and is not merged.


## Official KRX OTP -> CSV feasibility extension

Baseline PR head `337192c2591e81944f3a4fb6dcedc2d9fa3930f5` and the completed 413-receipt DART collection remain accepted and unchanged. The separate feasibility plan was published **before any new KRX requests** in commit `6ab3555db4c4a0ae6d63654d9e608b22c0ca4f23`; plan SHA-256 is `1fd169376b2537c603eca2d18a4420addbc5a4ab5c90fb14c93ab8a684787373`.

The exact route tested is form-urlencoded POST `https://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd`, with `url=dbms/MDC/STAT/standard/MDCSTAT03901`, `locale=ko_KR`, `mktId=STK`, explicit historical `trdDd`, `money=1`, `csvxls_isNo=false`, `name=fileDown`; followed conditionally by POST `https://data.krx.co.kr/comm/fileDn/download_csv/download.cmd`, `code=<valid OTP>`. KOSPI/STK is the relevant market because every pinned universe ticker has a KS suffix. No KOSDAQ/current-universe union was added.

Two fixed browser-style Referer profiles were tested: the official dataset page and official Marketplace `mdiLoader`. Each starts with a session GET and uses an anonymous cookie jar, a reasonable browser User-Agent and explicit form Content-Type. No login credentials are used, cookies are not persisted, redirects and retries are disabled. The bounded plan allows 18 requests, one worker, 15 seconds/request and a 2 MiB body ceiling; all 18 planned requests completed. This does not change any taxonomy/admission/coverage gate or authorize full-history collection.

| Requested and effective KR date | Dataset-page OTP | Marketplace-loader OTP | CSV endpoint negative control, both profiles | Historical classification rows |
|---|---|---|---|---:|
| 2015-01-02 | HTTP 200, `LOGOUT` | HTTP 200, `LOGOUT` | HTTP 403, error HTML | 0 |
| 2020-01-02 | HTTP 200, `LOGOUT` | HTTP 200, `LOGOUT` | HTTP 403, error HTML | 0 |
| 2023-01-02 | HTTP 200, `LOGOUT` | HTTP 200, `LOGOUT` | HTTP 403, error HTML | 0 |
| 2026-09-01 | HTTP 200, `LOGOUT` | HTTP 200, `LOGOUT` | HTTP 403, error HTML | 0 |

All four dates are trading days under the unchanged pinned KR calendar, so no substitution occurred. A non-session date would use the immediately prior KR session and record both dates and a substitution reason; tests cover that boundary.

**No valid OTP was issued and no genuine OTP exchange occurred.** For each rejected OTP, the preregistered empty-code CSV POST is explicitly `CONTROL_NO_VALID_OTP`, a download-endpoint negative control. `LOGOUT` is never forwarded as a code. The HTTP 403 responses are Korean KRX error-page HTML, not CSV; their full exact error text and bytes are retained. The dataset-page bootstrap returned HTTP 200; the bare `mdiLoader` bootstrap returned HTTP 404 and did not establish a successful loader session. The CSV error page says verbatim: “서비스 제공 불가능”, “일시적 접근 불안정으로 인하여 서비스가 원활하지 않습니다.” These results prove unsuccessful anonymous access in this environment, not that KRX has no historical classifications or that authenticated access is impossible. No full-history acquisition plan was opened or collection expanded.

Artifact identity is the committed `data/kr-industry-membership-foundation-v1/krx-otp-probe/manifest.json` plus immutable `raw/<sha256>.bin` objects. The manifest contains every endpoint/method, exact parameters and form-body hash, request and response timestamp, selected response headers, HTTP status, raw length/hash, date context, failure/control semantics, parser encoding/schema, and error body verbatim. Rejected responses have no admitted data schema or classification rows. A shared body is stored once and referenced by every request that returned it.

| Raw artifact | SHA-256 |
|---|---|
| Exact OTP `LOGOUT` bytes | `377b375adcc04b5ba5998c978372401a4c6327ccc218e17e383f72861085cb95` |
| CSV negative-control HTTP 403 error HTML | `2c860edd6d3458284e3b7f2f727385462a5e2c59d3f32ec4244da90780c0dfa9` |
| Dataset-page bootstrap HTTP 200 | `26e3ce5e6516b6d5660133959ffa969622b8a27022a4e3c1b5d205c8156c5953` |
| Marketplace-loader bootstrap HTTP 404 | `484da3401691104462b3cfff75dbf2ec487e04dd3327593ce3a9e85a594f630d` |

The parser rejects HTTP errors, HTML/XML/JSON/login bodies, malformed or empty CSV, missing classification schema, conflicting dates and duplicate subjects. A valid CSV can only produce **review-required observations**, never automatic membership. Only security code/name, industry code/label, market and date values are projected; price/performance values are not examined. A missing industry is UNKNOWN. Request date context alone does not establish original release visibility, taxonomy version or an economic validity interval. Current-dated rows cannot fill an earlier request.

Offline reproduction: `python scripts/probe_krx_industry_otp.py --verify`; the overall foundation verifier also checks this evidence. Raw corruption, changed request parameters, altered substitutions or parser decisions fail verification. Failed KRX sources do not enter the membership proof pool. Actual historical KRX classification rows obtained: **0**. Existing admitted mapping remains empty; full signal and annual coverage remains **0%**, with all 120 securities/date retained and 73,200 research name-dates. Taxonomy and granularity remain null. Final decision remains **`DATA_FOUNDATION_INSUFFICIENT`**.

## Corrected adjacent-date metric semantics

`adjacentContinuityFraction` is renamed to **`adjacentClassificationAvailabilityFraction`**. Numerator: repeated universe-security pairs with a valid classification on both adjacent signal dates. Denominator: every security present in both adjacent universes, including UNKNOWN. An industry or taxonomy-version switch still counts as available on both dates. The original frozen key `minimumAdjacentNameDateContinuityFraction` remains byte-for-byte unchanged at 0.90 and is explicitly interpreted as this availability gate; no threshold is added or tuned.

Separate descriptive metrics use **only both-classified pairs** as their denominator: `adjacentIndustryStabilityFraction` is the share whose `(taxonomy_version, industry_id)` pair did not change; `observedAssignmentSwitchRate` is the share that changed. Their denominator is `bothClassifiedAdjacentNameDatePairs`, and both fractions are null when it is zero. Assignment changes are already listed in `observedAssignmentChanges`. These descriptive metrics have no readiness threshold. Availability stays 0% on the retained real evidence, while stability/switch rate are null, not a claim that assignments were stable. A synthetic switch test proves availability can be positive while stability is zero. Annual/signal coverage, universe and all numerical readiness gates are unchanged.

NO HISTORICAL INDUSTRY RETURN WAS COMPUTED

NO FACTOR OR ALPHA OUTCOME WAS INSPECTED

NO CURRENT INDUSTRY CLASSIFICATION WAS BACKFILLED INTO HISTORY

NO TAXONOMY OR GRANULARITY WAS CHOSEN FROM FUTURE RETURNS

NO SEALED PRIOR STUDY WAS RERUN
