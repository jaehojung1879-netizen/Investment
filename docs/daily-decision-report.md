# Read-only daily Portfolio D brief

This presentation path reads committed `signal-history` blobs. It reuses
`weekly_decision` policy constants/calendar/freshness and the registered paper
receipt validators. It never invokes selectors, fetchers, recorders, assessors,
outcome builders or deployment. No workflow or production importer calls it.

After checking out the implementation PR, fetch the existing branch, pin its
full SHA, and render at an explicit timezone-aware report timestamp:

```sh
git fetch origin signal-history
git rev-parse origin/signal-history
python scripts/render_daily_decision_report.py \
  --source-ref FULL_40_CHARACTER_SHA \
  --as-of 2026-10-30T09:00:00+09:00 \
  --output /tmp/investment-daily-20261030
```

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
