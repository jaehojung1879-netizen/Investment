# Management guidance source pilot — 2026-11-25

Status: SOURCE_ONLY / exploratory manually selected examples; not a preregistration or an alpha test. Independent of #371 (ownership intent, semiconductor physical data, insider clusters). #354 studied realized earnings surprises, not revisions to an identical future target. #355 did not test conditional reassessment after announcement. No historical prices, returns or labels were read.

## Actual source evidence

Five dated SEC 8-K Exhibit 99.1 documents and filing indexes were inspected through public sources. The nine rows in observations.csv are manual numeric/state transcriptions, not a complete universe, automated parser, or contemporaneously acquired receipt. The SEC acceptance time is a conservative filing-time reference, not proof of first public release or executable price; the original HTML bytes and hash have not been retained here. No claims about coverage, independent sample size beyond this pilot, or PIT admission.

- Cisco FY2025: February 12 -> May 14 revenue range 56.0–56.5 -> 56.5–56.7 USD billion; GAAP EPS 2.40–2.52 -> 2.53–2.58; adjusted EPS 3.68–3.74 -> 3.77–3.79. Midpoint changes +0.35 billion, +0.095, +0.07. Three metrics are ONE issuer-disclosure comparison, not three independent events.
- UPS FY2025: January 30 approximately 89 billion revenue; April 29 no update to previous annual outlook; July 29 no revenue or operating profit guidance provided. Neither state is a numeric zero revision, a confirmed reaffirmation, nor an inferred numeric cut. The initial approximate point is encoded as equal bounds, not a precision claim.

Changing next-quarter targets must not be paired as revisions. Same fiscal period, currency/unit, issuer CIK, metric and accounting basis are required, and ambiguous gaps cannot be bridged. Even same-year guidance updates can mechanically reflect newly realized earnings or acquisitions, tax, FX, and remaining fiscal time. They are not analyst-consensus surprises. For a future research panel, record realized YTD results known at the filing, remaining-period guidance and scope/currency changes separately; test incremental information over realized earnings surprise and already-known price/industry information only under a new approved protocol.

## Next material gate (not implemented)

Acquire original 8-K exhibits and index/submission timestamps across an outcome-blind predetermined issuer cohort using the existing #354 Item 2.02 accession catalog where accessible. Retain immutable hashes and independently double-label ranges, omissions, withdrawals, scope changes, restatements and same-target continuity. Quantify issuer/sector/year coverage, document retrieval failures, labeling agreement and independent issuer-time clusters. Audit source access via existing GitHub Actions before declaring a network blocker; no new workflow or credential exposure. If usable coverage is insufficient, stop at SOURCE_ONLY. No outcome execution, new paid data or live record activation.

Reproduce the manually transcribed comparison:
`python research/guidance_source_pilot_v1/inspect_guidance.py`
`pytest -q tests/test_guidance_source_pilot_v1.py`
