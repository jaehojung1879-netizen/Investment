# The US half of the model has never been measured

`alphaDiagnostics` in `ledger/historical-portfolio-validation.json` reports
`fullComposite` with **zero observations in the US** and `claimEligible:
false`. The reason is one line of wiring: `historical_replay.py` reads every
ticker's fundamentals from ONE `FundamentalStore`, and the only file wired
into it is `ledger/fundamentals/pit-kr.jsonl`.

So the 13-year replay tested `momentum 0.3 + lowvol 0.2` in the US. The other
half of the production weight — **value 0.3 and quality 0.2** — has never been
evaluated on a US name, not once, in thirteen years of replay. That is why
this is first: the two selectors' results (`ALPHA_RANK` −4.87%p, `CALIBRATED`
+1.08%p, pairwise CI `[-1.006, +0.042]` → INDISTINGUISHABLE) are measurements
of something that is not the production model in the region that carries most
of the book. Whatever we fix next, we cannot tell whether the fix was right.

## What CI has actually proven

Only these. Everything else in this document is a measurement to take, not a
route to use.

| Source | Verdict | Where it was proven |
|---|---|---|
| `data.sec.gov` | `REFUSED_ON_EVERY_ADDRESS` | `Probe SEC egress addresses` run #1, 2026-09-04 |
| `www.sec.gov` | `REFUSED_ON_EVERY_ADDRESS` | same run |
| SEC, any header set | `REFUSED_ON_EVERY_HEADER_SET` | `Probe SEC header isolation` |
| SEC bulk ZIP datasets | block page | `Probe SEC bulk financial statement datasets` |
| FMP `/stable`, current key | serves statements **with `filingDate`** | `Probe FMP fundamentals` run #4, 2026-09-05 |
| FMP `/stable`, current key | `limit` capped at **4 periods** | same run |

The SEC verdict is as firm as this repository's evidence gets. Eight parallel
runners took eight **distinct** Azure addresses — `4.154.40.4`,
`4.154.135.147`, `4.155.255.60`, `20.109.39.56`, `20.168.110.19`,
`20.169.93.176`, `128.24.162.210`, `172.214.155.183` — and all sixteen
requests came back 403. The header run had already shown the refusal does not
move when the request moves: four header sets across two hosts, byte-identical
block pages (4,819B on `data.sec.gov`, 1,925B on `www.sec.gov`). A refusal
that does not change when the request changes is not reading the request.

The FMP result is the one that is easy to misread, so it is worth stating
precisely. FMP **is** open, it **does** carry the point-in-time field, and the
sample returned `filingDate` on 4 of 4 rows for AAPL, JPM, XOM and KO. What it
will not do is go back: `limit=20` was refused with FMP's own sentence —

> `Special Parameters : The values for 'limit' must be between 0 and 5 based
> on your current subscription.`

— and the deepest period any call reached was **2025-09-26**. The replay
starts **2013-01-01**. Two further limits showed up in the same run: `O`
(Realty Income) was refused on the symbol itself (`Special Endpoint : This
value set for 'symbol' is not available under your current subscription`), and
the statement endpoints take no date argument at all, so there is no window to
ask for and no offset to page with.

**Therefore: there is no CI-proven route to US point-in-time fundamentals
today.** FMP is the only vendor proven reachable from the Actions IP pool, and
it is proven to stop eleven years short of where the replay begins. Naming any
other vendor as a route right now would be exactly the move that produced run
#49, where an unproven KRX endpoint answered 119 of 119 Korean tickers with
`400 Bad Request`.

## What has never been asked

Two things, and both are cheap.

**SEC has two more hosts.** The verdict was reached on `data.sec.gov` and
`www.sec.gov`. Access is measured per service — the KRX approval opened
`sto/stk_bydd_trd` and left three other endpoints refusing exactly as before —
so `efts.sec.gov` and the apex `sec.gov` (no `www`) are not covered by a
finding about two other hostnames. They are probably refused too. "Probably"
is the word this repository has learned to spend ten minutes removing.

**Four vendors that are not sec.gov.** Each re-serves filings from a different
host under a different access model, and each either carries a publication
date or does not:

| Vendor | What would make it the answer | What would kill it |
|---|---|---|
| `finnhub` | `/stock/financials-reported` returns the filer's own XBRL with `filedDate` and `acceptedDate`, and takes `from`/`to` | no 2013 depth, or no delisted names |
| `polygon` | `/vX/reference/financials` carries `filing_date` and `acceptance_datetime` and filters by report date | free-tier depth cap |
| `simfin` | normalised statements carrying `Publish Date` **and** `Restated Date` — restatement history is more than SEC's own API gives | ticker coverage |
| `alphavantage` | — | probed specifically to **measure** whether any publication date exists, rather than to exclude it on the strength of its documentation |

## The probe

`scripts/probe_us_pit_fundamentals.py`, run by
`.github/workflows/us-pit-fundamentals-probe.yml`. It writes nothing to the
ledger; **`replay-v14` stays sealed and no re-acquisition is triggered.**

Every key is optional, and that is the point. Reachability is asked **without
a credential**, so a run with no secrets at all still answers the question run
#49 skipped: *does this host answer the Actions IP pool?* A vendor with no key
is reported `KEY_MISSING` and nothing is claimed about its depth — a
credential that was never sent is not evidence about the source.

### The standard every vendor is judged by

