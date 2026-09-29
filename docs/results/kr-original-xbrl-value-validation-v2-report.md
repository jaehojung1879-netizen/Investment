# Original XBRL source-value audit v2 — BLOCKED

Follow-up to the closed [v1 result](kr-original-xbrl-value-validation-v1-report.md)
(BLOCKED, 60 AMBIGUOUS_SOURCE_FACT; untouched). Protocol frozen at
`14f42050fd15487f5c87717d61615e1b08701e7e`, SHA-256
`a0251b2459de1ed820c7306c822e29429d92b18b72e2063d044e34ba8db3871d`. Same 60 items,
sample SHA-256 `590513ede1c8bd06d701f22f4b1aa01bcf8b004aa30b9410540865696e863e70`,
candidate SHA-256 `af642e7e79e9ba59ac6ee14faf033f4d63887188bab6506845c082e21dc3d1cc`.

## Result

**Overall verdict: BLOCKED.** One formal live run (Actions run `36557135754`,
head `bf07e16a`, artifact `11029185628`, zip SHA-256
`48b30e3692808a9537e5616c07c06679fafd8fb1a23cf484e0458021bb7b4ce9`, report SHA-256
`b119f483033413e9710c773681caf4f7b530c1be510a6d72cf141c141709fef9`). No retry.
All 57 receipts were served. Per-item fields in the JSON are reproduced from the
job log; the artifact zip could not be downloaded from the authoring environment.

| Classification | Count |
|---|---:|
| MATCH | 0 |
| VALUE_MISMATCH | 0 |
| SEMANTIC_MISMATCH | 0 |
| METADATA_MISMATCH | 0 |
| AMBIGUOUS_SOURCE_FACT | 60 |
| SOURCE_UNAVAILABLE | 0 |
| INFRASTRUCTURE_ERROR | 0 |

## What v2 resolved

The v1 blocker is gone: for all 60 items the exact scheme
`http://dart.fss.or.kr/ifrs/CIK` was accepted and its identifier equalled the
frozen `corpCode`. Because MISMATCH outcomes return before the later checks, all
60 also passed the period, basis, unit/currency (KRW) and unitRef/decimals
provenance checks.

## Newly exposed systematic blocker

All 60 now stop, with one reason, at the next check:
`source presentation does not prove required financial statement`. The
presentation evidence found for the element is empty for 60 of 60, so the reader
could not connect the concept to the required statement through a presentation
role it recognises. The steps after it (nil/transform attributes, duplicate-fact
consistency, exact Decimal comparison) were not reached, so no value was
compared. Descriptively, the raw source text equals the stored candidate amount
in all 60, but that is not a MATCH and is not treated as one.

Per the protocol, no other rule was widened inside v2 and nothing was repaired.
The cause is not diagnosed: raw ZIPs are not retained here, so it is unknown
whether these 2015 packages lack a recognisable presentation linkbase, use role
or href conventions the frozen reader does not recognise, or something else.
Resolving it needs a new, separately justified version (v3) with its own
independent evidence and pre-registration, on the same fixed sample.

## Confidence

`CANDIDATE_UNCONFIRMED` **cannot be promoted**: no item is MATCH. No candidate
repair, v5 seal or Alpha execution occurred; no historical outcome data was read.
