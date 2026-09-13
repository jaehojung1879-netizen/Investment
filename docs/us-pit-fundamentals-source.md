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
| `efts.sec.gov`, apex `sec.gov` | `REFUSED_ON_EVERY_SEC_HOST` | US PIT probe run #1, 2026-09-13 |
| finnhub, polygon, simfin, alphavantage | host **answers** the Actions pool | same run |
| FMP, asked by date | `TOO_SHALLOW` — 5 quarters, ends 2025-06 | same run |
| **finnhub** | **`OPEN`** — 2012-13 filings with `filedDate`, all 7 production factors computable | Probes run #1 (`us-pit-fundamentals`), 2026-09-13 |
| polygon | depth confirmed, accounts not found — **unresolved**, see run #2 | same run |
| simfin | empty on every sample including AAPL — **unresolved**, our query not ruled out | same run |
| polygon | all 7 factors computable once the normalised keys were candidates; departed cohort **rate-limited**, not measured | Probes run #2, 2026-09-13 |
| simfin | `TOO_SHALLOW` — the recent-window control was served, so the history really is absent on this key | same run |

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

## Run #1, 2026-09-13 — what the probe measured

Dispatched with no vendor secrets except the FMP key that already existed.

### SEC is closed on all four hosts, and the block pages pair up

```
data.sec.gov   403  BLOCKED  4819B   baseline
www.sec.gov    403  BLOCKED  1925B   baseline
efts.sec.gov   403  BLOCKED  4819B   never asked before
sec.gov        403  BLOCKED  1925B   never asked before
```

The byte counts are the finding. `efts.sec.gov` returns the same 4,819-byte
page as `data.sec.gov`, and the apex `sec.gov` the same 1,925-byte page as
`www.sec.gov` — two block pages across four hostnames, not four independent
refusals. That is a domain-wide policy rather than a per-host one, and the two
baseline hosts refused in the same run, so it is attributable to SEC and not
to the day. `REFUSED_ON_EVERY_SEC_HOST`. The "probably" is now measured;
changing hostname is not a way in.

### Every non-SEC vendor answers the Actions pool

```
finnhub       401  ANSWERED  {"error":"Please use an API key."}
polygon       401  ANSWERED  {"status":"ERROR",...,"error":"API Key was not provided"}
simfin        401  ANSWERED  {"error":"Full authentication is required..."}
fmp           401  ANSWERED  {"Error Message":"Invalid API KEY..."}
alphavantage  200  ANSWERED  {"Error Message":"the parameter apikey is invalid or missing..."}
```

Not one `HOST_REFUSED`, not one `NO_ANSWER_FROM_HOST`. Every host replied in
its own protocol, which settles both halves of the question: the credential is
the only thing missing, and SEC's refusal is sec.gov's policy rather than
anything about the GitHub Actions address range.

Alpha Vantage answered **HTTP 200 carrying an error body**. A reader that
judged on the status code would have recorded that as data. Deciding on the
body's shape instead of the status earned its place on the first real run.

### FMP, asked by date: `TOO_SHALLOW`

All four living samples came back `NO_DATE_WINDOW_ENDPOINT` with earliest
periods of 2025-06-27 … 2025-06-30. The `limit` cap of 5 buys five quarters —
about fifteen months. The replay needs roughly **54** quarters. One quarter
deeper than run #4's 2025-09-26, for the same wall.

### The departed cohort, and a correction to this probe

All four departed names were refused with one sentence:

> `Special Endpoint : This value set for 'symbol' is not available under your
> current subscription`

That is **not** evidence that FMP lacks retired tickers, and the first version
of this probe would have let it read that way. One of the four, `AA`, still
trades today: `delisted` in `data/universe-history.json` means *left the
screening universe*, not *stopped trading*, and Alcoa left the index in 2017.
A live large-cap refused by the same sentence makes this a **subscription
symbol restriction** — FMP's free tier serves a cut universe — which is a
different problem, with a different fix, from a vendor that has no history for
dead tickers.

Two things changed as a result:

* `vendor_verdict` now splits the old `LIVING_ONLY` in two. Departed names
  that are **refused** get `DEPARTED_REFUSED` and the vendor's sentence is
  carried with it, because a paywall may be answerable with money. Departed
  names that come back **empty** keep `LIVING_ONLY`, because a vendor willing
  to answer and holding nothing is the actual survivorship hole.
