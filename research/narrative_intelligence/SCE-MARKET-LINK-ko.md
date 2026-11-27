# Sixth batch: beliefs and prices — first descriptive market link

2026-11-28 · EXPLORATORY / AUTHOR_VALIDATION_ONLY.

## Source recheck, not an independent audit

The existing SCE 22-month panel (Jan 2025–Oct 2026, 44 published levels) was
rechecked against the original NY Fed releases or indexed primary-source
excerpts during this chat, using the source URLs and publication dates in
sce_release_panel.json. No new raw-file receipt. No values overwritten.
For the May 2026 release (June 8), the stock expectation is printed as
38.0%, but its narrative says +0.4 pp; April release (May 7) prints 38.4%.
Unemployment 43.2% vs April 43.9% likewise differs from the May release's
stated -0.4 pp. The reason (revision, rounding or text error) is unresolved.
Use consecutive published levels and compute -0.4 and -0.7 pp, respectively.
This is a published-level difference, not necessarily the agency's revised
month-on-month comparison. Retain discrepancy rather than silently edit.
Sources:
- https://www.newyorkfed.org/newsevents/news/research/2026/20260507
- https://www.newyorkfed.org/newsevents/news/research/2026/20260608

The NY Fed SCE page confirms chart workbook and latest/older microdata links.
https://www.newyorkfed.org/microeconomics/sce
https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-data.xlsx
Web XLSX unsupported; direct urllib read failed DNS Errno -3 again. No
workbook acquired. No bypass, no claim of historical release-time PIT.

## Price comparison (not an investment outcome test)

Same contiguous window as prior household-belief pilot. Read public secondary
SPX monthly price return table rounded to one decimal place (not total return):
https://returnsview.com/stock/GSPC/
Cross-check early months with:
https://amsflow.com/data-reports/historical-returns/SPX
and late 2026 closes with:
https://portfolio-terminal.com/markets/sp-500/september-2026
https://www.statmuse.com/money/ask/s-and-p-500-total-return-indices-monthly-closing-price-for-2026

Source caches differ: opened Amsflow and returnsview pages can show a partial
August 2026 month; do not use that partial value. Use completed-month rounded
values for Aug/Sep/Oct 2026 (+2.6/-0.5/-0.9 percent) verified in latest indexed
monthly table and the dated close reports. The StatMuse title mentions total
return but displayed underlying is GSPC; treat as price-index close only.
No full proprietary price series stored in git; redistribution rights not
established. These are secondary current-history snapshots, not a canonical
authorized price ledger. Aggregate derived diagnostics only. Data period
chosen in prior pilot, comparison chosen here, not preregistered.
For 21 changes Feb 2025–Oct 2026 compute dB_t = B_t - B_(t-1) from published
levels. Compare with r_(t-1) (fully elapsed calendar month before the survey
month) and r_t (same survey month, includes trades after some respondents
answered). Neither is a future return target from SCE public release time.
Same-month association cannot identify causal direction, nor an early signal.
No access to existing protected study outcomes or trading evaluation.

| Measure | Prior-month SPX price return | Same-month SPX price return |
|---|---:|---:|
| Stock belief change Pearson r (21) | -0.089638 | 0.484716 |
| Same nonzero direction (of 21) | 9 | 12 |
| Leave-one-month-out minimum r | -0.214267 | 0.360398 |
| Leave-one-month-out maximum r | 0.035535 | 0.600862 |
| Unemployment belief change r (21) | -0.236365 | -0.470184 |
| Stock belief r Feb-Dec 2025 (11) | -0.089240 | 0.560685 |
| Stock belief r Jan-Oct 2026 (10) | -0.086476 | 0.442107 |

JS on committed SCE panel and separately run Python statistics on a
transcription independently reproduced primary numbers and leave-one-out
range; same author, not independent reviewer. No confidence interval,
significance or causal conclusion; leave-one-out is a fragility diagnostic
not a statistical test. The data are short, serially dependent, rotating
aggregate sample with overlapping 12-month subjective probability horizons.

The meaningful result: contemporaneous co-movement exists in this small
sample; prior-month return alone has weak association with monthly belief
change. It is consistent with concurrent response to market/economic news,
but cannot prove extrapolation or direction. No evidence here that belief
innovations forecast future prices. KEEP matched timing and multidimensional
measurement. STOP interpreting this as predictive edge, or fitting a model
to 21 points. Potential research: independently admit survey field dates
and actual response-level timing, trailing prices and contemporaneous
economic-news surprises, distinguish revision/aggregate composition, then
evaluate a fixed baseline on a fresh sample. Exact timestamp and source rights
are blocking. Only after a separately approved prospective experiment may
we score new forecasts or subsequent total return.

Reproduction: provide lawful external CSV with columns month,price_return_pct
and exactly Jan 2025–Oct 2026, rounded to one decimal place; run
python -m research.narrative_intelligence.sce_market_link --returns /tmp/spx.csv
The script does not fetch or persist price data. New module not run from
the remote committed tree here; calculation independently checked in Python.
No new infrastructure or forecast registry activation.
