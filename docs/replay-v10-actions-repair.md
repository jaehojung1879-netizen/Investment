# Replay v10: production Actions repair after v9

Replay v10 is a new experiment generation. It does not change production
scoring. It repairs two input-acquisition defects observed only after replay v9
was merged and executed against the live vendor routes.

## What failed in the live runs

Run #42 completed the v9 acquisition and replay, then correctly failed the
continuous-headline contract. The 2025-09-19 KRX session was absent for all 68
active Korean names in the Yahoo batch while the benchmark traded. The v9 FDR
recovery accepted 26 names and rejected 42. Two rejected names, `024110.KS` and
`271560.KS`, were held in the 2025-08-21..2025-09-22 block, so both selectors
reported `continuous_nav_has_unknown_intervals`.

The rejection rule was wrong for this use. It compared Yahoo's auto-adjusted
total-return close directly with FDR's raw close return. The observed bridge
differences for the 68 names ranged from 0 to 227.11 bps (median 34.31 bps);
`024110.KS` was 50.38 bps and `271560.KS` was 120.04 bps. A dividend adjustment
can therefore look like vendor disagreement even when the two raw price returns
agree.

Run #43 failed earlier with
`benchmark/2011-01: published input prefix changed/recovered`. Run #42 had
selected FDR for KOSPI 200 (3,855 sessions through 2026-09-07). The resolver then
selected Yahoo on #43 (3,782 sessions through 2026-09-09) solely because Yahoo
was one session fresher. The two complete histories are different vendor
lineages, so the immutable-prefix guard correctly rejected the switch. However,
the resolver had already overwritten the shared benchmark snapshot/index before
the input commit failed, and the failure-preservation step committed that
unaccepted cache state. Detection worked; source selection and transaction
ordering did not.

## v10 fixes

Benchmark source selection now follows configuration order on generation
bootstrap and stores the selected `(vendor, symbol)` as a static,
content-addressed `benchmark/source` input component. Every later acquisition in
that generation may use only the pinned source. Another accepted source remains
diagnostic redundancy; being one day fresher cannot replace the lineage. If the
pinned source is unavailable, only a snapshot whose index matches that lineage
may be used.

Benchmark cache writes are transactional with the immutable input store.
Resolution is side-effect free in `run_replay`; the snapshot and index are
persisted only after the generation input commit succeeds. An
`INPUT_VERSION_CONFLICT` therefore cannot alter the cache inherited by the next
run.

Systemic Korean price recovery now uses this order:

1. retry the proven market-wide hole in small Yahoo batches and accept an exact
   adjusted-price bridge when available;
2. otherwise compare FDR raw returns with a narrow Yahoo **raw-close** bridge,
   retaining the original 25 bps independent-vendor tolerance;
3. map the FDR observation back to the Yahoo adjusted basis using the adjustment
   factors observed at both anchors;
4. where the unavailable session lies inside an adjustment-factor transition,
   store both-source uncertainty and use the lower of the two observable bounds
   for the long-only daily NAV. This cannot improve the missing day's NAV. An
   unexplained adjustment over 500 bps remains rejected as a corporate-action
   case requiring reviewed evidence.

Accepted/rejected rows now record the adjusted bridge, raw bridge, adjustment
basis shift, reconstruction method and `pathUncertaintyBps`. The report also
publishes counts and the maximum uncertainty. The integrity and continuous-NAV
gates are unchanged.

Scheduled runs now use the committed frozen snapshot. A cron job is allowed to
verify replay determinism; it is not allowed to decide that a changed historical
vendor prefix constitutes a new experiment. Non-frozen acquisition is therefore
manual and versioned.

## Version and metric comparison

`REPLAY_VERSION` is `replay-v10` and `DATA_VERSION` adds pinned benchmark lineage
and basis-aware systemic-gap recovery. Reusing v9 would silently reinterpret its
historical valuation inputs, so it is forbidden.

| Generation/run | Result | Headline comparison |
|---|---|---|
| v8 observed | blocked; unknown input intervals | unavailable |
| v9 run #42 | blocked; two held KR prices missing | no publishable headline |
| v9 run #43 | stopped by immutable-prefix conflict | no metrics produced |
| v10 PR fixture | source and calendar invariants pass | not comparable to v8/v9; live full replay not run in PR |

No v10 live headline is claimed before the post-merge full workflow. Even after
that run, v10 is not directly comparable with legacy generations because FX,
corporate-action, daily-path and recovered-price definitions differ.

## Remaining limits and exact operator sequence

The lower-bound reconstruction is source-backed but is still not an executable
intraday price. Its maximum bps uncertainty must be read with MDD, Sharpe and
Sortino. H.10 remains a reference FX fixing, the BOK policy rate remains a cash
proxy, early historical-universe coverage is incomplete, and macro history is
not fully vintaged. Passing v10 does not confer `liveValidated` status.

After merge, run the workflows in this order:

1. **Historical point-in-time replay** with `full=true`,
   `frozen_inputs=false`, `retrain=false`. This creates the new v10 inputs and
   full replay.
2. **Historical point-in-time replay** with `full=true`,
   `frozen_inputs=true`, `retrain=false`. This must reproduce the same input
   hash, schedule and sealed cross-sections.
3. Only if both replay runs and `contractValidation` pass, run
   **Build insight data and deploy Pages**.

The next full replay requires the new `DATA_VERSION` and `REPLAY_VERSION`
introduced here. A later correction inside the sealed v10 prefix requires
another explicitly named experiment; it must not be accepted by weakening the
guard or by rerunning the same generation non-frozen.
