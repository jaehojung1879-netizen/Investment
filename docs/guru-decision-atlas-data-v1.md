# Guru Decision Atlas — 13F data foundation v1

> **Data foundation only, for a future, entirely separate research line.**
> Guru holdings are not a strategy. No future return, no manager ranking,
> no "Guru vs. our model" comparison is computed here. Nothing in this
> track is imported by any Main Alpha module —
> `tests/test_guru_alpha_separation.py` checks this mechanically, by
> grepping/importing across `pipeline/`, not by convention alone.

## Why this exists, and why it is not built into Main Alpha

The eventual purpose of this track (not attempted in this PR) is to compare,
on a name that clears our own screen, whether a tracked manager was also
accumulating it, was doing the opposite, or was silent — and specifically to
notice when THIS project found something a tracked manager evidently did
not. Guru holdings being correlated with a name is never treated as a reason
to hold it, and Guru's absence from a name is never treated as a reason to
avoid it. None of that comparison exists yet; this PR only builds the
historical record it would need.

## What SEC actually provides (researched; live-verification blocked from
this sandbox, see Access status below)

- **SEC's own structured Form 13F Data Sets**
  (`sec.gov/data-research/sec-markets-data/form-13f-data-sets`, backed by
  the DERA Data Library) ship as TSVs inside a per-window ZIP:
  `SUBMISSION.tsv` (accession number, CIK, filing date, period of report),
  `COVERPAGE.tsv`, `OTHERMANAGER.tsv`, `SIGNATURE.tsv`, `SUMMARYPAGE.tsv`,
  and `INFOTABLE.tsv` (issuer, title of class, CUSIP, value, shares,
  put/call, voting authority). Structured XML-based data begins ~2013Q2;
  earlier filings exist but are heterogeneous text/HTML, fetchable
  per-filing rather than from the bulk TSVs.
- **The URL scheme changed in March 2024**: the old
  `sec.gov/files/dera/data/form-13f/<quarter>.zip` pattern now largely
  404s; the current scheme is a rolling 3-month window
  (`sec.gov/files/structureddata/data/form-13f-data-sets/<window>_form13f.zip`).
  All of this is on `www.sec.gov` — the domain `AGENTS.md`'s Vendor refusal
  invariants (v2.9) already measured as refusing this repository's GitHub
  Actions IP pool site-wide.
- **Per-filer submissions API**: `data.sec.gov/submissions/CIK{10-digit}.json`,
  no auth, returns recent filings plus pointers to older shard JSON for full
  history — this is the fallback route `scripts/backfill_guru_13f.py` uses
  for the 7 already-known manager CIKs when the bulk route is unavailable.
- **No free CUSIP↔ticker crosswalk exists.** `company_tickers.json` maps
  CIK↔ticker only; CUSIP is a proprietary CGS identifier with no free
  official mapping. This is a structural gap `pipeline/security_identity.py`
  documents rather than works around with a guess.

## Evidence that SEC access is likely blocked here too, not assumed

`pipeline/institutional_13f.py` (the existing, unrelated production 13F
dashboard reader) already has a live-fetch-failure fallback in its own
code — read directly, not inferred:

```python
except Exception as exc:
    cached = cached_managers.get(manager.get("id")) if use_cache else None
    if cached and cached.get("reportDate") and cached.get("filingUrl"):
        output.append({
            **cached, ...,
            "status": "CACHED_OFFICIAL", "sourceMode": "CACHED_SEC",
            ...
        })
```

and `data/institutional_13f_cache.json` records `sourceMode: LIVE_SEC`,
`fetchedAt: 2026-08-15` — the exact date `AGENTS.md` already names as when
SEC last served this repository live, before refusing it site-wide. Since
the Form 13F bulk dataset and the per-manager submissions API sit on the
same two hosts (`www.sec.gov`, `data.sec.gov`) already measured blocked for
Form 4, 8-K, and the bulk financial-statement dataset, the honest read is:
**very likely blocked today, on both 13F routes, but this is inference from
adjacent measurements, not a fresh direct probe result.**
`scripts/probe_guru_13f_access.py` is what would actually answer this, and
it has not been run in an environment with real network access.

## Schema (`pipeline/guru_13f_store.py`, one row per manager × accession × CUSIP/class/putCall)

`managerId, managerName, managerCIK, reportDate, filingDate,
accessionNumber, filingForm, amendmentFlag, originalOrAmended, issuer,
titleClass, CUSIP, putCall, shares, reportedValue, portfolioWeight,
previousShares, changeShares, changePct, action, acquisitionWindowStart,
acquisitionWindowEnd, id`

