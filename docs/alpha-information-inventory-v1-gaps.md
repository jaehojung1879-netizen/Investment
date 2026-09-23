# Alpha information inventory v1 — data gaps

> **Read-only. No production behavior changes.** This document ranks data
> gaps by whether closing them is a prerequisite for a genuinely new research
> question, not by expected performance (none was measured to produce this
> ranking).

Gap severity used throughout:

- **STRUCTURAL GAP** — without this, the next study would not be
  meaningfully different from research already done in this repository
  (see the research map's §8 comparison table).
- **NICE_TO_HAVE** — would improve a study's precision or robustness, but a
  meaningful new study can proceed without it.
- **NON_BLOCKING** — unrelated to the immediate next research question;
  worth knowing about, not worth building for its own sake right now.

---

## 1. Korean investor-type flow (per-stock 외국인/기관/개인 순매수)

**Severity: STRUCTURAL GAP.**

Nothing anywhere in this repository — not production, not the 31-feature
research matrix, not the Opportunity model — contains any investor-behavior
signal for Korea. This is a genuinely distinct information family (who is
buying, not what the price/fundamentals say), and Korea is the one region
where an official, free, per-stock, point-in-time-safe source is known to
exist (KRX's own "투자자별 매매(개별종목)" statistics, corroborated by the
`pykrx` library's documented mechanism). Grade **B — REPAIRABLE**: the data
is real and free; the blocker is that it sits behind KRX's public
statistics portal (`data.krx.co.kr`), not behind this repo's currently
subscribed Open API key (`sto/stk_bydd_trd` only), and that portal was
already found unreachable from this sandbox's network allowlist by this
repo's own `scripts/probe_krx_index_membership.py`.

**What building this requires**: either (a) KRX subscribing this repo's
existing Open API key to whatever service category exposes investor-type
data under `svc/apis` (unconfirmed whether one exists there, distinct from
the public-portal route), or (b) a collector built from an environment that
can actually reach `data.krx.co.kr`, adapting the session/CSRF handling
`pykrx` already implements rather than re-deriving it from scratch. PIT
safety is not a concern once access exists — this is same-day, end-of-trading
data with no restatement mechanism.

---

## 2. Korean macro/regime engine (entire axis)

**Severity: STRUCTURAL GAP.**

Production's 6-axis regime engine is confirmed **100% US/global** — all 21
indicator series are FRED or CBOE. Korea has zero regime-axis
representation; the only Korean macro numbers reaching the site at all are
four display-only rows (`Korea_10Y`, `Korea_3M`, `USD_KRW`) never read by
`regime.py`. Any hypothesis of the form "macro regime × KR stock behavior"
is currently untestable, not merely untested, because the Korean side of
the interaction does not exist as a computed quantity anywhere.

**What building this requires**: the ECOS fetch layer is confirmed **100%
dead code** — `config.json`'s `ecos.KR` block is read only as a boolean
diagnostic flag (`cfg.has_ecos`), and no HTTP call to `ecos.bok.or.kr`
exists anywhere in `pipeline/`. Building it needs: (a) a genuine `ECOS_API_KEY`
and a fetch function analogous to `datafeed.fetch_macro`'s FRED loop; (b)
resolving the confirmed **`KTB_3Y`/`CorpBond_3Y` duplicate-series-ID bug** —
both currently point at `817Y002`, which multiple independent secondary
sources describe as a single broad table bundling several distinct bond/CD
rates distinguished only by an `item_code` this repo's config schema has no
field for at all; a fetch function built against the current config would
not even be able to tell these two series apart; (c) live verification of
every series ID against ECOS's own `StatisticTableList` API (not possible
in this inventory — no key was available in the sandbox); (d) a decision on
whether to also pursue KOSIS (Grade C, free registration, covers series ECOS
does not — retail sales, CSI, BSI, employment detail, export detail).

---

## 3. Analyst estimate revisions (US and KR)

**Severity: STRUCTURAL GAP for a genuinely new "market expectations" axis;
NICE_TO_HAVE if the goal is only to refine existing price/fundamental
factors.**

This is the one information family named across almost every candidate
hypothesis in institutional-quality equity research (revision breadth,
dispersion, surprise) and it is confirmed **not reliably free at historical
PIT depth in either region**: US Finnhub free-tier endpoints exist but read
as current-snapshot or shallow-rolling-window products (two independently
surfaced sources disagree on retention: ~4 months vs 12-24 months — neither
is a stable 2013–2026 panel), and Finnhub maintains a *separate paid pricing
page* specifically for "stock estimates." Korea's FnGuide/FnSpace equivalent
is ToS-blocked for building a persistent database at all (already
established in `docs/challenger-2-signal-source-feasibility-v1.md`, not
re-tested here). Grade **D (US) / E (KR)**.

**What closing this would require**: a paid vendor relationship (IBES/
Refinitiv/Visible Alpha/Zacks for US institutional-grade historical
estimate revisions; no free-tier path was found for either region). This is
flagged, per this inventory's own instruction, as a candidate that
**needs paid data**, not as something to keep re-probing free tiers for.

---

## 4. Historical (point-in-time) sector classification

**Severity: NICE_TO_HAVE, not structural.**

Production's sector map (`sectors.py`) is a single current classification
applied uniformly across the whole 2013–2026 replay window. No dated,
point-in-time sector-membership history was found anywhere in the repo.
Several economically sensible features (sector rotation persistence,
intra-sector dispersion, sector-relative valuation built on point-in-time
peer groups) are downstream of this and cannot be built PIT-safely without
it. This is graded NICE_TO_HAVE rather than structural because: (a)
production already accepts today's classification as an approximation for
the whole history (an existing, disclosed limitation, not a new one this
inventory introduces), and (b) most sector-conditioned candidate hypotheses
in this inventory's next-hypotheses document do not require a *dated*
sector history to be tested meaningfully — the ETF-based `rotation.py`
sector reads and the existing static sector map are sufficient starting
points. Grade **E** for a genuine backfillable point-in-time sector history
— no evidence of a source for one was found; this repository's own PIT
discipline (per `AGENTS.md`) would forbid backfilling today's classification
onto the past even if convenient.

---

## 5. Market microstructure (true bid/ask, order flow, intraday)

**Severity: NON_BLOCKING.**

Confirmed: no bid/ask, order-book, or intraday tick data source exists
anywhere in this repository, and none of the candidate next-hypotheses in
this inventory require it — every candidate is buildable from daily OHLCV.
True microstructure signals (Amihud illiquidity computed on tick data,
genuine bid-ask spreads, VWAP) are graded **E — NOT_RESEARCHABLE_NOW** in the
data map and are non-blocking for the immediate research agenda; they would
only become relevant for a much shorter-horizon (intraday) research
question this inventory was not asked to scope.

---

## 6. Short selling (Korea and United States)

**Severity: NICE_TO_HAVE, with a genuine definitional-stability caveat that
applies regardless of severity.**

Both regions have official, free, historical short-interest data (Korea:
KRX's public short-sale statistics; US: FINRA/Nasdaq bi-monthly reports back
to 2007/2013+). Both are graded **C — ACQUIRABLE** on access grounds. But
Korea's short-selling history spans **at least three regulatory regimes**
within the 2013–2026 window — a full-market ban from roughly 2020-03 to
2021 (exact end date disputed across sources, ~2021-05), and a second,
longer ban from 2023-11-05 to 2025-03-31 paired with a structural reporting
overhaul (the Naked Short-Selling Detection System) — meaning a short-sale
factor is either illegal-to-observe or measured under a materially
different microstructure across large stretches of the sample. This is
graded NICE_TO_HAVE rather than structural because the other KR-flow gap
(§1) already covers the higher-priority "who is trading" information family
without this specific definitional instability; short-selling access should
be built only with the regime-break caveat carried forward explicitly into
any factor construction that uses it, never averaged away.

---

## 7. Accounting quality (accruals, cash conversion, working-capital change)

**Severity: STRUCTURAL GAP for a "quality beyond profitability levels"
hypothesis; the raw material is mostly already collected.**

This is the most favorable gap in the whole inventory in cost/effort terms:
operating-cash-flow, net-income, asset, and capex figures are **already
collected** as raw PIT filings (DART and Finnhub) — accruals, OCF/NI,
FCF/NI, asset growth, debt growth, capex intensity, and operating-margin
stability are all graded **FEASIBLE** in the data map's §8, meaning no new
vendor or new PIT-timing research is needed, only new derivation code
exposing fields (debt/asset/equity levels) that are currently computed as
intermediate values and discarded rather than persisted. Receivables,
inventory, and working-capital items genuinely are **not** collected in
either region's raw account list (`NOT_FEASIBLE_DATA_MISSING`) and would
require expanding `WANTED_ACCOUNTS`/the Finnhub unit-anchor list, a larger
lift than the derivation-only items.

---

## 8. Summary — what blocks a genuinely new study, ranked by what it takes to unblock

| Gap | Severity | What's missing | Grade | Effort to close |
|---|---|---|---|---|
| KR large-holdings disclosure (5%-rule, DART) | STRUCTURAL (for an ownership-behavior axis) | Not collected, but reuses an already-proven PIT mechanism 1:1 | B | **Lowest** — same vendor, same key, same receipt-date pattern as `dart_fundamentals.py` |
| US dividend-change derivation | STRUCTURAL (for a corporate-action axis), narrow scope | Raw field already collected in the Finnhub PIT store; only a derived field is missing | B | **Very low** — no new vendor, no new PIT-timing research |
| Accounting quality (accruals/cash-conversion/growth ratios) | STRUCTURAL | Raw fields collected; derived fields/exposure missing | B | Low — schema/derivation work only |
| KR investor-type flow (per-stock) | STRUCTURAL | Real official source exists, wrong access path for current sandbox/API key | B | Medium — needs either a KRX subscription change or a reachable-network build |
| KR macro/regime (ECOS layer) | STRUCTURAL | Fetch layer entirely unbuilt; one config field (duplicate series ID) is actively wrong | C | Medium-high — new vendor integration + a config-schema fix + live ID verification |
| KR/US short interest | NICE_TO_HAVE | Access exists; PIT-lag correction and (KR) regime-break handling needed | C | Medium |
| Analyst estimate revisions | STRUCTURAL (for an "expectations" axis) but likely unbuildable free | No free historical PIT panel found in either region | D (US) / E (KR) | **Not closable without paid data** |
| Historical sector classification | NICE_TO_HAVE | No dated source found | E | Not currently closable |
| Market microstructure (true tick/bid-ask) | NON_BLOCKING | No source exists; not needed for any current candidate | E | Not applicable to the current research horizon |

None of the STRUCTURAL gaps above require new collection code before a
non-data-dependent action: **the highest-priority item in this whole
inventory needs no new data at all** — `regional-alpha-model-v1`'s 31-feature
research matrix is fully built, PIT-safe, and has never been run. See the
executive report's recommendation ordering.
