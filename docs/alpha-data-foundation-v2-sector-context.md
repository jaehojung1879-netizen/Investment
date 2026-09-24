# Sector context — investigation (alpha-research-foundation-v2)

> Investigation only. No historical sector classification is backfilled
> onto the past, and no sector-context feature is wired into any scoring
> path by this document.

## Question

Can a genuinely point-in-time (as the market understood it AT THE TIME)
sector/industry classification history be reconstructed for either region,
so that sector-relative features (rotation persistence, intra-sector
dispersion, sector-relative valuation on a period-correct peer group) could
be built without backfilling today's classification onto the past — which
this repository's own PIT discipline forbids?

## United States — GICS

- **A full point-in-time GICS history exists, but only as a paid product.**
  S&P Global Market Intelligence's "GICS History" dataset covers active and
  inactive classifications for 97,000+ companies across 135+ countries, with
  history extending back to 1985 and explicit from/thru dates per
  classification — exactly the point-in-time shape this project needs. It
  is not free.
- **GICS itself was created in 1999** (S&P DJI has since extended
  classifications back to 1989 within the paid product), and the structure
  has been revised multiple times since (sector/industry-group boundaries
  moved, e.g. the 2018 restructuring that split out Communication Services
  from Consumer Discretionary/Information Technology). A classification
  applied uniformly across 2013-2026 would silently straddle at least one
  of these revisions if built from today's mapping.
- **A free, community-maintained alternative exists** (an R package
  packaging GICS data) but its point-in-time completeness and update
  cadence were not independently verified in this investigation — it is
  flagged as an unverified lead, not a usable source, until someone checks
  it directly against S&P's own revision history.
- **Grade: D — PAID_OR_LICENSED** for a genuine point-in-time US sector
  history. The static, current sector map already in `pipeline/sectors.py`
  remains the only option for production's own use, applied — as it already
  is, and not newly introduced by this finding — uniformly across the whole
  replay window.

## Korea — KRX classification (time-sensitive finding)

**KRX announced a wholesale replacement of its own industry classification
system on 2026-09-22 — two days before this investigation — called KRICS
(KRX Industry Classification Standard).** This is directly relevant and
was not something a static inventory could have anticipated:

- The **previous** KRX classification was based on Statistics Korea's
  standard industrial classification (KSIC) — a general-purpose government
  classification, not a market-structure-aware one.
- **KRICS** organizes listed companies into 9 sectors (Energy & Chemicals,
  Materials, Industrial Goods, Mobility, Information Technology, Finance &
  Real Estate, Consumer Goods, Healthcare, Media & Contents), 24 industry
  groups, 60 industries, and 129 sub-industries — built over roughly two
  years of research starting 2024, specifically to correct cases like
  semiconductor and battery makers being classified in a way market
  participants and analysts found unusable.
- Classification results and related market data (prices, trading volume)
  are set to be disclosed on the KRX Index website starting **2026-10-26**,
  with regular reclassification reviews each April based on that year's
  business/audit reports, plus ad-hoc reviews for new listings or major
  corporate events.

**Implications for this project, stated plainly, none of them acted on
here:**
1. Any KR sector-context feature built on the OLD KSIC-based mapping would
   be built on a classification KRX itself is retiring within weeks of this
   writing — a poor foundation for new research investment.
2. KRICS, once live, is a forward-looking opportunity: if KRX publishes its
   classification changes with dates (which its own "regular April review
   plus ad-hoc review" cadence suggests it will track), a genuine
   point-in-time KR sector history could begin to accumulate FROM ITS LAUNCH
   DATE forward — but this is not retroactive, and nothing in the research
   above found evidence KRX intends to publish a point-in-time history of
   the OLD classification for the 2013-2026 window.
3. This is a live, moving situation, not a settled one. A future study
   should re-check KRX's own KRICS documentation (due 2026-10-26) before
   assuming either its exact structure or its historical-publication
   behavior — nothing here is more than a two-days-old announcement,
   researched via general web search, not a primary KRX filing.

**Grade: E — NOT_RESEARCHABLE_NOW** for a retroactive 2013-2026 point-in-time
KR sector history (no such source exists or is announced). **Unresolved,
not yet gradable**, for a forward-looking KRICS-based history starting
2026-10-26 — too new to grade; revisit after the stated launch date.

## Existing production mapping — unaffected by this finding

`pipeline/sectors.py`'s current, static sector map is unaffected by
anything above: this investigation does not recommend changing it, does
not backfill KRICS or GICS history onto it, and does not wire any new
sector feature into `longterm.py`'s scoring. The existing
`rotation.py` (ETF-based) and the Opportunity radar's member-median-relative-
momentum proxy both continue to use today's static classification, exactly
as documented in `alpha-information-inventory-v1-data-map.md` §14 — nothing
here changes that.

## Conclusion

`HISTORICAL_SECTOR_CONTEXT_UNRESOLVED` stands for both regions, exactly as
`alpha-information-inventory-v1` already found — this investigation adds
detail (US: paid-only; KR: the incumbent classification is being replaced
this month) without changing the bottom line. No historical sector
classification is backfilled by this project; a sector-relative feature
that needs one stays out of scope until either a paid GICS History license
is obtained or KRICS accumulates enough of its own dated history to be
useful, whichever comes first.

Sources (WebSearch, 2026-09-24): S&P Global Market Intelligence "GICS
History" product pages and brochure; S&P DJI's own "25 Years of GICS"
overview; Korean financial press coverage of KRX's KRICS announcement
(이비엔뉴스, 뉴스웨이, 뉴데일리, 서플), 2026-09-22.
