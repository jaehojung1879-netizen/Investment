# Run #44: the audit crashed, and the workflow reported someone else's failure

Run #44 was the first live execution of replay-v10 (`docs/replay-v10-actions-repair.md`).
It went red with:

> the portfolio audit blocked the report … check `contractValidation.failures`
> in `ledger/historical-portfolio-validation.json`

That message was wrong. The audit never produced a report to block.

## What actually happened

`replay-v10` added a static `benchmark/source` input component that pins one
vendor lineage per generation. Its rows are `{region, ticker, source, symbol,
policy}` — no `date`, no `Close`.

`InputStore.load(valuation_only=True)`, which only `scripts/audit_portfolio.py`
calls, projects every component whose name starts with `price/` or `benchmark/`
down to `(date, ticker, Close)` so the audit does not inflate the whole
multi-GB snapshot. `unpack` was taught to exclude `benchmark/source` from that
prefix test when the component was added; `load` was not. So the audit died
with `KeyError: 'date'` on its own generation's lineage rows.

The step is `continue-on-error: true`, and the crash landed before
`output.write_text(...)`, so:

* `ledger/historical-portfolio-validation.json` stayed at the **replay-v9**
  report written by run #42, while `ledger/historical-diagnostics.json` was
  replaced with replay-v10's;
* both were pushed to `signal-history` in commit `c931224`, leaving the two
  files describing different generations;
* the final step, which could only see `outcome == 'failure'`, quoted the
  stale v9 report's `continuous_nav_has_unknown_intervals` as run #44's reason.

The timing corroborates it: the audit step took 43 s in run #44 against 10 m 04 s
in run #42, and neither `historical/replay-v10/reports/` nor the
`historical/replay-v9/portfolio-validation.json` archive — both written before
the contract is evaluated — exists on `signal-history`.

## Fixes in this change

1. `pipeline/replay_inputs.py` gets one `is_price_panel()` predicate, used by
   both `load` and `unpack`, so the two cannot drift apart again.
2. `scripts/audit_portfolio.py` separates the two failures by exit code:
   `1 = BLOCKED` (a completed audit whose contract failed — its report is this
   run's verdict) and `2 = INCOMPLETE` (the audit never finished — the report on
   disk belongs to an earlier run).
3. `.github/workflows/replay.yml` records that exit code and branches on it, and
   prints which generation the report on disk actually belongs to.

Neither the replay inputs nor the gates change, so `REPLAY_VERSION` and
`DATA_VERSION` are untouched and replay-v10's sealed snapshot stays valid. The
fix can be verified by re-running the workflow with `frozen_inputs=true`, which
reads the committed snapshot and fetches no vendor data.

## What this does NOT fix

The v10 report that run now produces is still expected to be **BLOCKED**, for a
real reason: the 2025-09-19 KRX session is absent from the Yahoo panel for 42 of
68 active Korean names, and the continuous-NAV contract requires 100 % of
matured blocks. Four blocks hold one of those names
(`004020 010130 012330 015760 017670 024110 028260 271560`), so both selectors
report `continuous_nav_has_unknown_intervals`.

Two findings from run #44's own telemetry bear on the eventual repair, and
neither is addressed here because both change acquired inputs and therefore
require a new generation:

* **The v10 hypothesis about that gap is not supported by v10's own data.**
  `docs/replay-v10-actions-repair.md` attributed the rejections to comparing
  Yahoo's auto-adjusted close against FDR's raw close. But every rejected row in
  `inputRecovery.krPriceRows` now reports `adjustedBridgeDifferenceBps` and
  `rawBridgeDifferenceBps` agreeing to four decimal places (e.g. `012330.KS`
  176.5655 vs 176.5650; `271560.KS` 120.0369 vs 120.0369). The adjustment basis
  is identical over the bridge, so the disagreement is a genuine vendor
  disagreement on the 09-18 → 09-22 price ratio, not a dividend artifact. The
  same 42 names are rejected as under v9, now under `RAW_RETURN_BRIDGE_MISMATCH`.
* **The "small-window retry" is not small.** `recover_systemic_kr_gaps` computes
  one window from `min(systemic) - 14d` to `max(systemic) + 14d`. Run #44 found
  five systemic dates — 2017-09-22, 2017-12-20, 2022-01-03, 2022-05-09,
  2025-09-19 — so the targeted retry that is meant to be a focused re-request
  became an eight-year bulk download of ~68 tickers, twice (adjusted and raw):
  the same shape of request that dropped the rows in the first place.
  `krPriceSummary.targetedYahooRetries` is `0` and
  `basisBoundReconstructions` is `0`, so the designed first-choice recovery
  never once succeeded. Scoping the window per contiguous gap group would let it
  run as intended.

Underneath both is a structural point worth deciding on separately: Yahoo is the
primary price vendor for Korean equities and its KRX history is incomplete. Run
#44's own benchmark resolution measured `fdr:KS200` at 100 % known-calendar
coverage against `yahoo:^KS200` at 98.08 %, and the KR benchmark preflight at
98.06 % against 100 % for the US. The recovery layer is compensating for a
vendor choice, and it will keep having to.