* `departed_samples` now picks the names that left **earliest** rather than
  the alphabetically first. Alphabetical order chose `AA, ABC, ACE, AET` —
  spelling put a still-trading name at the head of a cohort meant to ask about
  names that are gone. Earliest-left gives `ANR, BIG, CBE, DV`: names the
  replay's very first cross-sections held, and mostly tickers that genuinely
  retired.

## Run #2, 2026-09-13 — the US route opens

The first run with `FINNHUB`, `MASSIVE` (Polygon) and `SIMFIN` in the
environment, and therefore the first measurement of **depth** rather than
reachability.

### finnhub — `OPEN`, and this is the route

| cohort | sample | result |
|---|---|---|
| living | AAPL, JPM, XOM, KO | `PIT_DEPTH_CONFIRMED` — 5 periods each inside the window |
| departed | ANR | `PIT_DEPTH_CONFIRMED` — 7 periods |
| departed | BIG | `PIT_DEPTH_CONFIRMED` — 4 periods |
| departed | CBE | `PIT_DEPTH_CONFIRMED` — 3 periods |
| departed | DV | `NO_ROWS` |

Every one of the seven production value and quality factors is computable from
what came back — `earningsYield`, `bookYield`, `fcfYield`, `roe`, `opMargin`,
`profitMargin`, `debtToEquity`. That is the half of the model the US leg has
never been evaluated on, closed by one vendor, with `filedDate` on the rows.

Full backfill: **10 calls per ticker × 829 names = 8,290 calls.**

### polygon — the key works; the verdict did not

The `MASSIVE` secret authenticated (32 chars) and the depth is, if anything,
better than finnhub's: six periods per living name, and three of the four
departed names including `DV`, which finnhub missed. The probe called it
`OPEN`.

It should not have. In the same report, **not one of the nine production
accounts was found** — every factor came back `불가`. A source we cannot
compute a single factor from is not an open route, and a verdict that says it
is would send someone to write a collector against nothing.

The likely cause is this probe, not Polygon: `read_polygon` looked for the
filer's own US-GAAP tags (`NetIncomeLoss`) in a response from a vendor that
NORMALISES filings, and a normalised statement does not keep the filer's
spelling. That is the `fillingDate` lesson arrived at from the other side —
a renamed field and an absent field produce the same output, and the output
reads as the worse finding. Polygon's status is **unresolved pending a
re-measurement**, not `OPEN` and not a failure.

### simfin — reported `TOO_SHALLOW`, and that was not a finding about simfin

All eight samples returned zero rows. **AAPL included**, for a window in which
AAPL certainly filed. A 200 carrying an empty list, across an entire panel, is
far more likely our query than the vendor's coverage — wrong parameter names,
wrong casing, wrong period spelling. Access is measured per service, and a
vendor's refusal is attributed only after our side of the request has been
ruled out. Ours had not been. simfin is **unresolved**, not shallow.

### fmp — `TOO_SHALLOW`, confirmed

Earliest period 2025-06-27 … 06-30 on the `limit=5` cap; five quarters against
the roughly fifty-four the replay needs. All four departed names refused on
the subscription sentence.

### What run #2 changed in the probe

Three defects, all of which produced a confident sentence the evidence did not
support:

1. **`OPEN` did not look at the accounts.** It now does: depth and a filing
   date with no computable factor is `ACCOUNTS_NOT_FOUND`.
2. **A miss named only what we looked for.** The readers now carry
   `fieldsSeen` — the vendor's own field names — so "missing `netIncome`"
   becomes "carries `net_income_loss`", which is a name to add rather than a
   vendor to retire. Polygon's normalised keys are candidates alongside the
   US-GAAP tags; neither list is asserted to be right.
3. **An empty answer had no control.** When the historical window comes back
   empty, the probe now asks the same vendor for `2025-01-01..2026-06-30`,
   a window where the answer is not in doubt. Empty there too and the verdict
   is `REQUEST_NOT_RULED_OUT`, which points at our query rather than at the
   vendor's history.

## Probes run #2, 2026-09-13 — the fixes land, and one more mis-read

Same workflow, after the three corrections above shipped.

**finnhub — `OPEN`, unchanged and now under a stricter rule.** Same eight
samples, same depths, all seven factors. `fieldsSeen` confirms what it is:
`AccountsPayableCurrent`, `AdditionalPaidInCapital`, `AccumulatedOther
ComprehensiveIncomeLossNetOfTax` — the filer's own US-GAAP tags, re-served.