- **`action` ∈ {NEW, ADD, HOLD, REDUCE, EXIT}`.** A move is `HOLD` unless it
  clears BOTH a relative bar (≥0.5% change, matching the same 0.5% band
  `institutional_13f._changes` already uses, so this repository's two 13F
  readers do not define "noise" two different ways) AND an absolute bar
  (≥100 shares) — either bar alone lets through a false positive the other
  is there to catch (a 1-share move on a 3-share base reads as 33%; a 0.4%
  move on 10M shares is still 40,000 real shares). A position dropped
  entirely between two filings becomes a synthetic `EXIT` row (shares=0),
  never a silent omission.
- **No exact trade date or price is ever stored.** A `NEW`/`ADD` position
  carries `acquisitionWindowStart`/`acquisitionWindowEnd` — the previous
  report date + 1 day (or the manager's first-ever FILING date, not report
  date, when there is no prior quarter) through the current report date —
  bracketing when the public could first have known, never inventing a
  precise moment 13F itself does not disclose.
- **Amendments are preserved, never overwritten.** Stored under their own
  `accessionNumber`; the "previous" baseline for change calculations is
  anchored on the original 13F-HR (or the earliest 13F-HR/A if no original
  exists), never silently replaced by a later amendment the way the
  existing dashboard reader's simpler "latest wins" logic does.
- **`reportDate` and `filingDate` are kept distinct** throughout the schema
  — a tradable signal built on this data later could only use `filingDate`
  forward, and the schema enforces that distinction from the start rather
  than retrofitting it.
- Storage reuses `pipeline/historical_store.py`'s deterministic-gzip,
  quarter-sharded, checksummed pattern directly rather than inventing a
  second one.

## Identity resolution (`pipeline/security_identity.py`)

Two tiers, both explicit about their own confidence, plus an unresolved
queue rather than a silent drop:

- `EXACT_CUSIP_MATCH` — only when a caller supplies a CUSIP→ticker map; no
  such map is freely available from SEC in bulk, so this tier is expected to
  be sparse without a licensed or curated map.
- `NAME_FUZZY_MATCH` — normalized-name lookup against `company_tickers.json`'s
  CURRENT names, always flagged with a `pointInTimeRisk` note, since a
  decade-old 13F issuer name may not match anything current (mergers,
  renames, delistings).
- Everything else is `UNRESOLVED`, listed in its own queue. The
  unresolved rate was not measured (no real 13F data was fetched in this
  PR) but is expected to be non-trivial for older filings and any
  acquired/renamed/delisted issuer — an accepted, documented small-unresolved-set
  outcome, not a defect to fix by loosening the matcher.

## Physical separation from Main Alpha

Everything lives under `data/research/guru-decision-atlas/` (quarter-sharded,
gzip, deterministic — never a raw SEC ZIP committed to git).
`tests/test_guru_alpha_separation.py` mechanically asserts that
`pipeline/longterm.py`, `pipeline/opportunity.py`,
`pipeline/kelly_portfolio.py`, and `pipeline/build.py` import neither
`guru_13f_store` nor `security_identity` — a guardrail, not a promise in a
docstring.

## Workflow

**As of `workflow-hygiene-live-data-fixes-v1` (2026-09-24), there is no
dedicated backfill workflow in Active Actions.** A real probe run (Actions
run 35964478931) measured `verdict: BLOCKED, route: NONE` — the SEC bulk
13F dataset and both per-manager-submissions routes are refused from this
repository's GitHub Actions runners, the same domain-wide block already
measured for Form 4, 8-K and the bulk financial-statement dataset. Running
the same probe again from the same network answers the same way, so the
dedicated `guru-13f-backfill.yml` workflow (still in git history) was
retired from the Actions menu; re-running it would just spend CI minutes
confirming a fact already measured.

`scripts/probe_guru_13f_access.py` — the exact script that workflow ran —
is now one option in `.github/workflows/probes.yml`'s dropdown
(`guru-13f-access`), so access can be re-checked with the same one click
any other source probe uses, without a bespoke workflow file. If a future
probe run reports `SERVED`, a backfill workflow can be restored from git
history (or rebuilt against `scripts/backfill_guru_13f.py`, which is
unchanged and still committing nothing automatically — its output is a
report artifact, not a git commit, exactly as designed here) — see
`docs/workflow-inventory.md` for the current Actions inventory.

## Grade

**Guru 13F historical backfill, automated, from this repository's current
CI: Grade C — ACQUIRABLE, confirmed blocked today.** The code is complete,
tested against synthetic fixtures for both the bulk-dataset and
per-manager-fallback routes, point-in-time-correct by design, and would need
zero redesign if SEC ever un-blocks the Actions IP range or if run from a
different network. The domain-wide SEC block this repository already proved
for Form 4, 8-K, and the bulk financial-statement dataset has now been
directly re-measured for the 13F routes specifically too, rather than
inferred by adjacency: `scripts/probe_guru_13f_access.py` (Actions run
35964478931, 2026-09-24) measured `403 Request Rate Threshold Exceeded` on
the bulk dataset and `403 Undeclared Automated Tool` on the per-manager
submissions API, verdict `BLOCKED`, route `NONE`. Re-checking this later
is one click — `guru-13f-access` in `.github/workflows/probes.yml`'s
dropdown — not a workflow to rebuild.