Each rule below is a mistake this repository has already paid for.

1. **A structured refusal counts as an answer.** KRX's
   `{"respMsg":"Unauthorized Key"}` established that the base and the path
   were right and the key had been read. An HTML interstitial establishes
   nothing. `reach_outcome` decides on the body's shape, never the status.
2. **Nothing coming back is not the vendor's fault yet.** `NO_ANSWER_FROM_HOST`
   is its own verdict, separate from `HOST_REFUSED`, because our egress has
   not been ruled out — and attributing a refusal before ruling our side out
   is how the SEC reading spent a while being an assumption that happened to
   be correct.
3. **Depth is asked BY DATE.** The window is `2012-01-01..2013-06-30`, around
   the replay's own first session. A vendor that accepts the window and
   answers with recent rows is reported `WINDOW_NOT_HONOURED`, never as depth:
   that is the Naver `fchart` shape, which took `count=6000`, capped the
   response at ~3,000 trailing sessions, and let the caller apply `start` to
   an already-truncated window — 46,356 Korean rows vanished in v12 and
   nothing failed. A vendor that takes no date argument at all gets
   `NO_DATE_WINDOW_ENDPOINT`, a different finding with a different fix.
4. **The publication date is decided before depth.** A filing dated
   2013-03-31 that we cannot show was published before 2013-05-14 is
   lookahead, not history. Same standard as DART's receipt date and SEC's
   `filed`.
5. **Living and departed names are separate cohorts, never pooled.** 219 of
   the 829 US names in `data/universe-history.json` were members before 2013
   and have since been delisted. A vendor serving only what is listed today
   answers for 610 of 829 and reports as "73% coverage" — when what it
   actually has is the survivorship hole v12 and v13 spent two generations
   closing in Korean prices. That verdict is `LIVING_ONLY`, and it is not
   `OPEN`.
6. **Field names get candidate lists.** FMP shipped the misspelt
   `fillingDate` on `/api/v3` for years and corrected it to `filingDate` on
   `/stable`; a reader that knew one spelling would have reported "no
   point-in-time" about a response carrying it in every row. Which name
   answered is recorded.
7. **The vendor's own sentence is the finding.** Refusal bodies are kept and
   trimmed, never paraphrased into our label and never dropped — the 402 body
   that got discarded is how "FMP dropped statements from the free tier"
   became a conclusion about a run that had also, in its own log, been served.
8. **The backfill is sized off every name that was ever a member** (829), not
   the 70 in today's config. Sizing off the current list under-orders by an
   order of magnitude and rebuilds the survivorship hole while doing it.

### Running it

GitHub registers a `workflow_dispatch` workflow only once the file is on the
default branch, so this one cannot be dispatched from the PR branch — merge
first, then run it. (`Tests` runs on the pull request either way, so the 49
unit tests are proved in CI before the merge.)

1. Run **Probe US PIT fundamentals sources** with no secrets added yet.
   That alone settles the two unasked SEC hosts and tells you which of the
   four vendors answers the Actions IP pool at all. Cost: about a minute.
2. For every vendor that came back `KEY_MISSING` rather than
   `NO_ANSWER_FROM_HOST`, take a free key and add it as a repository secret:
   `FINNHUB`, `POLYGON`, `SIMFIN`, `ALPHAVANTAGE`. The workflow already
   passes all four through; nothing else needs editing.
3. Run it again. Read the per-vendor verdict:

   | Verdict | What it means for the next move |
   |---|---|
   | `OPEN` | living **and** departed names returned 2013 filings with publication dates — write the collector against this vendor |
   | `LIVING_ONLY` | depth is there but the dead names are not; usable only if the survivorship hole is quantified and declared |
   | `TOO_SHALLOW` | reachable, but does not reach 2013 — same shape as FMP's free tier |
   | `NO_POINT_IN_TIME` | data without a publication date; retire it |
   | `KEY_REFUSED` | the vendor's sentence in the report says whether a subscription or a different key is the fix |
   | `HOST_REFUSED` | the SEC shape; a key changes nothing |
   | `NO_ANSWER_FROM_HOST` | not attributable to the vendor yet — check whether other hosts answered in the same run |

4. Only a vendor reported `OPEN` gets a collector written against it, and the
   verdict goes in this document with its run number before any collector is
   merged.

## If every vendor fails

There is one route left that does not depend on any vendor, and its honest
label is that it **deliberately does not run in CI**.

SEC publishes the same filing data as quarterly **Financial Statement Data
Sets** — `sub.txt` carries the accession's `filed` date, `num.txt` the tagged
values. They are refused from the Actions IP pool like everything else on
`sec.gov`, but they are ordinary downloads from any address that is not in
that pool. Fetched once from a laptop, filtered to the 829 US names, converted
to `PIT_FUNDAMENTALS_V1` rows and committed to the `signal-history` branch,
they would give the US half exactly what DART gave the Korean half — from the
authoritative source, free, with the real filing date.

The trade-off is that it is a manual quarterly refresh instead of a scheduled
job, and that has to be stated in `metricDefinition` rather than discovered
later. It is the fallback, not the first move, because a vendor reported
`OPEN` would automate the same thing.

## What this does not change

No sealed input moves. `replay-v14` stays sealed, no new `REPLAY_VERSION`
generation is needed, and no 50-minute re-acquisition is triggered. The probe
writes one JSON artifact and nothing else.
