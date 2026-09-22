# Four-factor PIT instrumentation proposal v1

> Proposal only. No historical ledger is rewritten, no production output
> changes in this PR. This describes a schema addition for FUTURE signal
> generation only, so a subsequent subfactor-level attribution audit
> becomes possible on the NEXT replay generation without repeating
> `four-factor-signal-attribution-audit-v1`'s finding that raw subfactor
> inputs were never stored.

## The gap this closes

`four-factor-signal-attribution-audit-v1` measured, by scanning the sealed
`replay-v16` signal record, that momentum's two raw inputs (`mom121`,
`mom6`), all four value inputs (`earningsYield`, `fwdEarningsYield`,
`bookYield`, `fcfYield`) and all five quality inputs (`roe`, `opMargin`,
`profitMargin`, `earningsGrowth`, `debtToEquity`) are computed internally
by `historical_replay.py` but never written to the persisted signal
record — only each sleeve's already-blended percentile survives. Only
Lowvol's single raw input (`vol252`) is stored, incidentally, via
`risk.vol252Pct`.

## Proposed schema addition

A new, OPTIONAL block on future signal records, alongside the existing
`factorPercentiles` and `features` blocks:

```json
"rawFactorInputs": {
  "mom121": <float | null>,
  "mom6": <float | null>,
  "earningsYield": <float | null>,
  "fwdEarningsYield": <float | null>,
  "bookYield": <float | null>,
  "fcfYield": <float | null>,
  "roe": <float | null>,
  "opMargin": <float | null>,
  "profitMargin": <float | null>,
  "earningsGrowth": <float | null>,
  "debtToEquity": <float | null>
}
```

Sourced from the same `raw_rows[ticker]` dict `historical_replay.py`
already assembles at
`pipeline/historical_replay.py:537-556` before calling
`longterm_mod.score_cross_section` — no new computation, only a new
persistence step for values that already exist in memory at signal-build
time.

## What this is NOT

- Not a rewrite of `historical-signals.jsonl`. Existing sealed shards are
  immutable and untouched.
- Not a `modelVersion`/`featureVersion`/`dataVersion` bump on its own —
  per the version-generation-policy invariants, adding an optional field
  that nothing downstream currently reads does not change scoring or
  acquisition shape. Should this proposal be implemented, the PR that
  does so states explicitly whether any generation version needs to move,
  per that policy's own disclosure requirement.
- Not required for `challenger-2-fundamental-acceleration-v1`: that study
  reads `FundamentalStore`'s own per-filing PIT history directly (already
  append-only and retained), not the signal ledger's blended percentiles,
  so it does not depend on this proposal at all.

## Why propose it anyway

Every subfactor-level question this repository has asked so far
(`lowvol-alpha-separation-v1`'s harness-fidelity gap,
`four-factor-signal-attribution-audit-v1`'s Q7–Q9 `PIT_NOT_AVAILABLE`
answers) has been blocked by the same fact: the signal ledger keeps the
blend, not the ingredients. Storing the ingredients going forward is cheap
(the values already exist in memory) and would let a FUTURE study answer
"do 12-1M and 6M momentum carry different information" or "how redundant
are the four value inputs" directly from the sealed ledger, rather than
`PIT_NOT_AVAILABLE`.

## Explicitly deferred

- Implementing the schema change in `historical_replay.py`.
- Deciding whether it warrants a `featureVersion` bump.
- Backfilling it onto any existing ledger generation (never done — this
  is forward-only instrumentation).

This PR proposes the schema only.