**polygon — the parser was the problem, and the fix worked.** All seven factors
are now computable, and `fieldsSeen` says why: `accounts_payable`, `assets`,
`basic_average_shares`, `cost_of_revenue` — normalised snake_case, exactly the
vocabulary run #2's report could not name before. The hypothesis held.

**And the verdict was wrong again, for a new reason.** polygon came back
`LIVING_ONLY` — a survivorship hole — on a cohort where three of the four names
were refused with:

> `You've exceeded the maximum requests per minute, please wait or upgrade your
> subscription to continue.`

Those same three names — `BIG`, `CBE`, `DV` — had been served with three to six
periods each one run earlier. polygon has them. What the probe measured was its
own pacing, and it wrote the result down as the vendor's coverage. A refusal
that says *slow down* is not an observation about the data; it means the
question was never asked. `RATE_LIMITED` is now its own outcome, it ranks below
every real answer so another candidate always wins, and a cohort containing one
is `RATE_LIMITED_BEFORE_MEASURED` rather than any verdict about coverage.

**simfin — `TOO_SHALLOW`, and this time the control says so.** The control
window fired as designed and simfin answered it, which is what separates "no
such history" from "you did not understand the question". The control's result
was not printed, though, so the evidence for the verdict was invisible in the
log; it is printed now. On the current reading simfin genuinely lacks 2012-13
depth on this key.

## The collector

`scripts/collect_finnhub_fundamentals.py`, run by the `us` job of **Collect
fundamentals**, writing `ledger/fundamentals/us/finnhub-YYYY.jsonl.gz` on the
`signal-history` branch — the same shape, branch and budgeting the Korean
collector uses.

* **The universe is every US name that was ever a member** (829), not the
  seventy in today's config. 219 of them left before the replay starts.
* **Ten windows per ticker** from 2012-01-01, gapless and non-overlapping, so a
  resumed run cannot ask for a different span than the one already stored. It
  starts a year before the replay because a trailing-twelve-month figure at
  2013-01 needs the four quarters behind it.
* **A filing with no `filedDate` is refused.** Same rule as DART's receipt date.
* **Concepts are stored under the filer's own tags.** A normalisation applied at
  collection time cannot be revisited without re-fetching, and probe run #2 is
  the standing reminder that a tag vocabulary is measured, not assumed.
* **A rate limit stops the run and does not close the window.** The next run
  asks it again.
* **Windows asked are recorded separately from filings stored**, because a
  window that genuinely held nothing is, from the shards alone, indistinguish-
  able from one never asked — and re-buying it every run spends the budget on
  nothing.

### What it deliberately does not do yet

**There is no derivation.** `dart_derive` could only be written after the
Korean collector's field inventory had measured, over 2,927 filings, whether a
Q3 income figure was three months or nine — and reading a cumulative cash flow
as a quarterly one would have inflated free cash flow fourfold with nothing
raising an error. The same question is open here and the answer is not in
anyone's memory: a US 10-Q is filed with both a three-month and a year-to-date
context, and which one finnhub flattens into `report.ic` is a fact about the
vendor.

So this run measures it. The collector reports, and writes to
`inventory.json`, the distribution of stated period lengths **per form type** —
because a pooled count cannot answer the question a TTM is built from. The
derivation is a separate change, written against that answer, and until it
exists nothing is wired into the replay: `build_pit_fundamentals.py` still
knows only the Korean store, and `replay.yml` still passes only `pit-kr.jsonl`.

## Collection run #1, 2026-09-13 — what 4,971 filings said, and what they did not

The first slice bought 1,500 windows and stored **4,971 filings, none refused**:
every one carried a `filedDate`, which is the single field the whole collection
exists for. Shards landed for 2011–2015. Four things the run measured, and the
change each one forced:

### The filing periods are cumulative — but that is evidence, not proof

Period lengths split almost evenly three ways: **1,801 at a quarter, 1,615 at a
half, 1,553 at three quarters**. Three independent quarters would not produce a
half and a three-quarter bucket at all, so the *filing envelope* runs from the
fiscal year start.

That is a fact about the envelope. The entries inside `report.ic` carry no dates
of their own, so it is evidence about the values rather than proof. DART faced
exactly this question and settled it by **value ratios over 84 companies**, not
by field names, and the same method settles it here on data already bought:

* within one ticker-year, half-year over first-quarter and three-quarter over
  first-quarter;
* cumulative predicts ≈2.0 and ≈3.0, independent quarters ≈1.0 and ≈1.0;
* the statistic is the **median across companies**, never one company's ratio —
  no firm earns evenly through the year, and a seasonal one appears to
  contradict whichever reading it happens to sit opposite;
* four flow accounts are measured separately (net income, revenue, operating
  income, operating cash flow). Four agreeing is the claim. Four disagreeing is
  a finding to look at, not to average — the report says so and withholds the
  verdict;
* fewer than 30 ratios, or a median between the two bands, reports
  `INCONCLUSIVE` and **exits non-zero**, so a green check never implies an
  answer the data did not give.

`scripts/measure_us_period_semantics.py`, run as a step of the `us` job and
committed beside the shards as `period-semantics.json`.

### The FY term was never being collected

The rollforward a cumulative store needs is `TTM(Y,Q) = FY(Y-1) − cum(Y-1,Q) +
cum(Y,Q)`. Every term but one was in the store: the collector only ever asked
`freq=quarterly`. **Without the annual filing there is no TTM at all**, not a
less accurate one.

So the collector now runs both passes, annual first — one 10-K a year is the
cheap half and the anchor everything else hangs off. The 1,500 quarterly
windows already paid for are **not re-bought**: `windows.json` from the first
slice holds three-item entries, and a three-item entry means exactly what it
did, the quarterly pass. Reading those as "both frequencies done" would skip
1,500 annual calls that never happened; dropping them would re-buy 1,500
windows.

### Every GAAP tag arrives in two spellings

Both `Assets` and `us-gaap_Assets` are in the store, for the same account. A
derivation matching one spelling silently halves its own coverage.

Only a **known** namespace is stripped (`us-gaap`, `dei`, `srt`, `ifrs-full`,
`invest`, on either `_` or `:`). A filer's own extension tag contains an
underscore too, and collapsing `AcmeCorp_SpecialCharge` to `SpecialCharge`
would merge one company's bespoke line into an account that means something
else — with nothing downstream able to tell.

### Eight unit spellings, three meanings

| spelling | count | means |
|---|---|---|
| `usd` | 388,484 | currency |
| `_usd` | 36,280 | currency |
| `usdollar` | 3,128 | currency |
| `usd/shares` | 8,789 | per share |
| `usd/share` | 5,976 | per share |
| `_usd_/_shares` | 1,372 | per share |
| `shares` | 7,725 | share count |
| `unit12` | 7,185 | unclassified |

A derivation filtering on `unit == "usd"` drops 39,408 currency values. Worse,
per-share is tested **before** currency, because `usd/shares` contains `usd`
and classifying it as currency turns an EPS into a dollar amount nothing
downstream can tell apart from a real one. `unit12` is named rather than
guessed.

## Collection run #2, 2026-09-13 — the question is answered: **CUMULATIVE**

The annual pass ran, 1,500 more calls, 1,661 new filings, all 10-K. The store
is now 6,632 filings and the ratio measurement decided, on every flow account,
with between 1,018 and 1,393 ticker-years behind each:

| account | half / Q1 | three quarters / Q1 | three quarters / year | ratios | verdict |
|---|---|---|---|---|---|
| net income | 2.05 | 3.13 | 0.75 | 1,368 | CUMULATIVE |
| revenue | 2.04 | 3.08 | 0.74 | 1,122 | CUMULATIVE |
| operating income | 2.07 | 3.15 | 0.75 | 1,018 | CUMULATIVE |
| operating cash flow | 1.96 | 3.12 | 0.70 | 1,393 | CUMULATIVE |

Cumulative predicts 2.0 and 3.0; independent quarters predict 1.0 and 1.0.
Every account landed on the first, none between the bands, and the four agree.

**So a 10-Q's income statement runs from the fiscal year start, and TTM must be
built by rollforward: `TTM(Y,Q) = FY(Y-1) − cum(Y-1,Q) + cum(Y,Q)`.** Summing
four quarterly figures — the obvious reading, and the one a derivation written
from memory would have used — would have counted the first quarter four times,
the second three, and produced free cash flow roughly two and a half times too
large with every number still looking ordinary.

### Two defects the same data found

