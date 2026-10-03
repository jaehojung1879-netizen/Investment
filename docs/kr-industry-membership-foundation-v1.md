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
| Adjacent repeated-name classification continuity | >=90% | 0% |
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
