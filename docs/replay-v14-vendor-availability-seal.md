# The seal and the vendor that will not repeat itself

replay-v14 run #55 — the third of the three operator runs, `frozen_inputs=false`
— died on:

```
ERROR: corporate-events/2015-03: published input prefix changed/recovered;
       new DATA_VERSION/REPLAY_VERSION required
```

Nothing had changed in the code since run #53 sealed that generation. Run #54
(`frozen_inputs=true`) had just reproduced the same snapshot exactly:
`SCHEDULE_STABLE`, `reproducible: true`.

## What actually moved

Yahoo answers differently on different days for the same delisted ticker:

```
10 Failed downloads:
['SIVB','RE','SEE','SAI','RHT','RRD','SATS','RTN','RVTY']:
    YFTzMissingError('possibly delisted; no timezone found')
['SIAL']: YFPricesMissingError('possibly delisted; no price data found')
```

Measured across two production acquisitions of the SAME code an hour apart:

| run | `constituentsWithoutPriceHistoryCount` |
|---|---|
| #52 | 286 |
| #53 | 282 |

Four of the 326 former index members flipped, with no code change between the
runs. A ticker that vanishes takes its **whole decade** of rows out of every
monthly shard it appeared in, so one flip on a name that paid a dividend in
March 2015 rewrites `corporate-events/2015-03`.

The byte-exact check was right that the bytes moved and wrong about what it
meant. **No published number changed.** A vendor declined to repeat itself.

## Why this had to be fixed rather than documented

Acquisition is the only way new replay dates enter a generation: scheduled runs
are frozen by design and reproduce the sealed cutoff, they cannot extend it. So
a generation that can never be re-acquired is **frozen in time at its first
cutoff**, and every further date needs a fresh, incomparable generation.

That is precisely the disease that killed replay v7, v8, v9 and v10 — each
lasted one or two runs before the ledger had to start over — in a new form.
v11 cured the *adjustment basis* cause. This is the *vendor availability* cause,
and it was still live.

## What changed

Within a generation the **sealed rows are the authority**. `InputStore.commit`
now reconciles the prefix per name instead of comparing it wholesale:

* a sealed ticker the vendor did not serve this run is **restored from the
  store** — the rows are immutable, re-downloading them could only reproduce
  them;
* a ticker that was **never sealed** contributes nothing before the cutoff, so
  it cannot write history it was absent from (it may still join at the
  frontier, which is how a genuine new index member arrives);
* a sealed ticker whose values come back **different — a changed close, an
  extra session, a new dividend — is still a conflict and still stops the run.**

Reconciliation applies only to components whose rows carry both a date and a
ticker (`price/`, `benchmark/`, `corporate-events/`). Everything else — macro,
FX, the calendar, the static lineages, the universe definition — stays frozen
whole, because a change there is policy drift, not a vendor's mood.

The repair is never silent: `diagnostics.inputSnapshot.prefixReconciliation`
publishes `restoredTickers`, `ignoredTickers` and the component count on every
run.

### Why the splice is safe

The restored prefix is joined to a freshly fetched suffix, and that is only
sound because of replay-v11: on the as-traded forward total-return basis a
published value never moves, so both vintages are on one basis. On Yahoo's
back-anchored adjusted close — where every ex-dividend rescales the whole
history — splicing two vintages would have been exactly the error the module
warns about.

One mechanical detail carries real weight: `pack` emits each month ticker-major
and date-ascending, and the cutoff falls mid-month, so a spliced shard holds
sealed and fresh rows together. Returned prefix-block-then-suffix-block, the
*next* run's byte-exact check would fail on ordering alone and the seal would be
straight back where it started. The splice re-sorts, and a test pins that
ordering against `pack` itself rather than against the splice's own assumption.

## Tests