**A 10-K is not always a year.** Four of the 1,661 annual filings state a
period that is not: LYB 91 days, TTWO 89, DRI 244, and one stating no span at
all. They are transition reports, filed when a company moves its fiscal year
end. The stage was being read from the form — a 10-K taken to be a year by
definition — so LYB's 91-day figure would have entered the rollforward as the
FY term and understated that year roughly fourfold. The stage now comes from
the stated period length and from nothing else; a span that is not one of the
four stages yields no stage rather than a guess.

**5,353 values sit under labels that are not units.** `unit12`, `unit1`,
`u001`, `u002`, `unit13`, `unit14`, `unit15` — the filer's own XBRL unit ids,
passed through untranslated, carrying ordinary concepts: `NetIncomeLoss`,
`Assets`, `OperatingIncomeLoss`, `WeightedAverageNumberOfDilutedSharesOutstanding`.
Two measurements decided what to do:

* the same label means different things in different filings (`unit1` is
  dollars in one and a share count in another), so no table from label to
  meaning can exist — `unit_class` is right to refuse it;
* inside one filing the labels are consistent and there are only two to four
  of them. AMD's 2012 10-Q puts every dollar figure under `unit1` and both EPS
  figures under `unit14`.

So a label resolves **per filing**, from the concepts carrying it: a label
holding `EarningsPerShareBasic` is that filing's per-share unit. Measured over
the store, 17,931 unclassified values become 358, across 259 filings, and no
label that already read on its own changed meaning.

One guard, added because a test caught it rather than because it had happened:
an anchor says what KIND of quantity a label holds, never which currency.
`Revenues` under a label spelled `eur` is a revenue figure, and `currency`
means US dollars everywhere downstream. Promotion to currency is therefore
limited to labels shaped like generated ids — every one the anchors promoted
across 6,632 filings contained a digit, and every named unit (`pure`, `number`,
`store`, `eur`) did not. Per-share and share counts have no denomination to get
wrong, so they promote freely, which is what recovers the 163 values spelled
`eps`.

What is left unclassified is now visible by name: `number` 216, `pure` 83,
`store` 2, `eur` 1, and 30 values under generated ids that carried no anchor.
None of them is money this pipeline can spend.

### Where the collection stands

3,000 of 16,580 windows (18.1%). Nothing is wired into the replay until the
backfill is complete — a derivation over 18% of the universe would be a
survivorship hole with a different name.

**It finishes itself.** The workflow already runs on a cron at 03:40 UTC and
the `us` job's gate admits a scheduled event, so no one has to press anything;
what was missing was the budget. The first two slices spent 1,500 calls each,
which at that rate left nine more nights of remembering. The remaining 13,580
windows are 249 minutes at the collector's 1.1-second pacing, so the scheduled
ceiling is now the whole backfill (16,600 calls, 300 minutes) and one run
covers it.

A budget is a ceiling, not a target. Once the store has caught up the work
list is empty and the run ends in seconds, so the large ceiling costs nothing
on an ordinary day — it only removes the button.

The dispatch inputs are empty for the same reason. A `workflow_dispatch` input
with a default SENDS that default on every run, so a `default: "1500"` beside a
16,600 ceiling is not a suggestion — it is an override that fires every time
someone presses the button, and the mobile app cannot pass inputs at all, so
from a phone there is no way to override the override. Left empty, both the
scheduled path and the hand-started one fall through to the ceiling each region
set for itself, and typing a number still wins for anyone who deliberately
wants a short run.

Two things this does not change, and one it might. The pacing is what a rate
limit cares about, and 54 calls a minute stays under finnhub's 60. The
resumption rules are untouched: a refusal stops the run and does not mark the
window done. What is genuinely untested is whether a run this long meets a
daily quota that two shorter ones never reached — if it does, the run stops
there, the next night resumes from it, and we will have measured where the cap
actually is. That is the same standard every other claim in this document was
held to, and nothing is lost either way.

The budget is also now coupled to the job timeout by a test rather than by
someone remembering: a minute ceiling set at or near the 330-minute timeout
means the runner kills the job before the commit step, and every filing that
run paid for is thrown away with the container.

## Primary and backup, once the backups are real

finnhub is the primary because it is the only vendor measured end to end:
depth, publication dates, and every production account. The backups exist for
the failure this project has already lived through once — a vendor that served
us in August and refused in September.

The shape is the one the Korean price leg already uses: one vendor of record,
a second read alongside it, and a cross-check that has to agree before either
is sealed. What run #2 adds is the reason it is worth the second call —
**finnhub missed `DV` and polygon missed `ANR`.** The gaps are not the same
gaps, so the pair covers cross-sections neither covers alone.

