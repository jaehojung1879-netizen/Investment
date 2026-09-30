# Prospective validation foundation

The first eligible KR trading session **strictly after the date of the final v1 specification merge to main** is the earliest possible prospective start. Same-merge-date observations are conservatively excluded even if merge preceded market close. A previously unobserved 2026-09-15 label does not qualify: this system was not frozen then. No date is hardcoded as a future merge date. Only actual merge evidence may populate it.

Historical development artifacts and prospective receipt/outcome artifacts use separate namespaces and explicit scientific-status fields. Development ends2026-09-14; prospective prediction receipts begin only after actual final merge. There is no interpolation of the gap or pooling into a confirmation headline.

`prediction_receipt` implements immutable prediction-only first-write receipts with:

* signal date; exact spec SHA; exact raw snapshot SHA; exact trained-model snapshot SHA;
* per-stock H126 and H252 predictions/rank, Value/Quality/Catalyst/Risk scores, contributions where linear, missing/source/investability flags;
* selected zero-to-five securities, baseline and final weights/cash; benchmark-state inputs/multiplier;
* explicit PROSPECTIVE_PREDICTION_ONLY status.

The caller must supply predictions from the approved annual training cutoff using only matured training records, export/check the fitted model/transform snapshot before predicting, pin a fresh immutable raw-input snapshot, and atomically write the receipt at signal time before the next-session execution. The receipt rejects outcome/label/forward/realized/performance keys recursively and refuses a second write. This PR implements the storage boundary and provides the architecture; it does not activate a scheduled prediction job or manufacture prospective observations. Persist each receipt and sidecar in a dedicated append-only signal-history namespace or immutable Actions artifact immediately, then commit it; a local scratch write alone is not prospective evidence.

Later outcome joining must verify the receipt preexisted its H126/H252 endpoints, its original immutable hashes and public timestamp, and the same target/next-session semantics. Store joins separately; never rewrite the receipt with outcomes. Freeze a separate prospective evaluation plan/authorization before opening those outcomes, including required evidence length, model-change handling and inference. DEVELOPMENT_CANDIDATE is only permission to consider that plan, never confirmation or production promotion.