`pytest tests/` — **854 passed** (`test_pack_roundtrip_preserves_inputs_and_bounds_asof`
fails in this sandbox on a pandas `datetime64[us]`/`[ns]` index dtype; identical
on `main`, green on CI for #90–#97).

`tests/test_input_prefix_reconciliation.py` is new: 20 cases, of which the four
end-to-end ones through `InputStore.commit` all fail if the reconciliation is
reverted — a missing name extends instead of refusing, the spliced month keeps
pack's order, a name returning with different numbers still stops the run, and a
never-sealed name cannot write a published month.

`test_snapshot_reuses_objects_and_refuses_revision_recovery_and_removal` pinned
the old wholesale rule, including the "vendor served nothing" case that run #55
proved wrong. It is now
`test_snapshot_reuses_objects_and_refuses_a_revised_value` and keeps the teeth:
a revised close, an extra session on a sealed name, and a changed undated input
all still raise.

`test_yahoos_adjusted_close_would_have_been_refused_by_the_same_store` — the v11
control — still refuses, now naming the contradicted ticker.

## No new generation

**No `REPLAY_VERSION` or `DATA_VERSION` bump.** No sealed value changes: v14's
snapshot stays byte-identical and its evidence stands. What changes is how a
*later* re-acquisition reconciles with it, and the immutability guarantee is
strictly stronger afterwards — the published prefix can no longer drift with a
vendor's availability, only be contradicted, which still stops the run.

(A `DATA_VERSION` bump would in any case be self-defeating here: `manifest()`
raises `DATA_VERSION changed inside an existing replay generation` and would
force the very re-acquisition this removes the need for.)

## Operator sequence

Nothing to re-acquire. Re-run the third operator step on the existing v14 seal:

1. `full=false`, `frozen_inputs=false`, `retrain=false`. It must extend the
   generation rather than raise `INPUT_VERSION_CONFLICT`. Check
   `inputSnapshot.prefixReconciliation`: `restoredTickers` names whatever Yahoo
   declined to serve this run, `ignoredTickers` whatever was never sealed. A
   long `restoredTickers` list is the fix working, not a warning.
2. Only if that passes and `contractValidation` is eligible, run **Build insight
   data and deploy Pages**.

---

# Run #57: the availability cases cleared, and a different one surfaced

The fix worked on what it was built for. Run #57 no longer mentions
`corporate-events/2015-03`, and the nightly cron (#56, frozen) went green on the
sealed v14 generation. What stopped #57 was the reconciliation's teeth:

```
ERROR: price/2026-09: HUBB contradicts the sealed prefix;
       new DATA_VERSION/REPLAY_VERSION required
```

`price/2026-09` is the month that straddles the cutoff (`through: 2026-09-10`),
so those are the NEWEST sealed rows — the ones a vendor is most likely to revise.
HUBB has no sealed corporate event in that month (checked: 90 events in
`corporate-events/2026-09`, none for HUBB), and its seven sealed sessions are
2026-09-01 through 09-10 with 09-07 correctly absent for Labor Day.

## Why that message could not be acted on

It names one ticker and stops, and the scope is the whole diagnosis:

* **one** contradicting ticker is a corporate action to look up;
* **hundreds** is the vendor revising recent bars, which needs the opposite
  response.

`reconcile_prefix` raised on the alphabetically first offender, so "HUBB" could
have meant either. It now collects every contradicting name and reports the
count, the first five with the exact session and field that moved, and a
`(+N more)` tail:

```
price/2026-09: 37 of 503 sealed tickers contradict the sealed prefix:
  HUBB 2026-09-08 Close 643.55 -> 644.01; ...(+32 more);
  new DATA_VERSION/REPLAY_VERSION required
```

`first_difference` distinguishes a gained session, a lost session, and a changed
field, so the record says what kind of disagreement it is, not merely that there
was one. The conflict record under `ledger/replay-input-conflicts/` carries the
message verbatim (`reason: str(exc)`), so the evidence survives the run.

This is a diagnostic change only — the same runs conflict, and the same runs
pass. It is what the next run needs in order to be decidable.

## Tests

`pytest tests/` — **859 passed** (same known sandbox-only pandas dtype failure).

Five added or tightened: every contradicting ticker and the scope are named; the
list summarises rather than printing hundreds; and `first_difference` is
parametrised over gained, lost and changed.