Three rules carry over from the price leg, and they are not optional:

* **The vendor of record is recorded per row.** `PIT_FUNDAMENTALS_V1` already
  carries `source` and `sourceAsOf`; a panel mixing vendors without saying
  which answered where is a panel nobody can audit later.
* **A fallback never silently replaces the primary mid-history.** A ticker
  whose 2013 comes from one vendor and whose 2020 comes from another has a
  seam, and a seam that nothing reports is the v12 truncation in new clothes —
  46,356 rows went missing that way and no gate noticed. The seam is recorded
  and, where it matters, it fails the run.
* **The cross-check compares the publication date, not just the value.** Two
  vendors can agree on a quarter's net income and disagree by weeks on when it
  became visible. The second number is the one point-in-time depends on.

None of that gets built against polygon or simfin until they have a verdict
that survived a re-measurement. The next run decides whether the backup is
polygon, simfin, both, or neither — and finnhub does not wait for it.

## What was asked and still needs a credential

**Four vendors that are not sec.gov.** Each re-serves filings from a different
host under a different access model, each is now proven reachable, and each
either carries a publication date or does not:

| Vendor | What would make it the answer | What would kill it |
|---|---|---|
| `finnhub` | `/stock/financials-reported` returns the filer's own XBRL with `filedDate` and `acceptedDate`, and takes `from`/`to` | no 2013 depth, or no delisted names |
| `polygon` | `/vX/reference/financials` carries `filing_date` and `acceptance_datetime` and filters by report date | free-tier depth cap |
| `simfin` | normalised statements carrying `Publish Date` **and** `Restated Date` — restatement history is more than SEC's own API gives | ticker coverage |
| `alphavantage` | — | probed specifically to **measure** whether any publication date exists, rather than to exclude it on the strength of its documentation |

## The probe

`scripts/probe_us_pit_fundamentals.py`, run by the **Probes** workflow
(`.github/workflows/probes.yml`) with `probe: us-pit-fundamentals`. It writes
nothing to the ledger; **`replay-v14` stays sealed and no re-acquisition is
triggered.**

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

Actions → **Probes** → Run workflow, `probe: us-pit-fundamentals`, `args`
empty. GitHub registers a `workflow_dispatch` workflow only once the file is
on the default branch, so a change to this workflow has to merge before it can
be dispatched. (`Tests` runs on the pull request either way.)

The secrets it reads, and the names they are stored under:

| Vendor | Secret | Note |
|---|---|---|
| finnhub | `FINNHUB` | |
| polygon | `MASSIVE` | the name Polygon's own signup handed out; the repository keeps the vendor's spelling rather than inventing a matching one |
| simfin | `SIMFIN` | |
| fmp | `FMP` | already present since the earlier FMP probe |
| alphavantage | `ALPHAVANTAGE` | optional — probed to confirm the ABSENCE of a publication date |

Read the per-vendor verdict:

| Verdict | What it means for the next move |
|---|---|
| `OPEN` | living **and** departed names returned 2013 filings with publication dates, **and** at least one production factor is computable — write the collector against this vendor |
| `ACCOUNTS_NOT_FOUND` | depth and filing dates arrived but no production account was found under any candidate name. The report's `fieldsSeen` lists what the vendor actually sent; add those names and re-measure |
| `REQUEST_NOT_RULED_OUT` | the historical window came back empty **and so did a recent control window**. Our query is the suspect, not the vendor's history |
| `DEPARTED_REFUSED` | depth is there; the departed names were refused per symbol. Read the sentence — a subscription limit is answerable with money, "no such symbol" is not |
| `LIVING_ONLY` | depth is there and the departed names came back **empty** — the vendor was willing and had nothing. Usable only if the survivorship hole is quantified and declared |
| `TOO_SHALLOW` | reachable, but does not reach 2013 — same shape as FMP's free tier |
| `NO_POINT_IN_TIME` | data without a publication date; retire it |
| `KEY_REFUSED` | the vendor's sentence in the report says whether a subscription or a different key is the fix |
| `HOST_REFUSED` | the SEC shape; a key changes nothing |
| `NO_ANSWER_FROM_HOST` | not attributable to the vendor yet — check whether other hosts answered in the same run |

Only a vendor reported `OPEN` gets a collector written against it, and the
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
