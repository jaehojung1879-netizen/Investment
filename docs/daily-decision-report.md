# Read-only daily Portfolio D brief

Release integrity checks (2026-11-04 KST): a passive latest summary must match the decision-relevant fields of its
digest-valid FINAL receipt; a conflicting summary is UNKNOWN. A later in-week preview may display the verified final
decision still in force, while keeping observation freshness separate. A same-date preview is not upgraded to FINAL.
Paper NAV/ETF base dates must be valid final regional sessions no later than the report and stored status clocks;
unverifiable dates display UNKNOWN. No initial ledger means no observed return, not 0% performance.

Before any paper accounting, persisted shadow decisions now verify their stored digest, key, study identity and writer
timing independently. Moving an execution session without changing the decision digest is refused. Missing/inconsistent
stored fill costs are refused before further NAV writes. Existing bytes are not migrated or repaired automatically;
an incompatible legacy/dry-run book requires explicit review, never a reset or backfilled live track record.

This presentation path reads committed `signal-history` blobs. It reuses
`weekly_decision` policy constants/calendar/freshness and the registered paper
receipt validators. It never invokes selectors, fetchers, recorders, assessors,
outcome builders or deployment. No workflow or production importer calls it.

## Reproduce (the whole daily routine)

```sh
git fetch origin signal-history
SH=$(git rev-parse origin/signal-history)      # pin this full SHA; the report and the comparison cite it
```

The reader forbids lazy fetching (`GIT_NO_LAZY_FETCH=1`). A full clone needs nothing more. In a **partial clone**
(`git clone --filter=blob:none`) the blobs it reads must already exist locally, otherwise the render stops with
`LOCAL_GIT_SNAPSHOT_UNAVAILABLE: <commit>:<path>`. Materialise exactly the allowed paths first (a path absent from the commit is
recorded as `MISSING` by the report and never created):

```sh
python scripts/materialize_daily_report_sources.py "$SH"
```

Then render at an explicit timezone-aware report timestamp that is **not earlier than the source commit** (a snapshot committed
after its own reference time is refused):

```sh
python scripts/render_daily_decision_report.py \
  --source-ref "$SH" \
  --as-of 2026-11-02T15:30:00+09:00 \
  --output /tmp/investment-daily-20261102      # a new directory outside every Git repository
```

Two renders of the same source commit, report time and renderer commit give byte-identical `report.md` and `report.json`
(tested). The report embeds the renderer's own commit, so a hash printed here would go stale on every change; compare two
renders you made yourself, or read the hash the command prints.

The brief opens with one line, **오늘의 운영 판단**, taken from the same stored decision as the table further down:
per region "N종목 · ETF w%" or "UNKNOWN (reason)". It never names a stock. The session-freshness table below it can read
STALE (the observation session is older than the latest completed session) while that decision is still the one in force.

## One reading path

| Question | Where | Cadence |
|---|---|---|
| What do I hold today, is it fresh, what is verified, how is the paper path doing against the ETF? | **this brief** (`report.md`) | daily |
| What changed since the previous report? | `scripts/compare_daily_decision_reports.py` (below) | daily |
| Why: what do the historical research tracks show? | the four-track research report (*Reading the research results*) | when needed |

Three performance statements are always kept apart and never summed:

1. **Verified real-account performance**: none exists (no order, fill or account record). Printed as "없음", never as 0%.
2. **Prospective paper path** (`PROSPECTIVE_PAPER`, no orders): the stored status of `entry-state-shadow-ledger-v1`, shown as NAV and
   excess over the regional ETF **rebased to the session each path started**, with fill state and H126/H252 maturity. Missing or
   unreadable status is `UNKNOWN`; `PENDING_n_SESSIONS` means not yet matured, not a zero return.
3. **Historical exploratory backtests** (`HISTORICAL_DEVELOPMENT`): never in the brief; they live in the research report only.

"현재 운영 판단" shows a stock count and ETF weight only when the stored FINAL weekly decision is digest-valid, was made from fresh
inputs, is the decision for the **latest completed week-end session** of that region, and is internally consistent (status,
`stockCount`, `benchmarkWeightPct`, `holdings`, benchmark). A weekly decision stays in force until the next week-end session
completes, so Friday's decision still reads "current" the following Monday to Thursday while the session-freshness table calls its
observation date STALE; once a new week-end has completed with no new decision the row is `UNKNOWN`. A qualifying
`PASSIVE_NO_DEFENSIBLE_EDGE` reads "0개 · ETF 100%". A stock selection is **never displayed**: names and weights stay withheld
because no investment-admission registry exists, and every other state reads `UNKNOWN` with its reason code.

## Reading the research results

The four-track historical report (KR, US, Market C, Industry) is a separate read-only command added by the research-terminal change
(PR #299). Until that change is merged the command does not exist on `main`:

```sh
python scripts/render_four_track_report.py --as-of 2026-11-02T15:30:00+09:00 --output /tmp/investment-four-track-20261102
```

Its numbers are exploratory, outcome-exposed or blocked evidence and never feed the daily brief's decision, count or weights.

## Output files

`report.md` is the human brief; `report.json` contains exact source/code hashes,
missing paths, per-step statuses and stored assessment/outcome detail. Use the
same commit, timestamp and implementation to reproduce identical bytes. The
output must be a **new directory outside every Git repository/worktree**. No
original research source, ledger or registered specification is changed.

The report timestamp is a viewing reference, not a fabricated receipt clock.
The source commit must already exist by that reference. Source creation time,
fetch time (often UNKNOWN), observed session, source Git and current freshness
are separate fields. An old FRESH claim is recalculated at report time. A
regional index session does not certify a missing ETF quote.

Zero receipts require an empty validated ledger or an explicit matching-study
committed assessment/coverage zero; absence alone is UNKNOWN. Skipped recording
does not imply zero eligible names. Aggregate OK, a successful workflow, paper
PASS, internal weights and opportunity tiers never establish investment
admission. The renderer has no admission registry: certified candidate counts
remain UNKNOWN and it makes zero new nominations, retaining the existing
regional ETF default. The 0–5 operating policy is distinct from inactive D v2's
N=0…N>10 research objective. Persisted paper outcomes are displayed only after
receipt linkage and calendar maturity checks, with no return recalculation.

No native GitHub approval, model promotion, stock trade, paid source, historical
execution authorization or production allocation is produced by this command.


## What changed since the previous report? (read-only comparison)

Once two independent `report.json` outputs exist, compare them **without
fetching sources, recomputing returns or writing ledger entries**:

```sh
python scripts/compare_daily_decision_reports.py \
  --before /tmp/investment-daily-20261030/report.json \
  --after /tmp/investment-daily-20261031/report.json
```

The command prints JSON listing changes in regional observed/final sessions,
freshness, policy status, paper receipt counts (including `null`/UNKNOWN vs
actual zero), latest recording attempts, stored matured outcome counts and
source-path read/missing totals. It requires later report time and locally
declared source commit timestamps not after the report. The input reports
are **not independently source-re-attested by this diff**, and a changed
reported count is *not* a verified new signal, alpha, approval or recommendation.
The comparator never generates a new trade or investment nomination.
